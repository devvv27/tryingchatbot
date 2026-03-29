from __future__ import annotations

from typing import Dict, List, Tuple

from config.config import get_settings
from utils.booking_flow import (
    BookingState,
    booking_summary,
    detect_booking_intent,
    extract_details,
    missing_fields,
    prompt_for_field,
    validate_fields,
)
from utils.tools import booking_persistence_tool, email_tool, rag_tool


def trim_memory(messages: List[Dict]) -> List[Dict]:
    settings = get_settings()
    max_messages = settings.short_term_memory_messages
    return messages[-max_messages:]


def _compose_email_body(fields: Dict[str, str], booking_id: int) -> str:
    return (
        "Your booking is confirmed.\n\n"
        f"Name: {fields['name']}\n"
        f"Booking ID: {booking_id}\n"
        f"Date: {fields['booking_date']}\n"
        f"Time: {fields['booking_time']}\n"
        f"Booking type: {fields['booking_type']}\n"
        f"Phone: {fields['phone']}\n"
    )


def handle_user_message(
    user_text: str,
    booking_state: BookingState,
    rag_store,
    llm,
) -> Tuple[str, BookingState, List[str]]:
    statuses: List[str] = []

    extracted = extract_details(user_text)
    booking_state.fields.update(extracted)

    if booking_state.awaiting_confirmation:
        answer = user_text.strip().lower()
        if answer in {"confirm", "yes", "y"}:
            validation_error = validate_fields(booking_state.fields)
            if validation_error:
                return validation_error, booking_state, statuses

            try:
                save_result = booking_persistence_tool(booking_state.fields)
                booking_id = save_result["booking_id"]
                statuses.append(f"DB saved with booking ID {booking_id}.")
            except Exception as exc:
                return f"Could not save booking due to a database error: {exc}", booking_state, statuses

            email_result = email_tool(
                to_email=booking_state.fields["email"],
                subject=f"Booking Confirmation #{booking_id}",
                body=_compose_email_body(booking_state.fields, booking_id),
            )
            if email_result.get("success"):
                statuses.append("Confirmation email sent.")
                reply = f"Booking confirmed and saved. Your booking ID is {booking_id}."
            else:
                statuses.append("Email could not be sent.")
                reply = (
                    f"Booking saved with ID {booking_id}. "
                    "Email could not be sent, but booking was saved."
                )

            return reply, BookingState(), statuses

        if answer in {"edit", "no", "n"}:
            booking_state.awaiting_confirmation = False
            missing = missing_fields(booking_state.fields)
            if missing:
                return prompt_for_field(missing[0]), booking_state, statuses
            return "Please share what you want to change in the booking details.", booking_state, statuses

        return "Please reply with 'confirm' to save or 'edit' to change details.", booking_state, statuses

    if booking_state.is_booking_mode or detect_booking_intent(user_text):
        booking_state.is_booking_mode = True

        validation_error = validate_fields(booking_state.fields)
        if validation_error:
            return validation_error, booking_state, statuses

        missing = missing_fields(booking_state.fields)
        if missing:
            return prompt_for_field(missing[0]), booking_state, statuses

        booking_state.awaiting_confirmation = True
        return booking_summary(booking_state.fields), booking_state, statuses

    # General non-booking query: answer via RAG when PDFs are present, else LLM fallback.
    if rag_store and rag_store.is_ready:
        try:
            return rag_tool(user_text, rag_store, llm), booking_state, statuses
        except Exception as exc:
            return f"RAG error while answering from PDFs: {exc}", booking_state, statuses

    try:
        response = llm.invoke(user_text)
        return response.content if hasattr(response, "content") else str(response), booking_state, statuses
    except Exception as exc:
        return f"Runtime error while generating response: {exc}", booking_state, statuses
