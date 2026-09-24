"""
스탑로스(Stop Loss & Take Profit) 명령어 처리 모듈:
- 'tpr {익절 기준}': 익절 기준(Take Profit Rate) 설정 (항상 양수로 변환하여 저장)
- 'slr {손절 기준}': 손절 기준(Stop Loss Rate) 설정 (항상 음수로 변환하여 저장)
- 'start stls [주기]': 스탑로스 실시간 백그라운드 감시 루프 시작 (기본 10초)
- 'stop stls': 스탑로스 감시 루프 안전 중단
- 'stls': 현재 스탑로스 감시 상태 및 감시 대상 종목 현황 확인
"""

from trading.stop_loss import stop_loss_watcher
from utils.settings import (
    get_take_profit_rate,
    set_take_profit_rate,
    get_stop_loss_rate,
    set_stop_loss_rate,
)


def handle_tpr_command(args: list[str]) -> str:
    """
    'tpr' 명령어를 처리하여 익절 기준을 조회하거나 새로 설정합니다.
    양수/음수 중 어떤 값으로 입력하더라도 양수(+)로 전환하여 저장합니다.

    :param args: 명령어 뒤 인자 목록 (예: ['5'], ['-5.5'])
    :return: 텔레그램 회신 메시지 문자열
    """
    # 1. 인자가 없는 경우: 현재 설정된 익절 기준 안내
    if not args:
        current_tpr = get_take_profit_rate()
        return (
            "🎯 [현재 익절 기준 (Take Profit)]\n\n"
            f"• 설정 기준: +{current_tpr:g}% 도달 시 익절\n"
            "• 저장 위치: `config/data/settings.json`\n\n"
            "변경 방법:\n"
            "`tpr {익절 기준}`\n"
            "• 예시: `tpr 5` (+5% 도달 시 익절)\n"
            "• 예시: `tpr 7.5` (+7.5% 도달 시 익절)\n"
            "💡 양수/음수 중 어떤 값으로 넣어도 양수(+)로 전환되어 저장됩니다."
        )

    rate_arg = args[0].strip()

    # 2. 익절 기준 검증 및 저장
    success, norm_rate, msg = set_take_profit_rate(rate_arg)

    if success:
        return (
            "🎯 [익절 기준(TPR) 설정 완료]\n\n"
            f"• 설정된 익절 기준: +{norm_rate:g}%\n"
            f"• 수익률이 +{norm_rate:g}% 도달 시 익절(시장가 매도)을 진행합니다.\n"
            "• 설정이 `config/data/settings.json`에 성공적으로 저장되었습니다."
        )
    else:
        return f"⚠️ [익절 기준 설정 실패]\n• 사유: {msg}\n• 사용법: `tpr 5` (5% 도달 시 익절)"


def handle_slr_command(args: list[str]) -> str:
    """
    'slr' 명령어를 처리하여 손절 기준을 조회하거나 새로 설정합니다.
    양수/음수 중 어떤 값으로 입력하더라도 음수(-)로 전환하여 저장합니다.

    :param args: 명령어 뒤 인자 목록 (예: ['10'], ['-10'])
    :return: 텔레그램 회신 메시지 문자열
    """
    # 1. 인자가 없는 경우: 현재 설정된 손절 기준 안내
    if not args:
        current_slr = get_stop_loss_rate()
        return (
            "🛡️ [현재 손절 기준 (Stop Loss)]\n\n"
            f"• 설정 기준: {current_slr:g}% 도달 시 손절\n"
            "• 저장 위치: `config/data/settings.json`\n\n"
            "변경 방법:\n"
            "`slr {손절 기준}`\n"
            "• 예시: `slr 10` (-10% 도달 시 손절)\n"
            "• 예시: `slr -5` (-5% 도달 시 손절)\n"
            "💡 양수/음수 중 어떤 값으로 넣어도 음수(-)로 전환되어 저장됩니다."
        )

    rate_arg = args[0].strip()

    # 2. 손절 기준 검증 및 저장
    success, norm_rate, msg = set_stop_loss_rate(rate_arg)

    if success:
        return (
            "🛡️ [손절 기준(SLR) 설정 완료]\n\n"
            f"• 설정된 손절 기준: {norm_rate:g}%\n"
            f"• 손실률이 {norm_rate:g}% 도달 시 손절(시장가 매도)을 진행합니다.\n"
            "• 설정이 `config/data/settings.json`에 성공적으로 저장되었습니다."
        )
    else:
        return f"⚠️ [손절 기준 설정 실패]\n• 사유: {msg}\n• 사용법: `slr 10` (-10% 도달 시 손절)"


def handle_start_stls_command(args: list[str] | None = None) -> str:
    """
    'start stls' 명령어를 처리하여 스탑로스 백그라운드 감시 루프를 가동합니다.
    선택적으로 감시 주기(초)를 지정할 수 있습니다 (예: 'start stls 10').
    """
    interval = 10
    if args:
        # 혹시 'start stls 10' 형태에서 args가 ['stls', '10'] 이거나 ['10'] 일 수 있음
        for arg in args:
            clean = arg.strip()
            if clean.isdigit() and int(clean) > 0:
                interval = int(clean)
                break

    success, msg = stop_loss_watcher.start(interval=interval)
    if success:
        tpr = get_take_profit_rate()
        slr = get_stop_loss_rate()
        return (
            "🚀 [스탑로스 감시 시작]\n\n"
            f"• 상태: 가동 중 🟢 (감시 주기: {interval}초)\n"
            f"• 🎯 익절 기준 (TPR): +{tpr:g}% 도달 시 전량 시장가 매도\n"
            f"• 🛡️ 손절 기준 (SLR): {slr:g}% 도달 시 전량 시장가 매도\n"
            f"• 보유 종목 잔고(kt00018)를 {interval}초마다 동기화하여 감시합니다.\n\n"
            "중단하려면 `stop stls` 명령어를 입력하세요."
        )
    else:
        return msg


def handle_stop_stls_command(args: list[str] | None = None) -> str:
    """
    'stop stls' 명령어를 처리하여 스탑로스 백그라운드 감시 루프를 중단합니다.
    """
    success, msg = stop_loss_watcher.stop()
    return msg


def handle_stls_status_command(args: list[str] | None = None) -> str:
    """
    'stls' 명령어를 처리하여 현재 스탑로스 가동 상태 및 감시 중인 종목을 조회합니다.
    'stls start' 또는 'stls stop' 서브커맨드도 지원합니다.
    """
    if args:
        sub_cmd = args[0].strip().lower()
        if sub_cmd in ("start", "시작", "on"):
            return handle_start_stls_command(args[1:])
        elif sub_cmd in ("stop", "중단", "정지", "off"):
            return handle_stop_stls_command(args[1:])

    status = stop_loss_watcher.get_status()
    is_running = status["is_running"]
    interval = status["interval"]
    tpr = status["take_profit_rate"]
    slr = status["stop_loss_rate"]
    monitored_stocks = status["monitored_stocks"]
    last_check = status["last_checked_at"] or "미수행"
    last_error = status["last_error"]

    state_str = f"가동 중 🟢 ({interval}초 주기)" if is_running else "중지됨 ⚪"

    lines = [
        "📊 [스탑로스(Stop Loss) 현황]\n",
        f"• 감시 상태: {state_str}",
        f"• 🎯 익절 기준 (TPR): +{tpr:g}% 도달 시 매도",
        f"• 🛡️ 손절 기준 (SLR): {slr:g}% 도달 시 매도",
        f"• 최근 잔고 동기화 시각: {last_check}",
    ]

    if last_error:
        lines.append(f"• ⚠️ 최근 상태 메시지: {last_error}")

    lines.append("\n📋 **현재 감시 대상 보유 종목**")
    if not monitored_stocks:
        lines.append("• 감시 중인 보유 종목이 없습니다 (잔고 없음 또는 미수행).")
    else:
        for idx, item in enumerate(monitored_stocks, 1):
            nm = item.get("stock_name", "")
            cd = item.get("stock_code", "")
            qty = item.get("quantity", 0)
            tradable = item.get("tradable_quantity", qty)
            prft_rt = item.get("profit_rate", 0.0)
            cur_p = item.get("current_price", 0)
            pur_p = item.get("purchase_price", 0)

            sign = "+" if prft_rt > 0 else ""
            lines.append(
                f"{idx}. {nm} ({cd}) | {qty:,}주 (매매가능 {tradable:,}주)\n"
                f"   수익률: {sign}{prft_rt:.2f}% | 매입가 {pur_p:,}원 ➡️ 현재가 {cur_p:,}원"
            )

    lines.append("\n━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 **명령어 안내**")
    lines.append("• 감시 시작: `start stls` (또는 `start stls 10`)")
    lines.append("• 감시 중단: `stop stls`")
    lines.append(f"• 익절 기준 변경: `tpr {{퍼센트}}` (현재: +{tpr:g}%)")
    lines.append(f"• 손절 기준 변경: `slr {{퍼센트}}` (현재: {slr:g}%)")

    return "\n".join(lines)
