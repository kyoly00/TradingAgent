"""자연어 명령 변환과 실행 확인 흐름 테스트."""

import json
import sys
import types
import unittest
from unittest.mock import patch

# 이 저장소에는 별도 의존성 명세가 없으므로, 최소 단위 테스트는 외부 통신
# 라이브러리가 없는 검사 환경에서도 모듈 로딩만 가능하도록 대체 모듈을 사용합니다.
try:
    import dotenv  # noqa: F401
except ModuleNotFoundError:
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: False
    sys.modules["dotenv"] = dotenv_stub

try:
    import requests  # noqa: F401
except ModuleNotFoundError:
    requests_stub = types.ModuleType("requests")
    requests_stub.request = lambda *args, **kwargs: None
    requests_stub.exceptions = types.SimpleNamespace(
        RequestException=Exception,
        Timeout=Exception,
    )
    sys.modules["requests"] = requests_stub

from api.google_ai import convert_natural_language_to_commands
from telegram.commands.dispatcher import is_supported_command_text
from telegram.natural_language import NaturalLanguageCommandCoordinator


class _FakeResponse:
    def __init__(self, data: dict, ok: bool = True, status_code: int = 200):
        self._data = data
        self.ok = ok
        self.status_code = status_code

    def json(self) -> dict:
        return self._data


class SupportedCommandTextTests(unittest.TestCase):
    def test_recognizes_command_aliases_and_slash_prefix(self):
        self.assertTrue(is_supported_command_text("/BUY 005930 1"))
        self.assertTrue(is_supported_command_text("잔고"))
        self.assertTrue(is_supported_command_text("start gdcrs"))

    def test_rejects_natural_language_and_empty_text(self):
        self.assertFalse(is_supported_command_text("삼성전자 한 주 사 줘"))
        self.assertFalse(is_supported_command_text(""))
        self.assertFalse(is_supported_command_text("/"))


class NaturalLanguageCommandCoordinatorTests(unittest.TestCase):
    @staticmethod
    def _validator(command: str) -> bool:
        return command.split(maxsplit=1)[0] in {"report", "orders", "buy"}

    def test_empty_array_reports_missing_command_without_pending_state(self):
        coordinator = NaturalLanguageCommandCoordinator(
            converter=lambda _text, _guide: {
                "success": True,
                "commands": [],
                "error": None,
            }
        )

        reply = coordinator.request_confirmation(1, "알 수 없는 요청", self._validator)

        self.assertIn("변환 가능한 명령 없음", reply)
        self.assertFalse(coordinator.has_pending(1))

    def test_invalid_command_is_blocked(self):
        coordinator = NaturalLanguageCommandCoordinator(
            converter=lambda _text, _guide: {
                "success": True,
                "commands": ["not-a-command"],
                "error": None,
            }
        )

        reply = coordinator.request_confirmation(1, "위험한 요청", self._validator)

        self.assertIn("실행을 차단", reply)
        self.assertFalse(coordinator.has_pending(1))

    def test_y_executes_multiple_commands_in_order_and_clears_pending(self):
        coordinator = NaturalLanguageCommandCoordinator(
            converter=lambda _text, _guide: {
                "success": True,
                "commands": ["report", "orders"],
                "error": None,
            }
        )
        executed = []
        coordinator.request_confirmation(10, "보고서와 주문 조회", self._validator)

        reply, should_exit = coordinator.resolve_confirmation(
            10,
            "Y",
            lambda command: (executed.append(command) or f"{command} 결과", False),
        )

        self.assertEqual(executed, ["report", "orders"])
        self.assertIn("report 결과", reply)
        self.assertIn("orders 결과", reply)
        self.assertFalse(should_exit)
        self.assertFalse(coordinator.has_pending(10))

    def test_non_y_cancels_without_execution(self):
        coordinator = NaturalLanguageCommandCoordinator(
            converter=lambda _text, _guide: {
                "success": True,
                "commands": ["buy 005930 1"],
                "error": None,
            }
        )
        executed = []
        coordinator.request_confirmation(20, "한 주 사 줘", self._validator)

        reply, should_exit = coordinator.resolve_confirmation(
            20,
            "아니요",
            lambda command: (executed.append(command) or "", False),
        )

        self.assertEqual(executed, [])
        self.assertIn("취소", reply)
        self.assertFalse(should_exit)
        self.assertFalse(coordinator.has_pending(20))

    def test_exit_command_stops_remaining_batch(self):
        coordinator = NaturalLanguageCommandCoordinator(
            converter=lambda _text, _guide: {
                "success": True,
                "commands": ["report", "orders"],
                "error": None,
            }
        )
        executed = []
        coordinator.request_confirmation(30, "종료 뒤 조회", self._validator)

        _reply, should_exit = coordinator.resolve_confirmation(
            30,
            "y",
            lambda command: (
                executed.append(command) or "종료",
                command == "report",
            ),
        )

        self.assertEqual(executed, ["report"])
        self.assertTrue(should_exit)

    def test_pending_states_are_separated_by_chat(self):
        coordinator = NaturalLanguageCommandCoordinator(
            converter=lambda _text, _guide: {
                "success": True,
                "commands": ["report"],
                "error": None,
            }
        )
        coordinator.request_confirmation(1, "보고서", self._validator)
        coordinator.request_confirmation(2, "보고서", self._validator)

        coordinator.resolve_confirmation(1, "n", lambda _command: ("", False))

        self.assertFalse(coordinator.has_pending(1))
        self.assertTrue(coordinator.has_pending(2))

    def test_cancel_pending_removes_unconfirmed_commands(self):
        coordinator = NaturalLanguageCommandCoordinator(
            converter=lambda _text, _guide: {
                "success": True,
                "commands": ["report"],
                "error": None,
            }
        )
        coordinator.request_confirmation(1, "보고서", self._validator)

        coordinator.cancel_pending(1)

        self.assertFalse(coordinator.has_pending(1))


class GoogleAiApiTests(unittest.TestCase):
    @patch("api.google_ai.get_google_ai_api_key", return_value="test-key")
    @patch("api.google_ai.http_client.post")
    def test_sends_guide_and_parses_json_command_array(self, post_mock, _key_mock):
        post_mock.return_value = _FakeResponse(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps(["report", "orders"])}]
                        }
                    }
                ]
            }
        )

        result = convert_natural_language_to_commands("보고서와 주문", "GUIDE BODY")

        self.assertTrue(result["success"])
        self.assertEqual(result["commands"], ["report", "orders"])
        request_kwargs = post_mock.call_args.kwargs
        self.assertEqual(request_kwargs["headers"]["x-goog-api-key"], "test-key")
        prompt = request_kwargs["json"]["contents"][0]["parts"][0]["text"]
        self.assertIn("GUIDE BODY", prompt)
        schema = request_kwargs["json"]["generationConfig"]["responseFormat"]["text"]["schema"]
        self.assertEqual(schema["type"], "array")
        self.assertEqual(schema["items"]["type"], "string")

    @patch("api.google_ai.get_google_ai_api_key", return_value="")
    def test_missing_api_key_fails_without_http_request(self, _key_mock):
        result = convert_natural_language_to_commands("보고서", "GUIDE")

        self.assertFalse(result["success"])
        self.assertIn("GOOGLE_AI_API_KEY", result["error"])


if __name__ == "__main__":
    unittest.main()
