from __future__ import annotations

from collections import OrderedDict
import hashlib
import os
from typing import Any
from urllib.parse import urljoin

import requests

from app.citation_engine import strict_not_found


SYSTEM_PROMPT = """
You are a grounded enterprise assistant. Rules: 1) Use ONLY the provided context. 2) If the context is insufficient, respond exactly with: NOT_FOUND 3) Do not invent facts. 4) After the answer, include a section titled 'Citations'. 5) Each citation line format: - "<direct quote>" | Source: <document name> | Location: <location> 6) Keep answers concise and avoid repeating long quotes in prose.
""".strip()

MAX_CONTEXT_CHUNKS = int(os.getenv("LLM_MAX_CONTEXT_CHUNKS", "3"))
MAX_QUOTE_CHARS = int(os.getenv("LLM_MAX_QUOTE_CHARS", "420"))
MAX_OUTPUT_TOKENS = int(os.getenv("LLM_MAX_OUTPUT_TOKENS", "280"))
LLM_CACHE_SIZE = int(os.getenv("LLM_CACHE_SIZE", "128"))
_LLM_RESPONSE_CACHE: OrderedDict[str, str] = OrderedDict()

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
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
    for idx, chunk in enumerate(chunks[:MAX_CONTEXT_CHUNKS], start=1):
        quote = (chunk.get("quote_text") or "").strip()
        if len(quote) > MAX_QUOTE_CHARS:
            quote = quote[:MAX_QUOTE_CHARS].rstrip() + "..."
        lines.append(
            f"[{idx}] Source: {chunk.get('document_name', 'Unknown')} | "
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
    _cache_set(key, text)
    return text
