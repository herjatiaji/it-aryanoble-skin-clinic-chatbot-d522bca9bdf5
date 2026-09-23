"""MedicalAgent Tool Orchestrator for ERHA RAG System (PT Arya Noble).

Single Responsibility:
- Acts as the Agent Tool Orchestration & Reasoning Module for complex multi-topic queries.
- Executes parallel tool calls (search_products, search_treatments, search_contraindications).
- Fails closed on unknown tool calls (no un-audited fallbacks).
- Delegates final answer synthesis, safety gate, and guardrails to the unified GenerationPipeline.
"""

import json
import concurrent.futures
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger

from app.rag.config import settings
from app.rag.services.interfaces import BaseLLMAdapter
from app.rag.services.rag_retriever import HybridRetriever
from app.rag.services.intent import QueryIntentDetector, QueryIntent


# ── Agent Tool Schema & Reasoning Prompt ──────────────────────────────────────

AGENT_ORCHESTRATION_PROMPT = """<role>
You are ERHA Medical Assistant Tool Planner.
Your role is to evaluate complex medical queries from ERHA Doctors and determine which search tools to execute to gather complete clinical evidence.
</role>

<multi_concern_decomposition_rule>
CRITICAL: When the Doctor asks about MULTIPLE clinical concerns (e.g. Active Acne AND Post-Acne / Bekas Jerawat, or Treatment AND Facial Wash / Produk):
- Decompose the query and execute PARALLEL search actions for EVERY separate concern!
- Do NOT bundle them into a single vague query.
- Example: If asked for active acne + post-acne treatments & products:
  1. search_treatments("active acne papule inflammatory")
  2. search_treatments("bekas jerawat post-acne acne scar PIH")
  3. search_products("acne cleanser facial wash")
  4. search_products("bekas jerawat post-acne brightening spot serum")
</multi_concern_decomposition_rule>

<parallelism_guideline>
DEFAULT TO PARALLEL: Unless operations MUST be sequential, execute multiple tools simultaneously... parallel tool execution can be 3-5x faster.
When a question requires searching multiple topics, execute ALL necessary tool calls in a SINGLE turn.
MANDATORY: You MUST execute tool calls (search_treatments and/or search_products) on your very first turn using Action: tool_name or JSON format. DO NOT generate a direct conversational answer without calling tools!
</parallelism_guideline>

<conversation_history>
{history}
</conversation_history>"""

MEDICAL_AGENT_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": "Search ERHA product knowledge base for skincare product information, ingredients, usage, and recommendations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query for skincare products"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_treatments",
            "description": "Search ERHA clinical treatment/procedure database for in-clinic aesthetic procedures.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query for clinical treatments"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_contraindications",
            "description": "Search for safety information, contraindications, pregnancy/lactation warnings, allergies, and interactions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query for contraindications and clinical safety"
                    }
                },
                "required": ["query"]
            }
        }
    }
]


class MedicalAgent:
    """Medical Agent Tool Orchestrator for complex multi-step retrieval reasoning."""

    def __init__(
        self,
        retriever: HybridRetriever,
        llm_adapter: BaseLLMAdapter,
        max_iterations: int = 5,
    ):
        self.retriever = retriever
        self.llm_adapter = llm_adapter
        self.max_iterations = max_iterations
        self.tools_schema = MEDICAL_AGENT_TOOLS_SCHEMA

    def _search_knowledge_base(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Tool Execution: Performs Hybrid Retrieval (PGVector + BM25 + Reranker)."""
        try:
            result = self.retriever.retrieve(
                query=query,
                top_k=top_k,
                filter_metadata=filter_metadata,
                rerank=True,
                rerank_top_n=top_k,
            )
            hits = result.get("results", [])
            if not hits:
                return "No relevant information found in the knowledge base.", []

            formatted = []
            sources_list = []

            for i, hit in enumerate(hits[:top_k], 1):
                meta = hit.get("metadata", {})
                source = meta.get("source_file") or meta.get("filename") or "unknown_file"
                title = meta.get("title") or meta.get("product_name") or source
                page = meta.get("page") or 1
                section = meta.get("section") or "General"
                score = round(float(hit.get("score", 0.0)), 4)
                chunk_id = hit.get("chunk_id", f"chk_{i}")
                text = hit.get("text", "").strip()
                image_url = meta.get("image_url") or meta.get("image")
                img_tag = f" | Image: {image_url}" if image_url else ""
                doc_type = meta.get("document_type", "GENERAL")
                rel_prods = meta.get("related_products", [])
                rel_prods_str = f" | Related Products: {', '.join(rel_prods[:3])}" if rel_prods else ""

                formatted.append(
                    f"[{i}] Type: {doc_type} | Title: {title}{img_tag}{rel_prods_str} | Section: {section} | Source: {source}\n{text}"
                )
                sources_list.append({
                    "chunk_id": chunk_id,
                    "score": score,
                    "text": text[:300],
                    "metadata": meta
                })

            return "\n\n".join(formatted), sources_list

        except Exception as e:
            logger.error(f"❌ Agent _search_knowledge_base failed for query '{query}': {e}")
            return f"Search execution failed: {str(e)}", []

    def _search_products(self, query: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Tool: Search ERHA product knowledge base."""
        expanded_query = f"produk skincare cream serum gel lotion {query}"
        return self._search_knowledge_base(
            query=expanded_query,
            top_k=7,
            filter_metadata=None,
        )

    def _search_treatments(self, query: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Tool: Search ERHA clinical treatment/procedure database."""
        expanded_query = f"treatment tindakan prosedur terapi {query}"
        return self._search_knowledge_base(
            query=expanded_query,
            top_k=7,
            filter_metadata=None,
        )

    def _search_contraindications(self, query: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Tool: Search for safety information, contraindications, pregnancy/lactation warnings, allergies, and interactions."""
        expanded_safety_query = f"kontraindikasi ibu hamil menyusui alergi interaksi efek samping keamanan {query}"
        return self._search_knowledge_base(query=expanded_safety_query, top_k=7)

    def _build_tool_descriptions(self) -> str:
        return """Available tools:
1. search_products(query) - Search ERHA product knowledge base for skincare product information, ingredients, usage, and recommendations.
2. search_treatments(query) - Search ERHA clinical treatment/procedure database for in-clinic aesthetic procedures.
3. search_contraindications(query) - Search for safety information, contraindications, pregnancy/lactation warnings, allergies, and drug interactions.

PARALLEL TOOL CALLING INSTRUCTION:
DEFAULT TO PARALLEL: Unless operations MUST be sequential, execute multiple tools simultaneously... parallel tool execution can be 3-5x faster.
When a question requires gathering multiple pieces of evidence (e.g., comparing items, checking products + contraindications together), call ALL relevant tools in a SINGLE turn.

Format for single or multiple parallel tool calls:
Thought: [reasoning about what information is needed and why tools are executed in parallel]
Action: [tool_name_1]
Action Input: [query_1]
Action: [tool_name_2]
Action Input: [query_2]

Or JSON tool call format:
```json
[
  {"name": "tool_1", "arguments": {"query": "query_1"}},
  {"name": "tool_2", "arguments": {"query": "query_2"}}
]
```"""

    def _parse_agent_actions(self, response: str) -> List[Dict[str, str]]:
        """Parse all actions from agent response (supports ReAct format and JSON arrays)."""
        actions = []
        try:
            cleaned = response.strip()
            if "```json" in cleaned:
                blocks = cleaned.split("```json")
                for block in blocks[1:]:
                    json_str = block.split("```")[0].strip()
                    try:
                        data = json.loads(json_str)
                        if isinstance(data, list):
                            for item in data:
                                act = item.get("name") or item.get("action")
                                args = item.get("arguments") or item.get("parameters") or item.get("input")
                                inp = args.get("query") if isinstance(args, dict) else str(args or "")
                                if act and inp:
                                    actions.append({"action": str(act).strip(), "input": str(inp).strip()})
                        elif isinstance(data, dict):
                            act = data.get("name") or data.get("action")
                            args = data.get("arguments") or data.get("parameters") or data.get("input")
                            inp = args.get("query") if isinstance(args, dict) else str(args or "")
                            if act and inp:
                                actions.append({"action": str(act).strip(), "input": str(inp).strip()})
                    except Exception:
                        pass
            elif cleaned.startswith("[") and cleaned.endswith("]"):
                data = json.loads(cleaned)
                if isinstance(data, list):
                    for item in data:
                        act = item.get("name") or item.get("action")
                        args = item.get("arguments") or item.get("parameters") or item.get("input")
                        inp = args.get("query") if isinstance(args, dict) else str(args or "")
                        if act and inp:
                            actions.append({"action": str(act).strip(), "input": str(inp).strip()})
        except Exception:
            pass

        if actions:
            return actions

        lines = response.strip().split("\n")
        current_action = None
        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith("Action:"):
                current_action = line_stripped[len("Action:"):].strip()
            elif line_stripped.startswith("Action Input:") and current_action:
                action_input = line_stripped[len("Action Input:"):].strip()
                actions.append({"action": current_action, "input": action_input})
                current_action = None

        return actions

    def _execute_tool(self, action: str, action_input: str) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Execute a tool by name.
        FAIL CLOSED: Unknown tools return an explicit error observation instead of falling back to generic search.
        """
        tool_map = {
            "search_products": self._search_products,
            "search_treatments": self._search_treatments,
            "search_contraindications": self._search_contraindications,
        }

        tool_func = tool_map.get(action)
        if tool_func is None:
            logger.error(f"❌ [FAIL CLOSED] Unknown tool '{action}' requested by agent. Execution rejected.")
            return (
                f"Tool Execution Error: Tool '{action}' does not exist or is unauthorized. "
                f"Allowed tools: search_products, search_treatments, search_contraindications.",
                []
            )

        return tool_func(action_input)

    def _execute_tools_parallel(self, actions: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Execute multiple tool calls concurrently using ThreadPoolExecutor."""
        if not actions:
            return []

        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(actions), 5)) as executor:
            future_to_action = {
                executor.submit(self._execute_tool, act["action"], act["input"]): act
                for act in actions
            }
            for future in concurrent.futures.as_completed(future_to_action):
                act = future_to_action[future]
                try:
                    obs_str, sources = future.result()
                except Exception as exc:
                    logger.error(f"❌ Parallel tool {act['action']} execution error: {exc}")
                    obs_str = f"Search failed: {str(exc)}"
                    sources = []

                results.append({
                    "tool": act["action"],
                    "input": act["input"],
                    "observation": obs_str,
                    "sources": sources
                })

        return results

    def run_tool_orchestration(
        self,
        question: str,
        history: List[Dict[str, str]] = None,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Orchestrates tool searches for complex queries via parallel tool calls.
        Returns tuple of (combined_evidence_str, structured_sources_list).
        """
        if history is None:
            history = []

        history_str = ""
        if history:
            for msg in history:
                role = "User" if msg.get("role") == "user" else "Assistant"
                content = msg.get("content", "")
                history_str += f"{role}: {content}\n"

        system = AGENT_ORCHESTRATION_PROMPT.format(history=history_str)
        tool_descriptions = self._build_tool_descriptions()

        conversation = f"{system}\n\n{tool_descriptions}\n\nUser question: {question}\n\n"
        all_sources = []
        all_obs_blocks = []

        try:
            for iteration in range(self.max_iterations):
                response = self.llm_adapter.generate(conversation)
                conversation += response + "\n"

                parsed_actions = self._parse_agent_actions(response)
                if parsed_actions:
                    tools_display = ", ".join([f"{a['action']}('{a['input']}')" for a in parsed_actions])
                    logger.info(f"⚡ [AGENT TOOL ORCHESTRATION] Turn {iteration + 1}: Executing {len(parsed_actions)} tool(s) in parallel: {tools_display}")
                    parallel_results = self._execute_tools_parallel(parsed_actions)

                    obs_lines = []
                    for res in parallel_results:
                        all_sources.extend(res.get("sources", []))
                        obs_lines.append(f"Observation ({res['tool']} for '{res['input']}'):\n{res['observation']}")
                        all_obs_blocks.append(f"[{res['tool']}] {res['observation']}")

                    conversation += "\n\n".join(obs_lines) + "\n\n"
                else:
                    break

            combined_evidence = "\n\n".join(all_obs_blocks) if all_obs_blocks else "No specific evidence collected by agent tools."
            return combined_evidence, all_sources

        except Exception as e:
            logger.error(f"❌ Agent tool orchestration failed: {e}")
            return f"Agent tool orchestration failed: {str(e)}", []

    def run(
        self,
        question: str,
        history: List[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Backward-compatible caller interface: Delegates directly to the unified GenerationPipeline.
        """
        from app.rag.services.rag_generator import GenerationPipeline
        pipeline = GenerationPipeline(
            retriever=self.retriever,
            llm_adapter=self.llm_adapter,
            medical_agent=self
        )
        return pipeline.generate_answer(question, history=history or [], force_agent=True)
