"""Google AI 자연어 명령 변환 설정."""

import os

from dotenv import load_dotenv


load_dotenv()

GOOGLE_AI_API_BASE_URL = os.getenv(
    "GOOGLE_AI_API_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta",
).rstrip("/")
GOOGLE_AI_MODEL = os.getenv("GOOGLE_AI_MODEL", "gemini-3.8-flash").strip()
GOOGLE_AI_TIMEOUT_SECONDS = 30
GOOGLE_AI_MAX_COMMANDS = 20
GOOGLE_AI_MAX_COMMAND_LENGTH = 160


def get_google_ai_api_key() -> str:
    """환경 변수에서 Google AI API 키를 가져옵니다."""
    return os.getenv("GOOGLE_AI_API_KEY", "").strip()
