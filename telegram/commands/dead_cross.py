"""데드크로스 자동매도 시작·중지·상태 명령 처리 모듈."""

from telegram.tel_send import send_telegram_message
from trading.dead_cross import dead_cross_watcher
from utils.logger import log_error, log_info
from utils.settings import get_dead_cross_auto_trade_enabled


def _execute_full_sell(stock_code: str, quantity: int) -> tuple[bool, str]:
    """기존 시장가 매도 명령 루틴으로 매매가능수량 전부를 주문합니다."""
    from .sell import handle_sell_command

    reply = handle_sell_command([stock_code, str(quantity)])
    return reply.startswith("💰 [매도 주문 접수 완료]"), reply


def configure_dead_cross_watcher(chat_id: int | str | None = None):
    """데드크로스 워처에 주문·텔레그램 콜백을 연결합니다."""
    dead_cross_watcher.configure(
        order_executor=_execute_full_sell,
        notifier=lambda message: send_telegram_message(message, chat_id=chat_id),
    )


def restore_dead_cross_watcher(chat_id: int | str | None = None):
    """저장된 활성화 설정이 켜져 있으면 프로그램 시작 시 감시를 복구합니다."""
    if not get_dead_cross_auto_trade_enabled():
        return
    configure_dead_cross_watcher(chat_id=chat_id)
    success, message = dead_cross_watcher.start(persist=False)
    if success:
        log_info(f"[데드크로스 자동 복구] {message}")
    else:
        log_error(f"[데드크로스 자동 복구 실패] {message}")


def handle_start_ddcrs_command(
    args: list[str] | None = None,
    chat_id: int | str | None = None,
) -> str:
    """보유 종목 데드크로스 감시와 자동매도를 활성화합니다."""
    if args:
        return "⚠️ 시작 명령 형식: `start ddcrs`"
    configure_dead_cross_watcher(chat_id=chat_id)
    success, message = dead_cross_watcher.start(persist=True)
    if not success:
        return message
    status = dead_cross_watcher.get_status()
    session_state = "실시간 감시 중" if status["session_active"] else "장 시작 또는 초기화 대기 중"
    return (
        "🚀 [데드크로스 자동매도 시작]\n\n"
        f"• 상태: {session_state}\n"
        f"• 이동평균: 단기 {status['short_period']} / 장기 {status['long_period']}\n"
        "• 대상: 계좌의 매도 가능한 국내주식 보유 종목\n"
        "• 조건: 단기 MA가 장기 MA를 위에서 아래로 돌파하면 시장가 전량 매도\n"
        "• 정규 장 시간마다 자동으로 실시간 감시를 실행합니다."
    )


def handle_stop_ddcrs_command(args: list[str] | None = None) -> str:
    """데드크로스 감시와 WebSocket 수신을 즉시 비활성화합니다."""
    if args:
        return "⚠️ 중지 명령 형식: `stop ddcrs`"
    _, message = dead_cross_watcher.stop(persist=True)
    return message


def handle_ddcrs_status_command(args: list[str] | None = None) -> str:
    """현재 데드크로스 자동매도 감시 상태를 반환합니다."""
    if args:
        return "⚠️ 상태 조회 형식: `ddcrs`"
    status = dead_cross_watcher.get_status()
    if status["session_active"]:
        state = "실시간 감시 중 🟢"
    elif status["is_running"]:
        state = "활성화됨 · 장 시작 또는 초기화 대기 중 🟡"
    else:
        state = "중지됨 ⚪"

    last_cross = status["last_cross"]
    last_cross_text = (
        f"{last_cross['stock_code']} ({last_cross['timestamp']})"
        if last_cross
        else "없음"
    )
    lines = [
        "📉 [데드크로스 자동매도 상태]\n",
        f"• 상태: {state}",
        f"• 이동평균: 단기 {status['short_period']} / 장기 {status['long_period']}",
        f"• 감시 중인 보유 종목: {status['monitored_count']}개",
        f"• 마지막 시세: {status['last_checked_at'] or '미수신'}",
        f"• 마지막 데드크로스: {last_cross_text}",
        f"• 최근 오류: {status['last_error'] or '없음'}",
    ]
    if status["monitored_codes"]:
        lines.append(f"• 종목코드: {', '.join(status['monitored_codes'])}")
    return "\n".join(lines)
