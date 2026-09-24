"""
명령어 라우팅 및 디스패처 모듈:
수신된 텔레그램 메시지에서 공백 제거 및 소문자 변환을 거쳐
해당하는 명령어 핸들러로 전달합니다.
"""

from .login import handle_login_command
from .status import handle_status_command
from .power import handle_power_command
from .search import handle_search_command
from .buy import handle_buy_command
from .sell import handle_sell_command
from .orders import handle_orders_command
from .modify import handle_modify_command
from .cancel import handle_cancel_command
from .report import handle_report_command
from .market_hours import handle_mkhr_command
from .settings_status import handle_stts_command
from .reservation import handle_rsv_command
from .stop_loss import (
    handle_tpr_command,
    handle_slr_command,
    handle_start_stls_command,
    handle_stop_stls_command,
    handle_stls_status_command,
)
from .help import handle_help_command



def dispatch_command(raw_text: str, chat_id: int | str | None = None) -> tuple[str, bool]:
    """
    수신된 텍스트 메시지의 앞뒤 공백을 제거하고 대소문자를 구분하지 않고 파싱하여
    해당 명령어 핸들러로 라우팅합니다.

    :param raw_text: 수신된 원본 메시지 문자열
    :param chat_id: 메시지를 보낸 채팅방 ID
    :return: (처리 결과 및 회신 메시지 문자열, 종료 요청 여부 bool)
    """
    if not raw_text:
        return "", False

    # 앞뒤 공백 제거 및 소문자 변환
    normalized = raw_text.strip().lower()

    if not normalized:
        return "", False

    # 공백 단위로 토큰 분리
    tokens = normalized.split()
    cmd = tokens[0]
    args = tokens[1:]

    # '/'로 시작하는 슬래시 명령어 지원 (/login, /status, /srch, /buy, /sell, /orders, /modify, /cancel, /report, /r, /mkhr, /stts, /rsv 등)
    if cmd.startswith("/"):
        cmd = cmd[1:]

    # 1. 종료 명령어 ('power off')
    if cmd == "power":
        reply, should_exit = handle_power_command(args)
        return reply, should_exit

    # 2. 로그인 및 갱신 명령어 ('login paper', 'login real', 'login renewal ...')
    if cmd == "login":
        reply = handle_login_command(args, chat_id=chat_id)
        return reply, False

    # 3. 상태 확인 명령어 ('status')
    if cmd in ("status", "상태"):
        return handle_status_command(args), False

    # 4. 종목 조회 명령어 ('srch {종목코드}', 'search {종목코드}')
    if cmd in ("srch", "search", "조회"):
        reply = handle_search_command(args)
        return reply, False

    # 5. 종목 매수 명령어 ('buy {종목코드} {수량} [지정가]')
    if cmd in ("buy", "매수"):
        reply = handle_buy_command(args)
        return reply, False

    # 6. 종목 매도 명령어 ('sell {종목코드} {수량} [지정가]')
    if cmd in ("sell", "매도"):
        reply = handle_sell_command(args)
        return reply, False

    # 7. 주문 체결/미체결 내역 확인 ('orders', 'orders all', '주문', '미체결')
    if cmd in ("orders", "order", "주문", "주문확인", "미체결"):
        reply = handle_orders_command(args)
        return reply, False

    # 8. 주문 정정 명령어 ('modify {원주문번호} {종목코드} {수량} {정정단가}')
    if cmd in ("modify", "정정", "변경"):
        reply = handle_modify_command(args)
        return reply, False

    # 9. 주문 취소 명령어 ('cancel {원주문번호} {종목코드} [취소수량]')
    if cmd in ("cancel", "취소"):
        reply = handle_cancel_command(args)
        return reply, False

    # 10. 계좌 자산 및 잔고 조회 명령어 ('report', 'r', '리포트', '잔고')
    if cmd in ("report", "r", "리포트", "잔고", "자산"):
        reply = handle_report_command(args)
        return reply, False

    # 11. 장 운영 시간 설정 명령어 ('mkhr {시작시간} {종료시간}')
    if cmd in ("mkhr", "장시간"):
        reply = handle_mkhr_command(args)
        return reply, False

    # 12. 스탑로스 시작/중단 명령어 ('start stls', 'stop stls')
    if cmd == "start" and args and args[0] in ("stls", "스탑로스", "stoploss"):
        reply = handle_start_stls_command(args[1:])
        return reply, False

    if cmd == "stop" and args and args[0] in ("stls", "스탑로스", "stoploss"):
        reply = handle_stop_stls_command(args[1:])
        return reply, False

    # 13. 스탑로스 상태 및 조작 명령어 ('stls', 'stls start', 'stls stop')
    if cmd in ("stls", "스탑로스", "stoploss"):
        reply = handle_stls_status_command(args)
        return reply, False

    # 14. 익절 기준 설정 명령어 ('tpr {익절기준}')
    if cmd in ("tpr", "익절"):
        reply = handle_tpr_command(args)
        return reply, False

    # 15. 손절 기준 설정 명령어 ('slr {손절기준}')
    if cmd in ("slr", "손절"):
        reply = handle_slr_command(args)
        return reply, False

    # 16. 전체 설정값 확인 명령어 ('stts')
    if cmd in ("stts", "settings", "설정"):
        reply = handle_stts_command(args)
        return reply, False

    # 17. 명령어 예약 실행 ('rsv ...')
    if cmd in ("rsv", "예약"):
        reply = handle_rsv_command(args)
        return reply, False

    # 18. 도움말 및 명령어 안내 ('help', 'command', 'commands', 'start', '도움말', '명령어')
    if cmd in ("help", "command", "commands", "cmd", "cmds", "start", "도움말", "명령어"):
        reply = handle_help_command(args)
        return reply, False

    # 19. 알 수 없는 명령어
    unknown_text = (
        f"❓ 알 수 없는 명령어입니다: '{tokens[0]}'\n\n"
        "사용 가능한 명령어:\n"
        "• `start stls` [주기] : 스탑로스 실시간 감시 시작 (기본 10초 주기)\n"
        "• `stop stls` : 스탑로스 실시간 감시 중단\n"
        "• `stls` : 스탑로스 감시 현황 및 보유 종목 확인\n"
        "• `tpr {익절기준}` : 익절 기준 퍼센티지 설정 (예: tpr 5 -> +5% 도달 시 익절)\n"
        "• `slr {손절기준}` : 손절 기준 퍼센티지 설정 (예: slr 10 -> -10% 도달 시 손절)\n"
        "• `orders` [all] : 주문 체결/미체결 내역 확인\n"
        "• `modify {원주문번호} [수량] {단가}` : 주문 정정 (예: modify 0000139 71000)\n"
        "• `cancel {원주문번호} [수량]` : 주문 취소 (예: cancel 0000139)\n"
        "• `buy {종목코드} {수량} [지정가]` : 종목 매수 주문\n"
        "• `sell {종목코드} {수량} [지정가]` : 종목 매도 주문\n"
        "• `report` 또는 `r` : 계좌 자산 및 보유 종목 조회\n"
        "• `srch {종목코드}` : 종목 정보 조회\n"
        "• `rsv {시간} {명령어}` : 명령어 예약 실행 (매일 평일 반복)\n"
        "• `rsv once {시간} {명령어}` : 1회성 명령어 예약 실행\n"
        "• `rsv list` : 예약 목록 확인 | `rsv remove {번호}` : 예약 삭제\n"
        "• `mkhr {시작} {종료}` : 장 운영 시간 설정\n"
        "• `stts` : 전체 시스템 설정값 확인\n"
        "• `login paper` : 모의투자 로그인\n"
        "• `login real` : 실전투자 로그인\n"
        "• `login renewal {시간}` : 토큰 갱신 시간 설정\n"
        "• `status` : 현재 상태 확인\n"
        "• `power off` : 프로그램 종료\n"
        "• `/help` 또는 `/command` : 명령어 사용법 보기"
    )
    return unknown_text, False


