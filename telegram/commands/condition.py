"""`cond` 조건검색식 목록조회 명령 처리 모듈."""

from api.condition import get_condition_list


def handle_cond_command(args: list[str] | None = None) -> str:
    """API 일련번호와 조건식명을 별도 목록 번호 없이 출력합니다."""
    if args:
        return "⚠️ 조건검색 목록조회 명령 형식: `cond`"

    result = get_condition_list()
    if not result.get("success"):
        return f"❌ [조건검색식 목록조회 실패]\n• 사유: {result.get('error')}"

    conditions = result.get("conditions") or []
    if not conditions:
        return "ℹ️ 등록된 조건검색식이 없습니다."

    lines = ["📋 [조건검색식 목록]", ""]
    for condition in conditions:
        lines.append(f"일련번호 {condition['seq']} | {condition['name']}")
    return "\n".join(lines)
