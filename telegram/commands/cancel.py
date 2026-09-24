"""
주식 주문 취소 명령어 처리 모듈:
'cancel {원주문번호} [취소수량]' 또는
'cancel {원주문번호} {종목코드} [취소수량]' 명령어를 파싱하고
키움 kt10003 TR을 호출하여 취소 결과를 회신합니다.
종목코드가 생략되면 당일 미체결/주문 내역에서 주문번호로 자동 조회합니다.
"""

from api.order import cancel_order


def handle_cancel_command(args: list[str]) -> str:
    """
    'cancel' 명령어 인자를 분석하여 주문 취소(kt10003)를 실행합니다.

    :param args: 명령어 뒤에 오는 인자 목록
                 - ['0000139'] -> 원주문번호 기준 잔량 전량 취소 (종목코드 자동 조회)
                 - ['0000139', '5'] -> 원주문번호 기준 5주 취소 (종목코드 자동 조회)
                 - ['0000139', '005930'] -> 기존 호환 (종목코드 지정, 전량 취소)
                 - ['0000139', '005930', '5'] -> 기존 호환 (종목코드 지정, 5주 취소)
    :return: 텔레그램으로 회신할 메시지 문자열
    """
    if len(args) < 1:
        return (
            "ℹ️ [주문 취소 명령어 사용법]\n\n"
            "형식: `cancel {원주문번호} [취소수량]`\n"
            "• 종목코드는 입력하지 않아도 당일 주문 내역에서 **자동으로 찾아 처리**합니다.\n"
            "• 취소수량을 생략하거나 `0`, `all`을 입력하면 **미체결 잔량 전부**를 취소합니다.\n\n"
            "사용 예시:\n"
            "• 잔량 전량 취소: `cancel 0000139`\n"
            "• 일부(5주)만 취소: `cancel 0000139 5`\n"
            "• 종목코드 직접 지정: `cancel 0000139 005930`\n\n"
            "💡 주문번호 확인은 `orders` 명령어로 가능합니다."
        )

    orig_ord_no = args[0].strip()
    stock_code = ""
    quantity = 0

    if len(args) == 1:
        # cancel {원주문번호} -> 전량 취소, 종목코드 자동 조회
        pass
    elif len(args) == 2:
        second = args[1].strip().lower()
        if second in ("all", "전체", "잔량", "0"):
            quantity = 0
        elif second.isdigit() and len(second) == 6:
            # 6자리 숫자 종목코드인 경우 (예: cancel 0000139 005930)
            stock_code = second
        else:
            try:
                quantity = int(second)
                if quantity < 0:
                    return "⚠️ 취소 수량은 0(전량) 이상이어야 합니다."
            except ValueError:
                # 숫자가 아닌 문자열이면 종목코드로 인식
                stock_code = second
    else:
        # len(args) >= 3: cancel {원주문번호} {종목코드} {취소수량}
        stock_code = args[1].strip()
        qty_str = args[2].strip().lower()
        if qty_str in ("all", "전체", "잔량", "0"):
            quantity = 0
        else:
            try:
                quantity = int(qty_str)
                if quantity < 0:
                    return "⚠️ 취소 수량은 0(전량) 이상이어야 합니다."
            except ValueError:
                return f"⚠️ 취소 수량이 올바른 숫자가 아닙니다: '{args[2]}'"

    # 주문 취소 API 호출 (kt10003)
    result = cancel_order(
        orig_ord_no=orig_ord_no,
        stock_code=stock_code,
        quantity=quantity,
    )

    clean_code = result.get("stock_code") or stock_code or "자동조회"
    qty_disp = "전량(잔량 전부)" if quantity == 0 else f"{quantity:,}주"

    if result.get("success"):
        new_ord_no = result.get("ord_no") or "미발급"
        base_no = result.get("base_orig_ord_no") or orig_ord_no
        return (
            f"🚫 [주문 취소 접수 완료]\n\n"
            f"• 원주문번호: `{base_no}`\n"
            f"• 취소접수번호: `{new_ord_no}`\n"
            f"• 종목코드: `{clean_code}`\n"
            f"• 취소수량: {qty_disp}\n"
            f"• 상태: {result.get('message', '정상 접수')}"
        )
    else:
        return (
            f"❌ [주문 취소 실패]\n\n"
            f"• 원주문번호: `{orig_ord_no}`\n"
            f"• 종목코드: `{clean_code}`\n"
            f"• 취소수량: {qty_disp}\n"
            f"• 실패사유: {result.get('message', '알 수 없는 오류')}"
        )
