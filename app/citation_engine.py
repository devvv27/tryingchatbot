from __future__ import annotations

from typing import Any


def citation_item(chunk: dict[str, Any]) -> dict[str, str]:
    return {
        "quote": chunk["quote_text"],
        "source": chunk["document_name"],
        "location": chunk["location_value"],
        "location_type": chunk["location_type"],
    }


def build_context_for_llm(chunks: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        lines.append(
            f"[{idx}] Source: {chunk['document_name']} | Location: {chunk['location_value']}\n"
            f"Quote: {chunk['quote_text']}"
        )
    return "\n\n".join(lines)


def strict_not_found() -> str:
    return (
        "I could not find the answer in the selected resources.\n\n"
        "Citations: None"
    )
