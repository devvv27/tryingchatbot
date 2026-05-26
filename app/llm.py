from __future__ import annotations

from collections import OrderedDict
import hashlib
import os
from typing import Any
from urllib.parse import urljoin
import re

import requests

from app.citation_engine import strict_not_found


SYSTEM_PROMPT = """
You are a grounded enterprise assistant. Rules: 1) Use ONLY the provided context. 2) If the context is insufficient, respond exactly with: NOT_FOUND 3) Do not invent facts. 4) After the answer, include a section titled 'Citations'. 5) Each citation line format: - "<direct quote>" | Source: <document name> | Location: <location> 6) Always reference the human-readable `Location` provided in the context (e.g., "Page 2", "Section: Introduction", "Tab: Sheet1, Row: 4"). NEVER reference or emit bracketed chunk indexes like "[1]", "[2]", or similar. 7) Prefer `Page N` when available for PDF sources. 8) Keep answers concise and avoid repeating long quotes in prose.
""".strip()

MAX_CONTEXT_CHUNKS = int(os.getenv("LLM_MAX_CONTEXT_CHUNKS", "3"))
MAX_QUOTE_CHARS = int(os.getenv("LLM_MAX_QUOTE_CHARS", "420"))
MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "280"))
LLM_CACHE_SIZE = int(os.getenv("LLM_CACHE_SIZE", "128"))
_LLM_RESPONSE_CACHE: OrderedDict[str, str] = OrderedDict()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")
OLLAMA_TIMEOUT_SECONDS = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "60"))


def set_ollama_model(model_name: str) -> None:
    global OLLAMA_MODEL
    OLLAMA_MODEL = model_name.strip() or OLLAMA_MODEL


def has_ollama_connection() -> bool:
    try:
        response = requests.get(urljoin(OLLAMA_BASE_URL.rstrip("/") + "/", "api/tags"), timeout=5)
        return response.ok
    except requests.RequestException:
        return False


def _ollama_chat_endpoint() -> str:
    return urljoin(OLLAMA_BASE_URL.rstrip("/") + "/", "api/chat")


def _compact_context(chunks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    # Provide context to the model without numeric chunk indexes. The model
    # should see only human-readable locations (Page/Section/Tab:Row) and the
    # quoted text; this reduces the chance it cites chunk numbers instead of
    # real locations.
    for chunk in chunks[:MAX_CONTEXT_CHUNKS]:
        quote = (chunk.get("quote_text") or "").strip()
        if len(quote) > MAX_QUOTE_CHARS:
            quote = quote[:MAX_QUOTE_CHARS].rstrip() + "..."
        lines.append(
            f"Source: {chunk.get('document_name', 'Unknown')} | "
            f"Location: {chunk.get('location_value', 'N/A')}\n"
            f"Quote: {quote}"
        )
    return "\n\n".join(lines)


def _cache_key(question: str, chunks: list[dict[str, Any]]) -> str:
    key_parts = [question.strip().lower()]
    for chunk in chunks[:MAX_CONTEXT_CHUNKS]:
        key_parts.append(str(chunk.get("id", "")))
        key_parts.append(str(chunk.get("location_value", "")))
    return hashlib.sha1("|".join(key_parts).encode("utf-8")).hexdigest()


def _cache_get(key: str) -> str | None:
    value = _LLM_RESPONSE_CACHE.get(key)
    if value is None:
        return None
    _LLM_RESPONSE_CACHE.move_to_end(key)
    return value


def _cache_set(key: str, value: str) -> None:
    _LLM_RESPONSE_CACHE[key] = value
    _LLM_RESPONSE_CACHE.move_to_end(key)
    while len(_LLM_RESPONSE_CACHE) > LLM_CACHE_SIZE:
        _LLM_RESPONSE_CACHE.popitem(last=False)


def generate_answer(question: str, context_text: str, chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return strict_not_found()

    if not has_ollama_connection():
        return f"Ollama is not reachable at {OLLAMA_BASE_URL}. Start Ollama locally and try again."

    key = _cache_key(question, chunks)
    cached = _cache_get(key)
    if cached is not None:
        return cached

    compact_context = context_text.strip() or _compact_context(chunks)

    user_prompt = (
        f"Question:\n{question}\n\n"
        f"Context:\n{compact_context}\n\n"
        "Provide a concise grounded answer and citations."
    )

    endpoint = _ollama_chat_endpoint()
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.1,
        "stream": False,
        "options": {
            "num_predict": MAX_OUTPUT_TOKENS,
            "temperature": 0.1,
        },
    }
    try:
        response = requests.post(
            endpoint,
            json=payload,
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        if not response.ok:
            return f"Ollama request failed: {response.status_code} {response.text}"
        response.raise_for_status()
        body = response.json()
        text = body.get("message", {}).get("content", "").strip()
    except Exception as exc:
        return f"Ollama request failed: {exc}"

    if not text:
        return strict_not_found()
    if text.strip() == "NOT_FOUND":
        return strict_not_found()
    # Post-process model citations: the model sometimes references the
    # context chunk index (e.g. "Location: [5]") instead of the human
    # readable location (e.g. "Page 2"). Replace occurrences like
    # "Location: [N]" with the corresponding `location_value` from the
    # provided `chunks` list so UI shows correct page/section information.
    def _replace_location(match: re.Match) -> str:
        try:
            idx = int(match.group(1))
            if 1 <= idx <= len(chunks):
                return f"Location: {chunks[idx - 1].get('location_value', 'N/A')}"
        except Exception:
            pass
        return match.group(0)

    processed = re.sub(r"Location:\s*\[(\d+)\]", _replace_location, text)

    # Also replace occurrences where the model may have used a bracketed
    # reference directly after a source, e.g. "| [5]" -> "| Location: <...>"
    def _replace_pipe_bracket(match: re.Match) -> str:
        try:
            idx = int(match.group(1))
            if 1 <= idx <= len(chunks):
                return f"| Location: {chunks[idx - 1].get('location_value', 'N/A')}"
        except Exception:
            pass
        return match.group(0)

    processed = re.sub(r"\|\s*\[(\d+)\]", _replace_pipe_bracket, processed)

    _cache_set(key, processed)
    return processed
