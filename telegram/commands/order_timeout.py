"""매수 주문 미체결 후속 처리 시간과 동작을 설정하는 명령어 모듈."""

from trading.buy_order_follow_up import buy_order_follow_up_manager
from utils.settings import (
    get_buy_order_timeout_settings,
    set_buy_order_timeout_settings,
)


def handle_time_command(args: list[str]) -> str:
    """`time {초} cancel|market` 설정 명령을 처리합니다."""
    if not args:
        seconds, action = get_buy_order_timeout_settings()
        if seconds == 0:
            state = "비활성화"
        elif action == "cancel":
            state = f"{seconds}초 후 미체결 잔량 취소"
        else:
            state = f"{seconds}초마다 호가 상향 후 시장가 전환"
        return (
            "⏱️ [매수 미체결 후속 처리 설정]\n\n"
            f"• 현재 상태: {state}\n"
            "• 설정: `time {초} cancel` 또는 `time {초} market`\n"
            "• 비활성화: `time 0 cancel` 또는 `time 0 market`"
        )

    if len(args) != 2:
        return (
            "⚠️ 올바른 형식으로 입력해 주세요.\n"
            "• `time {초} cancel`\n"
            "• `time {초} market`"
        )

    success, seconds, action, message = set_buy_order_timeout_settings(
        args[0],
        args[1],
    )
    if not success:
        return f"⚠️ [매수 미체결 설정 실패]\n• 사유: {message}"

    # 설정 변경 전에 등록된 주문은 이전 정책으로 처리하지 않도록 중단합니다.
    buy_order_follow_up_manager.cancel_all()
    if seconds == 0:
        return "✅ 매수 미체결 후속 처리 기능을 비활성화했습니다."

    action_text = (
        "미체결 잔량 전체 취소"
        if action == "cancel"
        else "호가를 한 단계씩 올린 뒤 시장가 전환"
    )
    return (
        "✅ [매수 미체결 후속 처리 설정 완료]\n\n"
        f"• 대기 시간: {seconds}초\n"
        f"• 처리 방식: {action_text}"
    )
