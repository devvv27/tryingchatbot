from __future__ import annotations

import smtplib
from email.mime.text import MIMEText
from typing import Dict

import requests

from config.config import get_settings
from db.database import create_booking
from db.models import BookingPayload


def rag_tool(query: str, rag_store, llm) -> str:
    """Input: query -> Output: retrieved answer."""
    if not getattr(rag_store, "is_ready", False):
        return "Please upload PDF files and click 'Process PDFs' before asking document questions."

    results = rag_store.retrieve(query, k=4)
    if not results:
        return (
            "I could not find specific details in the uploaded PDFs. "
            "Try asking a more focused question or re-process the PDFs."
        )

    context = "\n\n".join([f"Chunk {idx + 1}: {r.chunk}" for idx, r in enumerate(results)])
    prompt = (
        "You are a booking assistant answering with context from uploaded PDFs. "
        "If context is insufficient, say so briefly.\n\n"
        f"Question: {query}\n\n"
        f"Context:\n{context}"
    )
    try:
        response = llm.invoke(prompt)
        return response.content if hasattr(response, "content") else str(response)
    except Exception:
        # If model call fails, still return retrieved context so user gets useful output.
        return "\n\n".join([f"- {r.chunk[:320]}" for r in results])


def booking_persistence_tool(payload: Dict) -> Dict:
    """Input: structured booking payload -> Output: success + booking ID."""
    booking_id = create_booking(
        BookingPayload(
            name=payload["name"],
            email=payload["email"],
            phone=payload["phone"],
            booking_type=payload["booking_type"],
            booking_date=payload["booking_date"],
            booking_time=payload["booking_time"],
            status="confirmed",
        )
    )
    return {"success": True, "booking_id": booking_id}


def email_tool(to_email: str, subject: str, body: str) -> Dict:
    """Input: to_email/subject/body -> Output: success/failure."""
    settings = get_settings()

    if not settings.smtp_user or not settings.smtp_password or not settings.smtp_from_email:
        return {
            "success": False,
            "error": "SMTP credentials are not configured. Booking can still be saved.",
        }

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = settings.smtp_from_email
        msg["To"] = to_email

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_password)
            server.sendmail(settings.smtp_from_email, [to_email], msg.as_string())

        return {"success": True}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


def web_search_tool(query: str) -> Dict:
    """Optional web search tool using a third-party JSON API."""
    try:
        response = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1},
            timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        text = data.get("AbstractText") or ""
        heading = data.get("Heading") or ""
        related = data.get("RelatedTopics") or []

        if text:
            return {"success": True, "result": f"{heading}: {text}".strip(": ")}

        for item in related:
            if isinstance(item, dict) and item.get("Text"):
                return {"success": True, "result": item["Text"]}

        return {"success": True, "result": "No concise web result found."}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
