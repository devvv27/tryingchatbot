import os
from dataclasses import dataclass


@dataclass
class Settings:
	groq_api_key: str = os.getenv("GROQ_API_KEY", "")
	groq_model: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
	gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
	gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")
	llm_provider: str = os.getenv("LLM_PROVIDER", "auto")

	sqlite_db_path: str = os.getenv("SQLITE_DB_PATH", "bookings.db")

	smtp_host: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
	smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
	smtp_user: str = os.getenv("SMTP_USER", "")
	smtp_password: str = os.getenv("SMTP_PASSWORD", "")
	smtp_from_email: str = os.getenv("SMTP_FROM_EMAIL", "")

	# Number of turns to preserve in short-term memory.
	short_term_memory_messages: int = int(os.getenv("SHORT_TERM_MEMORY_MESSAGES", "25"))


def get_settings() -> Settings:
	return Settings()
