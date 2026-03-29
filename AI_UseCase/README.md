# AI Booking Assistant

This project implements the assignment requirements for a chat-based AI Booking Assistant with:
- RAG over user-uploaded PDFs
- Booking intent detection and multi-turn slot collection
- Explicit confirmation before saving data
- SQLite persistence with required schema
- Confirmation email sending via SMTP
- Mandatory Admin Dashboard for stored bookings
- Short-term memory for conversation continuity
- Friendly error handling

## Project Structure

- `app.py`: Streamlit entry point
- `config/config.py`: Environment-backed settings
- `models/llm.py`: Groq model setup
- `models/embeddings.py`: PDF extraction, chunking, TF-IDF embedding + retrieval
- `utils/chat_logic.py`: Intent routing, booking flow, and tool orchestration
- `utils/booking_flow.py`: Field extraction, validation, confirmation logic
- `utils/tools.py`: RAG tool, booking persistence tool, email tool, optional web search tool
- `utils/admin_dashboard.py`: Admin dashboard UI
- `db/database.py`: SQLite schema + CRUD
- `db/models.py`: Booking payload model

## Setup

Install dependencies:

```bash
pip install -r requirements.txt
```

Set environment variables:

```bash
GROQ_API_KEY=your_key
GROQ_MODEL=llama-3.1-8b-instant
SQLITE_DB_PATH=bookings.db
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your_email
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=your_email
```

## Run

```bash
streamlit run app.py
```

## Booking Flow Implemented

1. Detect booking intent.
2. Extract known details from messages.
3. Ask only missing fields.
4. Maintain short-term memory (last 25 messages by default).
5. Summarize details.
6. Ask explicit confirmation.
7. On confirmation: save to DB and send email.
8. Respond with booking ID.
9. Keep conversation history in session state.

## Notes

- Date format expected: `YYYY-MM-DD`
- Time format expected: `HH:MM` (24-hour)
- If email fails, booking is still saved and user receives a friendly message.
- SQLite is used as lightweight persistence for assignment scope.
