"""자연어 변환 결과의 확인 상태와 명령 실행을 관리합니다."""

import threading
import re
from collections import deque
from collections.abc import Callable
from pathlib import Path

from api.google_ai import convert_natural_language_to_commands
from utils.logger import log_error
from utils.stock_lookup import find_stock_name_candidates

from .commands.dispatcher import is_supported_command_text


CommandExecutor = Callable[[str], tuple[str, bool]]
MAX_MEMORY_ENTRIES = 12
MAX_CONTEXT_CHARS = 6000


class NaturalLanguageCommandCoordinator:
    """채팅방별 명령 제안 상태를 보관하고 확인 후 실행합니다."""

    def __init__(self, guide_path: Path | None = None):
        self._guide_path = guide_path or (
            Path(__file__).resolve().parents[1] / "command_guide.md"
        )
        self._pending_by_chat: dict[str, list[str]] = {}
        self._memory_by_chat: dict[str, deque[str]] = {}
        self._holdings_by_chat: dict[str, dict[str, tuple[str, int]]] = {}
        self._stock_entities_by_chat: dict[str, dict[str, str]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _chat_key(chat_id: int | str) -> str:
        return str(chat_id)

    def has_pending(self, chat_id: int | str) -> bool:
        with self._lock:
            return self._chat_key(chat_id) in self._pending_by_chat

    @staticmethod
    def _extract_safe_response_context(response: str) -> str:
        """외부 AI 문맥에는 종목 식별 정보와 생성 명령만 남깁니다."""
        lines = str(response).splitlines()
        selected: list[str] = []
        for line in lines:
            has_stock_code = bool(re.search(r"\b\d{6}\b", line))
            has_command = "`" in line
            if has_stock_code or has_command:
                selected.append(line.strip())
        return "\n".join(selected)[:2000]

    def _update_local_holdings(self, chat_id: int | str, response: str) -> None:
        """리포트 응답의 보유수량을 외부 전송 없이 채팅별 로컬 메모리에 저장합니다."""
        holding_pattern = re.compile(
            r"(?P<name>[^\n()]*)\((?P<code>\d{6})\)\s*\n"
            r"\s*[^\n]*보유수량:\s*(?P<quantity>[\d,]+)주"
        )
        holdings: dict[str, tuple[str, int]] = {}
        for match in holding_pattern.finditer(str(response)):
            code = match.group("code")
            name = match.group("name").strip(" •0123456789️⃣") or code
            quantity = int(match.group("quantity").replace(",", ""))
            if quantity > 0:
                holdings[code] = (name, quantity)
        if holdings:
            with self._lock:
                self._holdings_by_chat[self._chat_key(chat_id)] = holdings

    def _resolve_local_memory_commands(
        self,
        chat_id: int | str,
        commands: list[str],
    ) -> tuple[list[str], str]:
        """AI의 종목별 전량 중간 명령을 로컬 보유수량으로 치환합니다."""
        key = self._chat_key(chat_id)
        with self._lock:
            holdings = dict(self._holdings_by_chat.get(key, {}))

        resolved: list[str] = []
        pattern = re.compile(r"^sell\s+(\d{6})\s+all(?:\s+(\d+))?$", re.IGNORECASE)
        for command in commands:
            match = pattern.fullmatch(command.strip())
            if not match:
                resolved.append(command)
                continue
            stock_code, price = match.groups()
            holding = holdings.get(stock_code)
            if not holding:
                return [], (
                    f"{stock_code} 종목의 최근 보유수량을 로컬 메모리에서 확인할 수 없습니다. "
                    "먼저 `report`를 실행한 뒤 다시 요청해 주세요."
                )
            quantity = holding[1]
            resolved_command = f"sell {stock_code} {quantity}"
            if price:
                resolved_command += f" {price}"
            resolved.append(resolved_command)
        return resolved, ""

    def _remember(self, chat_id: int | str, entry: str) -> None:
        clean_entry = str(entry).strip()
        if not clean_entry:
            return
        key = self._chat_key(chat_id)
        with self._lock:
            memory = self._memory_by_chat.setdefault(
                key,
                deque(maxlen=MAX_MEMORY_ENTRIES),
            )
            memory.append(clean_entry[:2500])

    def record_exchange(
        self,
        chat_id: int | str,
        user_text: str,
        assistant_response: str,
    ) -> None:
        """직접 실행된 명령의 종목 문맥을 다음 자연어 요청에 사용할 수 있게 저장합니다."""
        self._update_local_holdings(chat_id, assistant_response)
        safe_response = self._extract_safe_response_context(assistant_response)
        entry = f"사용자: {user_text.strip()}"
        if safe_response:
            entry += f"\n프로그램: {safe_response}"
        self._remember(chat_id, entry)

    def _build_context(self, chat_id: int | str, user_text: str) -> str:
        key = self._chat_key(chat_id)
        with self._lock:
            history = list(self._memory_by_chat.get(key, ()))

        parts = []
        if history:
            parts.append("[최근 대화 메모리]\n" + "\n---\n".join(history))

        current_candidates = find_stock_name_candidates(user_text)
        with self._lock:
            entities = self._stock_entities_by_chat.setdefault(key, {})
            for item in current_candidates:
                entities[item["stock_code"]] = item["stock_name"]
            remembered_candidates = list(entities.items())[-5:]

        if remembered_candidates:
            candidate_lines = [
                f"- {stock_name} = {stock_code}"
                for stock_code, stock_name in remembered_candidates
            ]
            parts.append(
                "[현재 또는 최근 문장에서 확인된 로컬 종목명 후보]\n"
                + "\n".join(candidate_lines)
                + "\n후보가 여러 개면 문맥상 하나로 확정되는 경우에만 사용합니다."
            )
        return "\n\n".join(parts)[-MAX_CONTEXT_CHARS:]

    def request_conversion(self, chat_id: int | str, user_text: str) -> str:
        """자연어를 변환하고 유효한 명령이면 확인 대기 상태로 저장합니다."""
        try:
            command_guide = self._guide_path.read_text(encoding="utf-8")
        except OSError as exc:
            log_error(f"[명령어 가이드 읽기 실패] {exc}")
            return "❌ 자연어 처리에 필요한 command_guide.md를 읽을 수 없습니다."

        conversation_context = self._build_context(chat_id, user_text)
        result = convert_natural_language_to_commands(
            user_text,
            command_guide,
            conversation_context,
        )
        if not result.get("success"):
            error = result.get("error") or "알 수 없는 오류"
            self._remember(chat_id, f"사용자: {user_text}\n변환 실패: {error}")
            return f"❌ 자연어 명령 변환에 실패했습니다.\n• 사유: {error}"

        commands = result.get("commands", [])
        if not commands:
            self._remember(
                chat_id,
                f"사용자: {user_text}\n변환 결과: 필요한 정보가 부족하여 명령 없음",
            )
            return (
                "❓ 요청에 해당하는 실행 가능한 명령어를 찾지 못했습니다.\n"
                "명령어에 필요한 종목코드, 수량, 금액 또는 시간을 더 구체적으로 알려 주세요."
            )

        commands, memory_error = self._resolve_local_memory_commands(chat_id, commands)
        if memory_error:
            self._remember(chat_id, f"사용자: {user_text}\n로컬 메모리 확인 실패")
            return f"❓ {memory_error}"

        invalid_commands = [
            command for command in commands if not is_supported_command_text(command)
        ]
        if invalid_commands:
            log_error(
                "[자연어 명령 검증 실패] 지원하지 않는 명령이 포함됨: "
                + ", ".join(invalid_commands)
            )
            return "❌ AI가 지원하지 않는 명령을 생성하여 실행을 차단했습니다."

        with self._lock:
            self._pending_by_chat[self._chat_key(chat_id)] = list(commands)

        self._remember(
            chat_id,
            f"사용자: {user_text}\n제안 명령: {', '.join(commands)}",
        )

        command_lines = "\n".join(
            f"{index}. `{command}`" for index, command in enumerate(commands, start=1)
        )
        return (
            "🤖 다음 명령을 실행할까요?\n\n"
            f"{command_lines}\n\n"
            "실행하려면 `y`를 입력하세요. 다른 입력은 취소합니다."
        )

    def resolve_confirmation(
        self,
        chat_id: int | str,
        answer: str,
        executor: CommandExecutor,
    ) -> tuple[str, bool]:
        """확인 응답을 소비하고 y일 때만 보관된 명령을 순서대로 실행합니다."""
        with self._lock:
            commands = self._pending_by_chat.pop(self._chat_key(chat_id), None)

        if commands is None:
            return "", False
        if answer.strip().lower() != "y":
            self._remember(chat_id, "사용자 확인: 취소")
            return "🚫 자연어 명령 실행을 취소했습니다.", False

        responses: list[str] = []
        should_exit = False
        for index, command in enumerate(commands, start=1):
            reply, command_should_exit = executor(command)
            heading = f"▶️ {index}. `{command}`"
            responses.append(f"{heading}\n{reply}" if reply else heading)
            if command_should_exit:
                should_exit = True
                break

        result_message = "🤖 [자연어 명령 실행 결과]\n\n" + "\n\n".join(responses)
        self._remember(
            chat_id,
            "사용자 확인: 실행\n" + self._extract_safe_response_context(result_message),
        )
        return result_message, should_exit

    def cancel_pending(self, chat_id: int | str) -> None:
        with self._lock:
            self._pending_by_chat.pop(self._chat_key(chat_id), None)

    def clear(self) -> None:
        with self._lock:
            self._pending_by_chat.clear()
            self._memory_by_chat.clear()
            self._holdings_by_chat.clear()
            self._stock_entities_by_chat.clear()


natural_language_command_coordinator = NaturalLanguageCommandCoordinator()
