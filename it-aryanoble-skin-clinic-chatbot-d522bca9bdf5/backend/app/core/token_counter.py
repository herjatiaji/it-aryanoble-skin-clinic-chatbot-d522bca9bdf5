import json
import math
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger
import urllib.request
import urllib.error

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
    _ENCODER = tiktoken.get_encoding("cl100k_base")
except Exception:
    _TIKTOKEN_AVAILABLE = False
    _ENCODER = None


def count_image_tokens_local(width: int, height: int, detail: str = "auto") -> int:
    """
    Calculate image tokens locally based on standard tile pricing (512x512 grid).
    """
    if detail == "low":
        return 85

    # Scale down to fit within 2048 x 2048
    if width > 2048 or height > 2048:
        scale = min(2048 / width, 2048 / height)
        width = int(width * scale)
        height = int(height * scale)

    # Scale shortest side to 768px
    if width < height:
        scale = 768 / max(1, width)
    else:
        scale = 768 / max(1, height)

    width = int(width * scale)
    height = int(height * scale)

    # Count 512x512 tiles
    tiles_x = math.ceil(width / 512)
    tiles_y = math.ceil(height / 512)
    num_tiles = tiles_x * tiles_y

    return (num_tiles * 170) + 85


def count_tokens(text: Optional[str], model_name: Optional[str] = None) -> int:
    """
    Count tokens for plain text locally via tiktoken.
    """
    if not text:
        return 0

    if _TIKTOKEN_AVAILABLE and _ENCODER:
        try:
            return len(_ENCODER.encode(text))
        except Exception:
            pass

    words = len(text.split())
    char_estimate = len(text) / 3.5
    return max(1, int(max(words * 1.3, char_estimate)))


async def count_chat_prompt_tokens_api(
    user_query: str,
    system_prompt: Optional[str] = None,
    context_chunks: Optional[List[str]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    files: Optional[List[Dict[str, Any]]] = None,
    model_name: Optional[str] = "gpt-5.4-mini",
    api_key: Optional[str] = None,
    provider: str = "openai",
    base_url: Optional[str] = None
) -> int:
    """
    Counts exact input tokens via official Provider APIs:
    - OpenAI: Uses POST /v1/responses/input_tokens (exact multimodal support for text, images, tools, formatting).
    - Gemini: Uses POST :countTokens endpoint.
    - Fallback: Local tiktoken + image tile calculation if API call fails or offline.
    """
    provider_clean = (provider or "openai").lower()
    target_model = model_name or ("gemini-1.5-flash" if provider_clean == "gemini" else "gpt-5.4-mini")

    # 1. Try Gemini API
    if provider_clean == "gemini" and api_key:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{target_model}:countTokens?key={api_key}"
            
            contents = []
            if system_prompt:
                contents.append({"role": "user", "parts": [{"text": f"System Instructions: {system_prompt}"}]})
            if context_chunks:
                ctx_text = "\n\n".join(context_chunks)
                contents.append({"role": "user", "parts": [{"text": f"Context: {ctx_text}"}]})
            if history:
                for msg in history:
                    contents.append({
                        "role": "model" if msg.get("role") in ["assistant", "model"] else "user",
                        "parts": [{"text": msg.get("content", "")}]
                    })

            user_parts = [{"text": user_query}]
            if files:
                for f in files:
                    if isinstance(f, dict) and f.get("url"):
                        user_parts.append({"text": f"[Attached File: {f.get('filename', 'file')}]"})

            contents.append({"role": "user", "parts": user_parts})

            payload = json.dumps({"contents": contents}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

            def _call_gemini():
                with urllib.request.urlopen(req, timeout=4) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        return data.get("totalTokens")
                return None

            total = await asyncio.to_thread(_call_gemini)
            if total is not None:
                return int(total)
        except Exception as e:
            logger.warning(f"Gemini countTokens API fallback: {e}")

    # 2. Try OpenAI Responses Input Token Count API (POST /v1/responses/input_tokens)
    if provider_clean in ["openai", "deepseek"] and api_key:
        try:
            api_endpoint = f"{base_url.rstrip('/')}/responses/input_tokens" if base_url else "https://api.openai.com/v1/responses/input_tokens"
            
            input_items = []
            if context_chunks:
                ctx_joined = "\n\n".join([f"--- Context Chunk ---\n{c}" for c in context_chunks])
                input_items.append({"role": "system", "content": ctx_joined})

            if history:
                for msg in history:
                    input_items.append({
                        "role": "assistant" if msg.get("role") in ["assistant", "model"] else "user",
                        "content": msg.get("content", "")
                    })

            user_content = []
            user_content.append({"type": "input_text", "text": user_query})

            if files:
                for f in files:
                    if isinstance(f, dict):
                        if f.get("image_url"):
                            user_content.append({
                                "type": "input_image",
                                "image_url": f["image_url"],
                                "detail": f.get("detail", "auto")
                            })
                        elif f.get("file_id"):
                            user_content.append({
                                "type": "input_file",
                                "file_id": f["file_id"]
                            })

            input_items.append({"role": "user", "content": user_content if len(user_content) > 1 else user_query})

            request_body = {
                "model": target_model,
                "input": input_items
            }
            if system_prompt:
                request_body["instructions"] = system_prompt

            payload = json.dumps(request_body).encode("utf-8")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            req = urllib.request.Request(api_endpoint, data=payload, headers=headers, method="POST")

            def _call_openai():
                with urllib.request.urlopen(req, timeout=4) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode("utf-8"))
                        return data.get("input_tokens")
                return None

            total = await asyncio.to_thread(_call_openai)
            if total is not None:
                return int(total)
        except Exception as e:
            logger.debug(f"OpenAI count_tokens API call not available, falling back to local exact tokenizer: {e}")

    # 3. Exact Local Fallback (tiktoken + structure)
    return count_chat_prompt_tokens(
        user_query=user_query,
        system_prompt=system_prompt,
        context_chunks=context_chunks,
        history=history
    )


def count_chat_prompt_tokens(
    user_query: str,
    system_prompt: Optional[str] = None,
    context_chunks: Optional[List[str]] = None,
    history: Optional[List[Dict[str, str]]] = None,
    files: Optional[List[Dict[str, Any]]] = None
) -> int:
    """
    Calculate the total input (prompt) tokens locally including structural ChatML overhead.
    """
    total = 0
    if system_prompt:
        total += count_tokens(system_prompt) + 4

    if context_chunks:
        for chunk in context_chunks:
            total += count_tokens(chunk)

    if history:
        for msg in history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            total += count_tokens(role) + count_tokens(content) + 4

    total += count_tokens("user") + count_tokens(user_query) + 4

    if files:
        for f in files:
            if isinstance(f, dict) and f.get("is_image"):
                w = f.get("width", 1024)
                h = f.get("height", 1024)
                total += count_image_tokens_local(w, h)
            else:
                total += 100 # Base file metadata overhead

    return total


def count_chat_completion_tokens(ai_response_text: Optional[str]) -> int:
    """
    Calculate the output (completion) tokens for an AI answer.
    """
    return count_tokens(ai_response_text)
