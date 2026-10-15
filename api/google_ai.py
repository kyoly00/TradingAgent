"""Google AI를 이용해 자연어를 TradingAgent 명령어 배열로 변환합니다."""

import json
from typing import Any

from config.google_ai import (
    GOOGLE_AI_API_BASE_URL,
    GOOGLE_AI_MAX_COMMAND_LENGTH,
    GOOGLE_AI_MAX_COMMANDS,
    GOOGLE_AI_MODEL,
    GOOGLE_AI_TIMEOUT_SECONDS,
    get_google_ai_api_key,
)
from utils.logger import log_error

from .http_queue import http_client


SYSTEM_INSTRUCTION = """당신은 TradingAgent의 자연어 명령 변환기입니다.
제공된 command_guide.md에 실제로 정의된 명령만 생성하십시오.
응답은 설명, 마크다운, 코드 블록 없이 JSON 문자열 배열만 반환하십시오.
여러 단계가 필요하면 실행 순서대로 여러 문자열을 넣으십시오.
요청을 명령으로 안전하고 명확하게 변환할 수 없으면 빈 배열 []을 반환하십시오.
사용자가 말하지 않은 종목, 수량, 금액, 시간 또는 전략 값을 추측하지 마십시오.
대화 메모리와 로컬 종목 후보는 참고 정보이며, 현재 요청과 일치할 때만 사용하십시오.
`만원`은 10,000원 단위로 정확히 환산하십시오. 예: 145만원은 1450000원입니다.
특정 종목의 `전량` 매도는 `sell {종목코드} all` 또는 지정가가 있으면
`sell {종목코드} all {지정가}`라는 내부 중간 명령으로 반환하십시오.
수량이 없고 전량이라는 표현도 없으면 임의의 매도 수량을 만들지 말고 빈 배열을 반환하십시오.
"""


def _extract_candidate_text(payload: dict[str, Any]) -> str:
    candidates = payload.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise ValueError("Google AI 응답에 변환 결과가 없습니다.")

    content = candidates[0].get("content", {})
    parts = content.get("parts")
    if not isinstance(parts, list):
        raise ValueError("Google AI 응답 형식이 올바르지 않습니다.")

    texts = [part.get("text", "") for part in parts if isinstance(part, dict)]
    result = "".join(texts).strip()
    if not result:
        raise ValueError("Google AI가 빈 응답을 반환했습니다.")
    return result


def _parse_commands(candidate_text: str) -> list[str]:
    try:
        parsed = json.loads(candidate_text)
    except json.JSONDecodeError as exc:
        raise ValueError("Google AI 응답이 JSON 배열 형식이 아닙니다.") from exc

    if not isinstance(parsed, list):
        raise ValueError("Google AI 응답의 최상위 값은 배열이어야 합니다.")
    if len(parsed) > GOOGLE_AI_MAX_COMMANDS:
        raise ValueError("Google AI가 허용 개수보다 많은 명령을 반환했습니다.")

    commands: list[str] = []
    for item in parsed:
        if not isinstance(item, str):
            raise ValueError("Google AI 명령 배열에는 문자열만 포함할 수 있습니다.")
        command = item.strip()
        if not command:
            raise ValueError("Google AI 명령 배열에 빈 명령이 포함되어 있습니다.")
        if "\n" in command or "\r" in command:
            raise ValueError("각 명령은 한 줄이어야 합니다.")
        if len(command) > GOOGLE_AI_MAX_COMMAND_LENGTH:
            raise ValueError("Google AI가 너무 긴 명령을 반환했습니다.")
        commands.append(command)
    return commands


def convert_natural_language_to_commands(
    user_text: str,
    command_guide: str,
    conversation_context: str = "",
) -> dict[str, Any]:
    """자연어를 명령 문자열 배열로 변환하고 구조화된 결과를 반환합니다."""
    api_key = get_google_ai_api_key()
    if not api_key:
        return {
            "success": False,
            "commands": [],
            "error": "GOOGLE_AI_API_KEY 환경 변수가 설정되지 않았습니다.",
        }
    if not GOOGLE_AI_MODEL:
        return {
            "success": False,
            "commands": [],
            "error": "GOOGLE_AI_MODEL이 설정되지 않았습니다.",
        }

    url = f"{GOOGLE_AI_API_BASE_URL}/models/{GOOGLE_AI_MODEL}:generateContent"
    context_block = conversation_context.strip() or "사용 가능한 대화 메모리 없음"
    prompt = (
        "아래는 이 프로그램의 전체 명령어 가이드입니다.\n\n"
        "<command_guide>\n"
        f"{command_guide}\n"
        "</command_guide>\n\n"
        "<conversation_context>\n"
        f"{context_block}\n"
        "</conversation_context>\n\n"
        "다음 사용자 요청을 명령어 배열로 변환하십시오.\n"
        f"<user_request>{user_text}</user_request>"
    )
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0,
            "responseFormat": {
                "text": {
                    "mimeType": "APPLICATION_JSON",
                    "schema": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": GOOGLE_AI_MAX_COMMANDS,
                    },
                }
            },
        },
    }

    try:
        response = http_client.post(
            url,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            json=body,
            timeout=GOOGLE_AI_TIMEOUT_SECONDS,
        )
        if response.status_code != 200:
            try:
                error_payload = response.json()
                reason = error_payload.get("error", {}).get("message", "")
            except (ValueError, AttributeError):
                reason = ""
            detail = reason or f"HTTP {response.status_code}"
            raise RuntimeError(f"Google AI 요청 실패: {detail}")

        payload = response.json()
        commands = _parse_commands(_extract_candidate_text(payload))
        return {"success": True, "commands": commands, "error": ""}
    except Exception as exc:
        log_error(f"[자연어 명령 변환 실패] {exc}")
        return {"success": False, "commands": [], "error": str(exc)}
