"""Google Gemini REST API를 이용한 자연어 명령 변환 모듈."""

import json
from urllib.parse import quote

from api.http_queue import http_client
from config.google_ai import (
    GOOGLE_AI_API_BASE_URL,
    GOOGLE_AI_MAX_COMMAND_LENGTH,
    GOOGLE_AI_MAX_COMMANDS,
    GOOGLE_AI_MODEL,
    GOOGLE_AI_TIMEOUT_SECONDS,
    get_google_ai_api_key,
)
from utils.logger import log_error


_SYSTEM_INSTRUCTION = """당신은 TradingAgent 전용 명령 변환기다.
사용자의 자연어 요청을 제공된 command_guide.md에 실제로 존재하는 텔레그램 명령어로만 변환하라.
반드시 실행 순서대로 정렬된 JSON 문자열 배열만 반환하라.
설명, 마크다운, 코드 블록, 확인 질문은 반환하지 마라.
요청을 안전하고 확실하게 변환할 수 없거나 필수 인수가 부족하거나 지원 명령이 없으면 빈 배열 []을 반환하라.
종목명으로 종목코드를 추측하거나, 수량·금액·시간·투자 모드를 임의로 보충하지 마라.
여러 명령이 필요할 때만 배열에 여러 항목을 넣어라."""


def _extract_candidate_text(data: object) -> str:
    """Gemini generateContent 응답에서 첫 후보의 텍스트 부분을 결합합니다."""
    if not isinstance(data, dict):
        return ""
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        return ""
    first_candidate = candidates[0]
    if not isinstance(first_candidate, dict):
        return ""
    content = first_candidate.get("content")
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    return "".join(
        str(part.get("text") or "")
        for part in parts
        if isinstance(part, dict)
    ).strip()


def _normalize_command_array(value: object) -> list[str]:
    """AI 응답을 비어 있지 않은 단일 행 명령 문자열 배열로 검증합니다."""
    if not isinstance(value, list):
        raise ValueError("응답 최상위 값이 배열이 아닙니다.")
    if len(value) > GOOGLE_AI_MAX_COMMANDS:
        raise ValueError(
            f"한 번에 변환할 수 있는 명령은 최대 {GOOGLE_AI_MAX_COMMANDS}개입니다."
        )

    commands = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError("배열에 문자열이 아닌 항목이 포함되어 있습니다.")
        command = item.strip()
        if not command:
            raise ValueError("빈 명령 문자열이 포함되어 있습니다.")
        if "\n" in command or "\r" in command:
            raise ValueError("명령은 각각 한 줄이어야 합니다.")
        if len(command) > GOOGLE_AI_MAX_COMMAND_LENGTH:
            raise ValueError(
                "개별 명령 길이는 "
                f"{GOOGLE_AI_MAX_COMMAND_LENGTH}자를 초과할 수 없습니다."
            )
        commands.append(command)
    return commands


def convert_natural_language_to_commands(
    natural_text: str,
    command_guide: str,
) -> dict:
    """자연어를 TradingAgent 명령 문자열 배열로 변환합니다."""
    api_key = get_google_ai_api_key()
    if not api_key:
        return {
            "success": False,
            "commands": [],
            "error": ".env에 GOOGLE_AI_API_KEY가 설정되어 있지 않습니다.",
        }
    if not GOOGLE_AI_MODEL:
        return {
            "success": False,
            "commands": [],
            "error": "Google AI 모델명이 설정되어 있지 않습니다.",
        }

    model_name = GOOGLE_AI_MODEL.removeprefix("models/")
    url = (
        f"{GOOGLE_AI_API_BASE_URL}/models/"
        f"{quote(model_name, safe='')}:generateContent"
    )
    prompt = (
        "다음은 현재 프로그램의 전체 명령어 기준 문서다.\n\n"
        "<command_guide>\n"
        f"{command_guide}\n"
        "</command_guide>\n\n"
        "다음 사용자 입력을 위 문서에 맞는 명령어 배열로 변환하라.\n"
        "<user_input>\n"
        f"{natural_text.strip()}\n"
        "</user_input>"
    )
    payload = {
        "systemInstruction": {
            "parts": [{"text": _SYSTEM_INSTRUCTION}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "candidateCount": 1,
            "responseFormat": {
                "text": {
                    "mimeType": "application/json",
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
            json=payload,
            timeout=GOOGLE_AI_TIMEOUT_SECONDS,
        )
        data = response.json()
    except Exception as exc:
        log_error(f"[Google AI 자연어 명령 변환 통신 오류] {exc}")
        return {
            "success": False,
            "commands": [],
            "error": f"Google AI 통신 중 오류가 발생했습니다: {exc}",
        }

    if not getattr(response, "ok", False):
        error_message = "Google AI가 요청을 거부했습니다."
        if isinstance(data, dict) and isinstance(data.get("error"), dict):
            error_message = str(data["error"].get("message") or error_message)
        log_error(
            f"[Google AI 자연어 명령 변환 실패] HTTP "
            f"{getattr(response, 'status_code', 'unknown')}: {error_message}"
        )
        return {
            "success": False,
            "commands": [],
            "error": error_message,
        }

    candidate_text = _extract_candidate_text(data)
    if not candidate_text:
        block_reason = ""
        if isinstance(data, dict) and isinstance(data.get("promptFeedback"), dict):
            block_reason = str(data["promptFeedback"].get("blockReason") or "")
        reason = (
            f"Google AI 응답이 차단되었습니다: {block_reason}"
            if block_reason
            else "Google AI 응답에 명령 배열이 없습니다."
        )
        return {"success": False, "commands": [], "error": reason}

    try:
        commands = _normalize_command_array(json.loads(candidate_text))
    except (json.JSONDecodeError, ValueError) as exc:
        log_error(f"[Google AI 자연어 명령 응답 검증 실패] {exc}")
        return {
            "success": False,
            "commands": [],
            "error": f"Google AI 응답 형식이 올바르지 않습니다: {exc}",
        }

    return {"success": True, "commands": commands, "error": None}
