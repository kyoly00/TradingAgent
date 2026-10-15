"""매도 종목 재매수 쿨다운 설정 명령어 처리 모듈."""

from utils.settings import (
    get_repurchase_cooldown_hours,
    set_repurchase_cooldown_hours,
)


def handle_cooldown_command(args: list[str]) -> str:
    """`cooldown {시간}` 명령으로 재매수 제한 시간을 설정합니다."""
    if not args:
        hours = get_repurchase_cooldown_hours()
        state = "제한 없음" if hours == 0 else f"매도 후 {hours:g}시간"
        return (
            "🕒 [종목 재매수 쿨다운 설정]\n\n"
            f"• 현재 설정: {state}\n"
            "• 변경: `cooldown {시간}`\n"
            "• 비활성화: `cooldown 0`"
        )

    if len(args) != 1:
        return "⚠️ 올바른 형식으로 입력해 주세요: `cooldown {시간}`"

    success, hours, message = set_repurchase_cooldown_hours(args[0])
    if not success:
        return f"⚠️ [재매수 쿨다운 설정 실패]\n• 사유: {message}"
    if hours == 0:
        return "✅ 재매수 쿨다운 제한을 비활성화하고 기존 매도 기록을 비웠습니다."
    return (
        "✅ [재매수 쿨다운 설정 완료]\n\n"
        f"• 매도 후 제한 시간: {hours:g}시간\n"
        "• 제한 시간 동안 해당 종목의 모든 매수 주문이 차단됩니다."
    )
