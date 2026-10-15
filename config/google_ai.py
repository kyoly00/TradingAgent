"""Google AI 자연어 명령 변환 기능의 정적 설정과 환경 변수 로더."""

import os

from dotenv import load_dotenv


load_dotenv()

GOOGLE_AI_API_BASE_URL = os.getenv(
    "GOOGLE_AI_API_BASE_URL",
    "https://generativelanguage.googleapis.com/v1beta",
).rstrip("/")
GOOGLE_AI_MODEL = os.getenv("GOOGLE_AI_MODEL", "gemini-3.8-flash").strip()
GOOGLE_AI_TIMEOUT_SECONDS = 30.0
GOOGLE_AI_MAX_COMMANDS = 20
GOOGLE_AI_MAX_COMMAND_LENGTH = 160


def get_google_ai_api_key() -> str:
    """`.env`의 Google AI API 키를 공백 제거 후 반환합니다."""
    load_dotenv()
    return str(os.getenv("GOOGLE_AI_API_KEY") or "").strip()
