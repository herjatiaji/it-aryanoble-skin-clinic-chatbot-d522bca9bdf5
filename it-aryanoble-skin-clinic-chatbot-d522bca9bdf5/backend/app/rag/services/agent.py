"""ReAct AI Agent for complex multi-step medical queries.

Inspired by Open-Brain's agent.py, adapted for ERHA medical domain.
Enabled via RAG_AGENT_ENABLED=true environment variable.

The agent can orchestrate multiple tool calls to answer complex queries
like: "Apa krim ERHA untuk acne dan apa kontraindikasinya untuk ibu hamil?"

Agent flow: Question → Reason → Tool Call → Observe → Reason → ... → Answer
"""

import json
from typing import Dict, Any, List, Optional
from loguru import logger

from app.rag.config import settings
from app.rag.services.interfaces import BaseLLMAdapter
from app.rag.services.rag_retriever import HybridRetriever


# ── Agent System Prompt ──────────────────────────────────────────────────────

AGENT_SYSTEM_PROMPT = """You are ERHA Assistant Agent, a grounded knowledge-base assistant.

You have access to tools to search the ERHA product knowledge base.

STRICT RULES:
1. Answer ONLY what the user asked. Be concise and direct.
2. Do not provide unsolicited product recommendations, treatment regimens, or clinical advice.
3. Do not add greetings such as 'Halo Dok', emojis, unnecessary bullet points, or disclaimers.
4. Never substitute one product name for another. Preserve exact product names from context.
5. If requested information is not available in the knowledge base, state so clearly. Do not speculate.
6. For simple factual questions, keep the final answer to 1-3 sentences maximum.

Conversation history:
{history}"""



class MedicalAgent:
    """ReAct agent with medical knowledge base tools for multi-step reasoning."""

    def __init__(
        self,
        retriever: HybridRetriever,
        llm_adapter: BaseLLMAdapter,
        max_iterations: int = 5,
    ):
        self.retriever = retriever
        self.llm_adapter = llm_adapter
        self.max_iterations = max_iterations

    def _search_knowledge_base(
        self,
        query: str,
        top_k: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Tool: Semantic + BM25 hybrid search over the ERHA knowledge base."""
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
                return "No relevant information found in the knowledge base."

            formatted = []
            for i, hit in enumerate(hits[:5], 1):
                meta = hit.get("metadata", {})
                source = meta.get("source_file", "unknown")
                section = meta.get("section", "General")
                text = hit.get("text", "")[:500]
                formatted.append(
                    f"[{i}] Source: {source} | Section: {section}\n{text}"
                )
            return "\n\n".join(formatted)
        except Exception as e:
            logger.error(f"Agent tool search_knowledge_base failed: {e}")
            return f"Search failed: {str(e)}"

    def _search_products(self, query: str) -> str:
        """Tool: Search ERHA product knowledge base for skincare recommendations."""
        return self._search_knowledge_base(
            query=query,
            top_k=5,
            filter_metadata={"type": "product"},
        )

    def _search_treatments(self, query: str) -> str:
        """Tool: Search ERHA treatment/procedure database."""
        return self._search_knowledge_base(
            query=query,
            top_k=5,
            filter_metadata={"type": "treatment"},
        )

    def _search_contraindications(self, query: str) -> str:
        """Tool: Search for safety information, contraindications, and side effects."""
        safety_query = f"kontraindikasi efek samping keamanan {query}"
        return self._search_knowledge_base(query=safety_query, top_k=5)

    def _build_tool_descriptions(self) -> str:
        """Build tool descriptions for the ReAct prompt."""
        return """Available tools:
1. search_products(query) - Search ERHA product knowledge base for skincare product information, ingredients, usage, and recommendations.
2. search_treatments(query) - Search ERHA clinical treatment/procedure database for in-clinic aesthetic procedures.
3. search_contraindications(query) - Search for safety information, contraindications, side effects, and pregnancy/lactation warnings.

To use a tool, respond with:
Thought: [your reasoning about what to do next]
Action: [tool_name]
Action Input: [the search query]

After receiving the observation, continue reasoning:
Thought: [reflect on the observation]
... (repeat as needed)

When you have enough information, respond with:
Thought: I now have enough information to answer.
Final Answer: [your comprehensive response in markdown format]"""

    def _parse_agent_action(self, response: str) -> Optional[Dict[str, str]]:
        """Parse an action from the agent's response."""
        lines = response.strip().split("\n")
        action = None
        action_input = None

        for line in lines:
            line_stripped = line.strip()
            if line_stripped.startswith("Action:"):
                action = line_stripped[len("Action:"):].strip()
            elif line_stripped.startswith("Action Input:"):
                action_input = line_stripped[len("Action Input:"):].strip()

        if action and action_input:
            return {"action": action, "input": action_input}
        return None

    def _execute_tool(self, action: str, action_input: str) -> str:
        """Execute a tool by name."""
        tool_map = {
            "search_products": self._search_products,
            "search_treatments": self._search_treatments,
            "search_contraindications": self._search_contraindications,
        }

        tool_func = tool_map.get(action)
        if tool_func is None:
            # Fallback: try general search
            logger.warning(f"Unknown tool '{action}', falling back to general search.")
            return self._search_knowledge_base(action_input)

        return tool_func(action_input)

    def run(
        self,
        question: str,
        history: List[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Run the ReAct agent loop.
        Returns dict with 'answer', 'sources', and 'agent' flag.
        Falls back to None if agent fails (caller should use standard pipeline).
        """
        if history is None:
            history = []

        history_str = ""
        if history:
            for msg in history:
                role = "User" if msg.get("role") == "user" else "Assistant"
                content = msg.get("content", "")
                history_str += f"{role}: {content}\n"
        else:
            history_str = "(no previous conversation)\n"

        system = AGENT_SYSTEM_PROMPT.format(history=history_str)
        tool_descriptions = self._build_tool_descriptions()

        # Build initial prompt
        conversation = f"{system}\n\n{tool_descriptions}\n\nUser question: {question}\n\n"
        all_observations = []

        try:
            for iteration in range(self.max_iterations):
                logger.info(f"Agent iteration {iteration + 1}/{self.max_iterations}")

                # Generate agent response
                response = self.llm_adapter.generate(conversation)
                conversation += response + "\n"

                # Check for final answer
                if "Final Answer:" in response:
                    final_answer_start = response.index("Final Answer:") + len("Final Answer:")
                    answer = response[final_answer_start:].strip()
                    logger.info(f"Agent completed in {iteration + 1} iterations.")
                    return {
                        "answer": answer,
                        "sources": all_observations,
                        "agent": True,
                        "iterations": iteration + 1,
                    }

                # Parse and execute action
                parsed = self._parse_agent_action(response)
                if parsed:
                    action = parsed["action"]
                    action_input = parsed["input"]
                    logger.info(f"Agent tool call: {action}({action_input})")

                    observation = self._execute_tool(action, action_input)
                    all_observations.append({
                        "tool": action,
                        "input": action_input,
                        "output_preview": observation[:200],
                    })

                    conversation += f"Observation: {observation}\n\n"
                else:
                    # No action parsed and no final answer — force completion
                    logger.warning("Agent produced no action or final answer. Forcing completion.")
                    conversation += (
                        "You did not use a tool or provide a Final Answer. "
                        "Please provide your Final Answer now based on what you know.\n\n"
                    )

            # Max iterations reached — extract whatever we have
            logger.warning(f"Agent reached max iterations ({self.max_iterations}).")
            final_prompt = conversation + (
                "\nYou have reached the maximum number of reasoning steps. "
                "Please provide your Final Answer now based on the observations collected.\n\n"
                "Final Answer:"
            )
            final_response = self.llm_adapter.generate(final_prompt)
            return {
                "answer": final_response.strip(),
                "sources": all_observations,
                "agent": True,
                "iterations": self.max_iterations,
            }

        except Exception as e:
            logger.error(f"Agent execution failed: {e}")
            return None
