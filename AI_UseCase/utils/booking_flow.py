from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional

REQUIRED_FIELDS = [
    "name",
    "email",
    "phone",
    "booking_type",
    "booking_date",
    "booking_time",
]


@dataclass
class BookingState:
    is_booking_mode: bool = False
    awaiting_confirmation: bool = False
    fields: Dict[str, str] = field(default_factory=dict)


def detect_booking_intent(user_text: str) -> bool:
    text = user_text.lower()
    keywords = ["book", "booking", "appointment", "reserve", "schedule"]
    return any(k in text for k in keywords)


def extract_details(text: str) -> Dict[str, str]:
    extracted: Dict[str, str] = {}

    email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    if email_match:
        extracted["email"] = email_match.group(0)

    phone_match = re.search(r"(?:\+\d{1,3}[\s-]?)?(?:\d[\s-]?){10,15}", text)
    if phone_match:
        extracted["phone"] = re.sub(r"\s+", "", phone_match.group(0))

    date_match = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    if date_match:
        extracted["booking_date"] = date_match.group(0)

    time_match = re.search(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", text)
    if time_match:
        extracted["booking_time"] = time_match.group(0)

    # Heuristic extraction for common fields in free text.
    lower = text.lower()
    if "name is" in lower:
        name = text[lower.index("name is") + len("name is"):].strip().split(",")[0]
        if name:
            extracted["name"] = name.strip().title()

    if "for" in lower and "booking" in lower:
        part = text[lower.index("for") + 3:].strip().split(",")[0]
        if part and len(part.split()) <= 4:
            extracted["booking_type"] = part.strip()

    return extracted


def validate_fields(fields: Dict[str, str]) -> Optional[str]:
    email = fields.get("email", "")
    if email and not re.fullmatch(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", email):
        return "Please provide a valid email address."

    date_str = fields.get("booking_date", "")
    if date_str:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            return "Please enter date as YYYY-MM-DD."

    time_str = fields.get("booking_time", "")
    if time_str:
        if not re.fullmatch(r"(?:[01]?\d|2[0-3]):[0-5]\d", time_str):
            return "Please enter time as HH:MM in 24-hour format."

    return None


def missing_fields(fields: Dict[str, str]):
    return [f for f in REQUIRED_FIELDS if not fields.get(f)]


def booking_summary(fields: Dict[str, str]) -> str:
    return (
        "Please confirm these booking details:\n"
        f"- Name: {fields.get('name', '')}\n"
        f"- Email: {fields.get('email', '')}\n"
        f"- Phone: {fields.get('phone', '')}\n"
        f"- Booking type: {fields.get('booking_type', '')}\n"
        f"- Date: {fields.get('booking_date', '')}\n"
        f"- Time: {fields.get('booking_time', '')}\n\n"
        "Reply with 'confirm' to save or 'edit' to update details."
    )


def prompt_for_field(field_name: str) -> str:
    prompts = {
        "name": "Please share customer name.",
        "email": "Please share email address.",
        "phone": "Please share phone number.",
        "booking_type": "What booking/service type do you want?",
        "booking_date": "Please share preferred date in YYYY-MM-DD format.",
        "booking_time": "Please share preferred time in HH:MM (24-hour) format.",
    }
    return prompts[field_name]
