"""최대 보유 종목 수 설정 명령어 처리 모듈."""

from utils.settings import get_max_holding_count, set_max_holding_count


def handle_mxhold_command(args: list[str]) -> str:
    """`mxhold {개수}` 명령으로 최대 보유 종목 수를 설정합니다."""
    if not args:
        count = get_max_holding_count()
        state = "제한 없음" if count == 0 else f"최대 {count}개"
        return (
            "📦 [최대 보유 종목 수 설정]\n\n"
            f"• 현재 설정: {state}\n"
            "• 변경: `mxhold {개수}`\n"
            "• 비활성화: `mxhold 0`"
        )

    if len(args) != 1:
        return "⚠️ 올바른 형식으로 입력해 주세요: `mxhold {개수}`"

    success, count, message = set_max_holding_count(args[0])
    if not success:
        return f"⚠️ [최대 보유 종목 수 설정 실패]\n• 사유: {message}"
    if count == 0:
        return "✅ 최대 보유 종목 수 제한을 비활성화했습니다."
    return (
        "✅ [최대 보유 종목 수 설정 완료]\n\n"
        f"• 최대 보유 종목 수: {count}개\n"
        "• 한도 도달 시 새로운 종목의 매수 주문이 차단됩니다."
    )
