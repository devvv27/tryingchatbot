import os
from dataclasses import dataclass


def _get_setting(key: str, default: str = "") -> str:
	value = os.getenv(key)
	if value is not None and value != "":
		return value

	# Streamlit Cloud secrets fallback.
	try:
		import streamlit as st

		secret_value = st.secrets.get(key)
		if secret_value is None:
			return default
		return str(secret_value)
	except Exception:
		return default


@dataclass
class Settings:
	groq_api_key: str = _get_setting("GROQ_API_KEY", "")
	groq_model: str = _get_setting("GROQ_MODEL", "llama-3.1-8b-instant")
	gemini_api_key: str = _get_setting("GEMINI_API_KEY", "")
	gemini_model: str = _get_setting("GEMINI_MODEL", "gemini-1.5-flash")
	llm_provider: str = _get_setting("LLM_PROVIDER", "auto")

	sqlite_db_path: str = _get_setting("SQLITE_DB_PATH", "bookings.db")

	smtp_host: str = _get_setting("SMTP_HOST", "smtp.gmail.com")
	smtp_port: int = int(_get_setting("SMTP_PORT", "587"))
	smtp_user: str = _get_setting("SMTP_USER", "")
	smtp_password: str = _get_setting("SMTP_PASSWORD", "")
	smtp_from_email: str = _get_setting("SMTP_FROM_EMAIL", "")

	# Number of turns to preserve in short-term memory.
	short_term_memory_messages: int = int(_get_setting("SHORT_TERM_MEMORY_MESSAGES", "25"))


def get_settings() -> Settings:
	return Settings()
