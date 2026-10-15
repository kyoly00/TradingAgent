"""조건검색식별 명령 배정 목록을 관리하는 `jggs` 명령 모듈."""

from utils.settings import (
    add_condition_command_mapping,
    clear_condition_command_mappings,
    get_condition_command_mappings,
    remove_condition_command_mapping,
)


def _get_usage_message() -> str:
    return (
        "ℹ️ [조건검색식 명령 배정 목록]\n\n"
        "• 추가: `jggs add {조건식번호} {명령어}`\n"
        "  예: `jggs add 0 buy ( ) max 100000`\n"
        "• 조회: `jggs list`\n"
        "• 삭제: `jggs remove {일련번호}`\n"
        "• 전체 삭제: `jggs clear`"
    )


def _handle_add_command(args: list[str]) -> str:
    if len(args) < 3:
        return (
            "⚠️ 올바른 형식으로 입력해 주세요.\n"
            "• 형식: `jggs add {조건식번호} {명령어}`\n"
            "• 예시: `jggs add 0 buy ( ) max 100000`"
        )

    command = " ".join(args[2:]).strip()
    success, item, message = add_condition_command_mapping(args[1], command)
    if not success or item is None:
        return f"⚠️ [조건검색식 명령 배정 추가 실패]\n• 사유: {message}"

    return (
        "✅ [조건검색식 명령 배정 추가 완료]\n\n"
        f"• 조건식 번호: {item['condition_seq']}\n"
        f"• 명령어: {item['command']}\n"
        "• 목록 조회: `jggs list`"
    )


def _handle_list_command(args: list[str]) -> str:
    if len(args) != 1:
        return "⚠️ 목록 조회 형식: `jggs list`"

    mappings = get_condition_command_mappings()
    if not mappings:
        return (
            "📋 [조건검색식 명령 배정 목록]\n\n"
            "등록된 항목이 없습니다.\n"
            "추가 방법: `jggs add {조건식번호} {명령어}`"
        )

    lines = ["📋 [조건검색식 명령 배정 목록]", ""]
    for list_number, item in enumerate(mappings, start=1):
        lines.append(
            f"{list_number}. 조건식 {item['condition_seq']} | {item['command']}"
        )
    return "\n".join(lines)


def _handle_remove_command(args: list[str]) -> str:
    if len(args) != 2:
        return (
            "⚠️ 올바른 형식으로 입력해 주세요.\n"
            "• 형식: `jggs remove {일련번호}`\n"
            "• 예시: `jggs remove 1`"
        )

    success, item, message = remove_condition_command_mapping(args[1])
    if not success or item is None:
        return f"⚠️ [조건검색식 명령 배정 삭제 실패]\n• 사유: {message}"

    return (
        "🗑️ [조건검색식 명령 배정 삭제 완료]\n\n"
        f"• 조건식 번호: {item['condition_seq']}\n"
        f"• 명령어: {item['command']}\n"
        "• 남은 목록의 일련번호는 1번부터 다시 부여됩니다."
    )


def _handle_clear_command(args: list[str]) -> str:
    if len(args) != 1:
        return "⚠️ 목록 전체 삭제 형식: `jggs clear`"

    success, removed_count, message = clear_condition_command_mappings()
    if not success:
        return f"⚠️ [조건검색식 명령 배정 목록 초기화 실패]\n• 사유: {message}"

    return (
        "🗑️ [조건검색식 명령 배정 목록 초기화 완료]\n\n"
        f"• 삭제된 항목: {removed_count}개\n"
        "• 현재 등록된 항목: 0개"
    )


def handle_jggs_command(args: list[str] | None = None) -> str:
    """`jggs add/list/remove/clear` 하위 명령을 처리합니다."""
    if not args:
        return _get_usage_message()

    sub_command = args[0].strip().lower()
    if sub_command == "add":
        return _handle_add_command(args)
    if sub_command == "list":
        return _handle_list_command(args)
    if sub_command == "remove":
        return _handle_remove_command(args)
    if sub_command == "clear":
        return _handle_clear_command(args)
    return _get_usage_message()
