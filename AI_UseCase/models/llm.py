from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq

from config.config import get_settings


def get_chat_model():
    """Initialize and return the configured chat model.

    Selection rules:
    - LLM_PROVIDER=gemini -> Gemini
    - LLM_PROVIDER=groq -> Groq
    - LLM_PROVIDER=auto (default) -> Gemini if key present, else Groq
    """
    settings = get_settings()
    provider = (settings.llm_provider or "auto").strip().lower()

    if provider == "gemini" or (provider == "auto" and settings.gemini_api_key):
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is missing. Please set it in environment variables.")
        try:
            return ChatGoogleGenerativeAI(
                model=settings.gemini_model,
                google_api_key=settings.gemini_api_key,
                temperature=0,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize Gemini model: {exc}") from exc

    if provider in {"groq", "auto"}:
        if not settings.groq_api_key:
            raise RuntimeError(
                "No supported key found. Set GEMINI_API_KEY or GROQ_API_KEY in environment variables."
            )
        try:
            return ChatGroq(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                temperature=0,
            )
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize Groq model: {exc}") from exc

    raise RuntimeError("Invalid LLM_PROVIDER. Use auto, gemini, or groq.")