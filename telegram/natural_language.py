"""자연어 명령 변환과 채팅방별 실행 확인 상태를 관리합니다."""

import threading
from collections.abc import Callable
from pathlib import Path

from api.google_ai import convert_natural_language_to_commands
from utils.logger import log_error, log_info


CommandConverter = Callable[[str, str], dict]
CommandExecutor = Callable[[str], tuple[str, bool]]
CommandValidator = Callable[[str], bool]

COMMAND_GUIDE_PATH = Path(__file__).resolve().parents[1] / "command_guide.md"


class NaturalLanguageCommandCoordinator:
    """AI 변환 결과를 저장하고 다음 메시지의 실행 확인을 처리합니다."""

    def __init__(self, converter: CommandConverter = convert_natural_language_to_commands):
        self._converter = converter
        self._pending_commands: dict[str, tuple[str, ...]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _chat_key(chat_id: int | str) -> str:
        return str(chat_id)

    @staticmethod
    def _load_command_guide() -> str:
        return COMMAND_GUIDE_PATH.read_text(encoding="utf-8")

    def has_pending(self, chat_id: int | str) -> bool:
        """해당 채팅방에 실행 확인을 기다리는 명령 묶음이 있는지 반환합니다."""
        with self._lock:
            return self._chat_key(chat_id) in self._pending_commands

    def request_confirmation(
        self,
        chat_id: int | str,
        natural_text: str,
        command_validator: CommandValidator,
    ) -> str:
        """자연어를 변환해 검증한 뒤 채팅방별 확인 대기 상태로 저장합니다."""
        try:
            command_guide = self._load_command_guide()
        except OSError as exc:
            log_error(f"[command_guide.md 읽기 실패] {exc}")
            return (
                "❌ [자연어 명령 변환 실패]\n"
                "• 명령어 가이드 파일을 읽을 수 없습니다."
            )

        try:
            result = self._converter(natural_text, command_guide)
        except Exception as exc:
            log_error(f"[자연어 명령 변환 예외] {exc}")
            return (
                "❌ [자연어 명령 변환 실패]\n"
                "• Google AI 변환 처리 중 오류가 발생했습니다."
            )
        if not isinstance(result, dict):
            log_error("[자연어 명령 변환 실패] 변환 결과가 객체가 아닙니다.")
            return (
                "❌ [자연어 명령 변환 실패]\n"
                "• Google AI 변환 결과 형식이 올바르지 않습니다."
            )
        if not result.get("success"):
            reason = str(result.get("error") or "알 수 없는 오류")
            return f"❌ [자연어 명령 변환 실패]\n• 사유: {reason}"

        commands = result.get("commands") or []
        if not commands:
            return (
                "⚠️ [변환 가능한 명령 없음]\n"
                "• 요청에 해당하는 명령이 없거나 필수 정보가 부족합니다.\n"
                "• 종목코드, 수량, 금액, 시간 등 필요한 값을 확인해 주세요."
            )

        invalid_commands = [
            command for command in commands if not command_validator(command)
        ]
        if invalid_commands:
            log_error(
                "[Google AI 명령 검증 실패] 지원하지 않는 명령 반환: "
                + repr(invalid_commands)
            )
            return (
                "❌ [자연어 명령 변환 실패]\n"
                "• Google AI가 지원하지 않는 명령을 반환하여 실행을 차단했습니다."
            )

        normalized_commands = tuple(str(command).strip() for command in commands)
        with self._lock:
            self._pending_commands[self._chat_key(chat_id)] = normalized_commands

        command_lines = "\n".join(
            f"{index}. `{command}`"
            for index, command in enumerate(normalized_commands, start=1)
        )
        return (
            "🤖 [자연어 명령 변환 결과]\n\n"
            f"{command_lines}\n\n"
            "위 명령을 순서대로 실행하려면 `y`를 입력해 주세요.\n"
            "다른 내용을 입력하면 실행하지 않고 취소합니다."
        )

    def resolve_confirmation(
        self,
        chat_id: int | str,
        answer: str,
        command_executor: CommandExecutor,
    ) -> tuple[str, bool]:
        """대기 중인 명령을 `y`에서만 순차 실행하고 그 외 입력은 취소합니다."""
        with self._lock:
            commands = self._pending_commands.pop(self._chat_key(chat_id), None)

        if commands is None:
            return "", False
        if answer.strip().lower() != "y":
            return "🚫 자연어 변환 명령 실행을 취소했습니다.", False

        result_sections = []
        should_exit = False
        for index, command in enumerate(commands, start=1):
            try:
                reply, command_should_exit = command_executor(command)
            except Exception as exc:
                log_error(f"[자연어 변환 명령 실행 오류] 명령: {command!r}, 오류: {exc}")
                reply = f"❌ 실행 중 오류가 발생했습니다: {exc}"
                command_should_exit = False

            result_sections.append(
                f"▶️ {index}. `{command}`\n{reply or '응답 메시지 없음'}"
            )
            log_info(f"[자연어 변환 명령 실행] {index}/{len(commands)}: {command}")
            if command_should_exit:
                should_exit = True
                break

        return (
            "✅ [자연어 변환 명령 실행 결과]\n\n"
            + "\n\n".join(result_sections),
            should_exit,
        )

    def clear(self):
        """프로그램 종료 시 모든 확인 대기 상태를 제거합니다."""
        with self._lock:
            self._pending_commands.clear()

    def cancel_pending(self, chat_id: int | str):
        """해당 채팅방의 확인 대기 명령을 실행 없이 제거합니다."""
        with self._lock:
            self._pending_commands.pop(self._chat_key(chat_id), None)


natural_language_command_coordinator = NaturalLanguageCommandCoordinator()
