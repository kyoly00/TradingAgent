"""
골든/데드크로스 설정 명령어 처리 모듈:
분봉값 설정과 대상 종목 목록의 추가·조회·삭제를 처리합니다.
"""

from trading.golden_cross import golden_cross_watcher
from telegram.tel_send import send_telegram_message
from utils.logger import log_error, log_info
from utils.settings import (
    add_golden_cross_stock,
    clear_golden_cross_stocks,
    get_golden_cross_auto_trade_enabled,
    get_golden_cross_intervals,
    get_golden_cross_stocks,
    remove_golden_cross_stock,
    set_golden_cross_intervals,
)


def _execute_max_amount_buy(stock_code: str, amount: int) -> tuple[bool, str]:
    """기존 buy max 명령 루틴을 이용해 자동매수를 실행합니다."""
    from .buy import handle_buy_command

    reply = handle_buy_command([stock_code, "max", str(amount)])
    return reply.startswith("🛒 [최대 금액 매수 주문 접수 완료]"), reply


def configure_golden_cross_watcher(chat_id: int | str | None = None):
    """골든크로스 워처에 주문·텔레그램 콜백을 연결합니다."""
    golden_cross_watcher.configure(
        order_executor=_execute_max_amount_buy,
        notifier=lambda message: send_telegram_message(message, chat_id=chat_id),
    )


def restore_golden_cross_watcher(chat_id: int | str | None = None):
    """저장된 활성 설정이 켜져 있으면 프로그램 시작 시 감시를 복구합니다."""
    if not get_golden_cross_auto_trade_enabled():
        return
    configure_golden_cross_watcher(chat_id=chat_id)
    success, message = golden_cross_watcher.start(persist=False)
    if success:
        log_info(f"[골든크로스 자동 복구] {message}")
    else:
        log_error(f"[골든크로스 자동 복구 실패] {message}")


def handle_start_gdcrs_command(
    args: list[str] | None = None,
    chat_id: int | str | None = None,
) -> str:
    """골든크로스 감시와 자동매수를 활성화합니다."""
    if args:
        return "⚠️ 시작 명령 형식: `start gdcrs`"
    configure_golden_cross_watcher(chat_id=chat_id)
    success, message = golden_cross_watcher.start(persist=True)
    if not success:
        return message
    status = golden_cross_watcher.get_status()
    session_state = "실시간 감시 중" if status["session_active"] else "장 시작 대기 중"
    return (
        "🚀 [골든크로스 자동매수 시작]\n\n"
        f"• 상태: {session_state}\n"
        f"• 이동평균: 단기 {status['short_period']} / 장기 {status['long_period']}\n"
        f"• 대상 종목: {status['configured_count']}개\n"
        "• 정규 장 시간마다 자동으로 실시간 감시를 실행합니다."
    )


def handle_stop_gdcrs_command(args: list[str] | None = None) -> str:
    """골든크로스 감시와 WebSocket 수신을 즉시 비활성화합니다."""
    if args:
        return "⚠️ 중지 명령 형식: `stop gdcrs`"
    _, message = golden_cross_watcher.stop(persist=True)
    return message


def _get_usage_message() -> str:
    """gdcrs 명령어의 전체 사용법을 반환합니다."""
    return (
        "ℹ️ [골든/데드크로스 설정]\n\n"
        "• 이동평균 설정: `gdcrs intv {단기} {장기}`\n"
        "• 종목 추가: `gdcrs add {종목코드} {금액}`\n"
        "• 목록 조회: `gdcrs list`\n"
        "• 종목 삭제: `gdcrs remove {번호}`\n"
        "• 목록 전체 삭제: `gdcrs clear`\n"
        "• 감시 시작/중지: `start gdcrs` / `stop gdcrs`\n"
        "• 감시 상태: `gdcrs status`"
    )


def _handle_interval_command(args: list[str]) -> str:
    """골든/데드크로스 분봉 설정을 조회하거나 변경합니다."""
    if len(args) == 1:
        short_interval, long_interval = get_golden_cross_intervals()
        return (
            "📈 [현재 골든/데드크로스 이동평균 설정]\n\n"
            f"• 단기 MA: 1분봉 {short_interval}개\n"
            f"• 장기 MA: 1분봉 {long_interval}개\n\n"
            "변경 방법: `gdcrs intv {단기} {장기}`"
        )

    if len(args) != 3:
        return (
            "⚠️ 올바른 형식으로 입력해 주세요.\n\n"
            "• 형식: `gdcrs intv {단기} {장기}`\n"
            "• 예시: `gdcrs intv 5 20`"
        )

    success, short_interval, long_interval, message = set_golden_cross_intervals(
        args[1].strip(),
        args[2].strip(),
    )
    if not success:
        return (
            "⚠️ [골든/데드크로스 분봉 설정 실패]\n"
            f"• 사유: {message}\n"
            "• 허용 범위: 단기·장기 각각 1~60 사이의 정수"
        )

    golden_cross_watcher.request_refresh()
    relation_warning = ""
    if short_interval >= long_interval:
        relation_warning = (
            "\n⚠️ 자동 감시를 시작하려면 단기 MA를 장기 MA보다 작게 설정해야 합니다."
        )
    return (
        "📈 [골든/데드크로스 이동평균 설정 완료]\n\n"
        f"• 단기 MA: 1분봉 {short_interval}개\n"
        f"• 장기 MA: 1분봉 {long_interval}개\n"
        "• 설정이 `config/data/settings.json`에 성공적으로 저장되었습니다."
        f"{relation_warning}"
    )


def _handle_add_command(args: list[str]) -> str:
    """골든크로스 대상 종목을 목록에 추가합니다."""
    if len(args) != 3:
        return (
            "⚠️ 올바른 형식으로 입력해 주세요.\n"
            "• 형식: `gdcrs add {종목코드} {금액}`\n"
            "• 예시: `gdcrs add 005930 1000000`"
        )

    success, item, message = add_golden_cross_stock(args[1], args[2])
    if not success or item is None:
        return f"⚠️ [골든크로스 종목 추가 실패]\n• 사유: {message}"

    golden_cross_watcher.request_refresh()
    return (
        "✅ [골든크로스 종목 추가 완료]\n\n"
        f"• 종목코드: {item['stock_code']}\n"
        f"• 설정금액: {item['amount']:,}원\n"
        "• 설정이 `config/data/settings.json`에 성공적으로 저장되었습니다."
    )


def _handle_list_command(args: list[str]) -> str:
    """골든크로스 대상 종목을 등록 순서대로 조회합니다."""
    if len(args) != 1:
        return "⚠️ 목록 조회 형식: `gdcrs list`"

    stocks = get_golden_cross_stocks()
    if not stocks:
        return (
            "📋 [골든크로스 대상 종목 목록]\n\n"
            "등록된 종목이 없습니다.\n"
            "추가 방법: `gdcrs add {종목코드} {금액}`"
        )

    lines = ["📋 [골든크로스 대상 종목 목록]\n"]
    for number, item in enumerate(stocks, start=1):
        lines.append(
            f"{number}. {item['stock_code']} | 설정금액: {item['amount']:,}원"
        )
    return "\n".join(lines)


def _handle_remove_command(args: list[str]) -> str:
    """조회 목록 번호에 해당하는 골든크로스 대상 종목을 삭제합니다."""
    if len(args) != 2:
        return (
            "⚠️ 올바른 형식으로 입력해 주세요.\n"
            "• 형식: `gdcrs remove {번호}`\n"
            "• 예시: `gdcrs remove 1`"
        )

    success, item, message = remove_golden_cross_stock(args[1])
    if not success or item is None:
        return f"⚠️ [골든크로스 종목 삭제 실패]\n• 사유: {message}"

    golden_cross_watcher.request_refresh()
    return (
        "🗑️ [골든크로스 종목 삭제 완료]\n\n"
        f"• 종목코드: {item['stock_code']}\n"
        f"• 설정금액: {item['amount']:,}원\n"
        "• 남은 목록 번호는 등록 순서대로 다시 부여됩니다."
    )


def _handle_clear_command(args: list[str]) -> str:
    """골든크로스 대상 종목 목록을 모두 삭제합니다."""
    if len(args) != 1:
        return "⚠️ 목록 전체 삭제 형식: `gdcrs clear`"

    success, removed_count, message = clear_golden_cross_stocks()
    if not success:
        return f"⚠️ [골든크로스 종목 목록 초기화 실패]\n• 사유: {message}"

    golden_cross_watcher.request_refresh()
    return (
        "🗑️ [골든크로스 종목 목록 초기화 완료]\n\n"
        f"• 삭제된 종목: {removed_count}개\n"
        "• 현재 등록된 종목: 0개"
    )


def _handle_status_command(args: list[str]) -> str:
    """골든크로스 자동매수 감시 상태를 반환합니다."""
    if len(args) != 1:
        return "⚠️ 상태 조회 형식: `gdcrs status`"
    status = golden_cross_watcher.get_status()
    if status["session_active"]:
        state = "실시간 감시 중 🟢"
    elif status["is_running"]:
        state = "활성화됨 · 장 시작 대기 중 🟡"
    else:
        state = "중지됨 ⚪"

    last_cross = status["last_cross"]
    last_cross_text = (
        f"{last_cross['stock_code']} ({last_cross['timestamp']})"
        if last_cross
        else "없음"
    )
    return (
        "📊 [골든크로스 자동매수 상태]\n\n"
        f"• 상태: {state}\n"
        f"• 이동평균: 단기 {status['short_period']} / 장기 {status['long_period']}\n"
        f"• 설정/감시 종목: {status['configured_count']}개 / {status['monitored_count']}개\n"
        f"• 마지막 시세: {status['last_checked_at'] or '미수신'}\n"
        f"• 마지막 골든크로스: {last_cross_text}\n"
        f"• 최근 오류: {status['last_error'] or '없음'}"
    )


def handle_gdcrs_command(args: list[str]) -> str:
    """골든/데드크로스 설정 및 대상 종목 목록 명령을 처리합니다."""
    if not args:
        return _get_usage_message()

    sub_command = args[0].strip().lower()
    if sub_command == "intv":
        return _handle_interval_command(args)
    if sub_command == "add":
        return _handle_add_command(args)
    if sub_command == "list":
        return _handle_list_command(args)
    if sub_command == "remove":
        return _handle_remove_command(args)
    if sub_command == "clear":
        return _handle_clear_command(args)
    if sub_command == "status":
        return _handle_status_command(args)
    return _get_usage_message()
