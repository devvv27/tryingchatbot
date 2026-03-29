import streamlit as st

from config.config import get_settings
from db.database import init_db
from models.embeddings import LightweightRAGStore
from models.llm import get_chat_model
from utils.admin_dashboard import render_admin_dashboard
from utils.booking_flow import BookingState
from utils.chat_logic import handle_user_message, trim_memory


def _init_session_state() -> None:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "booking_state" not in st.session_state:
        st.session_state.booking_state = BookingState()
    if "rag_store" not in st.session_state:
        st.session_state.rag_store = LightweightRAGStore()
    if "status_log" not in st.session_state:
        st.session_state.status_log = []


def _instructions_page() -> None:
    settings = get_settings()
    st.title("AI Booking Assistant")
    st.markdown(
        """
This app implements:
- Chat-based RAG over user-uploaded PDFs
- Booking intent detection and slot-filling flow
- Explicit confirmation before DB save
- SQLite persistence
- Email confirmation after booking
- Mandatory admin dashboard for viewing bookings
        """
    )

    st.subheader("Environment Variables")
    st.code(
        "\n".join(
            [
                "LLM_PROVIDER=auto",
                "GEMINI_API_KEY=...",
                f"GEMINI_MODEL={settings.gemini_model}",
                "GROQ_API_KEY=...",
                f"GROQ_MODEL={settings.groq_model}",
                f"SQLITE_DB_PATH={settings.sqlite_db_path}",
                "SMTP_HOST=smtp.gmail.com",
                "SMTP_PORT=587",
                "SMTP_USER=...",
                "SMTP_PASSWORD=...",
                "SMTP_FROM_EMAIL=...",
            ]
        ),
        language="bash",
    )

    st.info("Date format: YYYY-MM-DD | Time format: HH:MM (24-hour).")


def _chat_page(llm) -> None:
    st.title("Booking Chat")

    uploads = st.file_uploader(
        "Upload one or more PDFs for RAG",
        type=["pdf"],
        accept_multiple_files=True,
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Process PDFs", use_container_width=True):
            if not uploads:
                st.error("Please upload at least one valid PDF.")
            else:
                try:
                    chunks = st.session_state.rag_store.build_from_pdf_files(uploads)
                    st.success(f"Processed PDFs successfully. Created {chunks} chunks.")
                except Exception as exc:
                    st.error(f"Invalid/missing PDFs or extraction error: {exc}")
    with col2:
        if st.button("Clear Chat History", use_container_width=True):
            st.session_state.messages = []
            st.session_state.booking_state = BookingState()
            st.session_state.status_log = []
            st.rerun()

    st.divider()

    if st.session_state.rag_store.is_ready:
        st.caption(f"RAG ready: {st.session_state.rag_store.chunk_count} chunks indexed.")
    else:
        st.caption("RAG not ready yet. Upload PDFs and click 'Process PDFs'.")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Ask a question or start a booking request"):
        st.session_state.messages.append({"role": "user", "content": prompt})

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                response, updated_state, statuses = handle_user_message(
                    user_text=prompt,
                    booking_state=st.session_state.booking_state,
                    rag_store=st.session_state.rag_store,
                    llm=llm,
                )
            st.markdown(response)

        st.session_state.booking_state = updated_state
        st.session_state.messages.append({"role": "assistant", "content": response})
        st.session_state.messages = trim_memory(st.session_state.messages)
        st.session_state.status_log.extend(statuses)

    if st.session_state.status_log:
        st.subheader("Status Messages")
        for line in st.session_state.status_log[-8:]:
            st.write(f"- {line}")


def main() -> None:
    st.set_page_config(page_title="AI Booking Assistant", page_icon="🧾", layout="wide")

    _init_session_state()
    init_db()

    llm = None
    llm_error = None
    try:
        llm = get_chat_model()
    except Exception as exc:
        llm_error = str(exc)

    with st.sidebar:
        st.title("Navigation")
        page = st.radio("Go to", ["Chat", "Admin Dashboard", "Instructions"], index=0)

    if llm is None and page != "Instructions":
        st.error(f"Model setup error: {llm_error}")
        st.info("Set GEMINI_API_KEY or GROQ_API_KEY, then reload the app.")
        return

    if page == "Chat":
        _chat_page(llm)
    elif page == "Admin Dashboard":
        st.title("Bookings")
        render_admin_dashboard()
    else:
        _instructions_page()


if __name__ == "__main__":
    main()