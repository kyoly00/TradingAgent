"""트레일링 스탑 설정과 자동매도 시작·중지 명령 처리 모듈."""

from telegram.tel_send import send_telegram_message
from trading.trailing_stop import trailing_stop_watcher
from utils.logger import log_error
from utils.settings import (
    get_trailing_stop_auto_trade_enabled,
    get_trailing_stop_settings,
    set_trailing_stop_settings,
)


def _execute_full_sell(stock_code: str, quantity: int) -> tuple[bool, str]:
    """기존 시장가 매도 명령으로 매매가능수량 전부를 주문합니다."""
    from .sell import handle_sell_command

    reply = handle_sell_command([stock_code, str(quantity)])
    return reply.startswith("💰 [매도 주문 접수 완료]"), reply


def configure_trailing_stop_watcher(chat_id: int | str | None = None):
    trailing_stop_watcher.configure(
        order_executor=_execute_full_sell,
        notifier=lambda message: send_telegram_message(message, chat_id=chat_id),
    )


def restore_trailing_stop_watcher(chat_id: int | str | None = None):
    """저장된 활성화 설정에 따라 프로그램 시작 시 감시를 복구합니다."""
    if not get_trailing_stop_auto_trade_enabled():
        return
    configure_trailing_stop_watcher(chat_id=chat_id)
    success, message = trailing_stop_watcher.start(persist=False)
    if not success:
        log_error(f"[트레일링 스탑 자동 복구 실패] {message}")


def handle_start_trst_command(
    args: list[str] | None = None,
    chat_id: int | str | None = None,
) -> str:
    """보유 종목 트레일링 스탑 감시와 자동매도를 시작합니다."""
    if args:
        return "⚠️ 시작 명령 형식: `start trst`"
    configure_trailing_stop_watcher(chat_id=chat_id)
    success, message = trailing_stop_watcher.start(persist=True)
    if not success:
        return message
    status = trailing_stop_watcher.get_status()
    return (
        "🚀 [트레일링 스탑 자동매도 시작]\n\n"
        f"• 고점 대비 하락률: {status['drop_rate']:g}%\n"
        f"• 최소 발동 수익률: {status['min_profit_rate']:g}%\n"
        "• 대상: 계좌의 국내주식 보유 종목\n"
        "• 시세: 공용 WebSocket 엔진의 실시간 체결 데이터\n"
        "• 조건 충족 시 매매가능수량 전부를 시장가 매도합니다."
    )


def handle_stop_trst_command(args: list[str] | None = None) -> str:
    """트레일링 스탑 감시와 공용 WebSocket 구독을 중지합니다."""
    if args:
        return "⚠️ 중지 명령 형식: `stop trst`"
    _, message = trailing_stop_watcher.stop(persist=True)
    return message


def handle_trst_command(args: list[str]) -> str:
    """`trst {고점대비하락률} {최소발동수익률}` 명령을 처리합니다."""
    if not args:
        drop_rate, min_profit_rate = get_trailing_stop_settings()
        return (
            "📉 [현재 트레일링 스탑 설정]\n\n"
            f"• 고점 대비 하락률: {drop_rate:g}%\n"
            f"• 최소 발동 수익률: {min_profit_rate:g}%\n\n"
            "변경 방법: `trst {고점대비하락률} {최소발동수익률}`\n"
            "예시: `trst 3.5 5`"
        )

    if len(args) != 2:
        return (
            "⚠️ 올바른 형식으로 입력해 주세요.\n"
            "• 형식: `trst {고점대비하락률} {최소발동수익률}`\n"
            "• 예시: `trst 3.5 5`"
        )

    success, drop_rate, min_profit_rate, message = set_trailing_stop_settings(
        args[0],
        args[1],
    )
    if not success:
        return (
            "⚠️ [트레일링 스탑 설정 실패]\n"
            f"• 사유: {message}\n"
            "• 두 값은 각각 0보다 큰 숫자로 입력해 주세요."
        )

    trailing_stop_watcher.reload_settings()
    return (
        "✅ [트레일링 스탑 설정 완료]\n\n"
        f"• 고점 대비 하락률: {drop_rate:g}%\n"
        f"• 최소 발동 수익률: {min_profit_rate:g}%\n"
        "• 설정이 `config/data/settings.json`에 저장되었습니다."
    )
