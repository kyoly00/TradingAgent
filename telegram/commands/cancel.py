"""
주식 주문 취소 명령어 처리 모듈:
'cancel {원주문번호} [취소수량]' 또는
'cancel {원주문번호} {종목코드} [취소수량]' 또는 'ccl pend' 명령어를 파싱하고
키움 kt10003 TR을 호출하여 취소 결과를 회신합니다.
종목코드가 생략되면 당일 미체결/주문 내역에서 주문번호로 자동 조회합니다.
"""

from api.order import cancel_order, get_orders


def _cancel_pending_orders() -> str:
    """현재 미체결 주문을 조회하고 각 주문의 남은 수량 전체를 취소합니다."""
    pending_result = get_orders(qry_tp="3")
    if not pending_result.get("success"):
        return (
            "❌ [미체결 주문 조회 실패]\n\n"
            f"• 사유: {pending_result.get('message', '알 수 없는 오류')}"
        )

    pending_orders = pending_result.get("orders", [])
    if not pending_orders:
        return "📋 현재 취소할 미체결 주문이 없습니다."

    # 동일 주문이 중복 반환되더라도 취소 요청은 한 번만 전송합니다.
    unique_orders = []
    seen_order_numbers = set()
    for item in pending_orders:
        order_number = str(item.get("ord_no") or "").strip()
        if order_number in seen_order_numbers:
            continue
        if order_number:
            seen_order_numbers.add(order_number)
        unique_orders.append(item)

    success_count = 0
    failure_count = 0
    result_lines = []

    for index, item in enumerate(unique_orders, start=1):
        order_number = str(item.get("ord_no") or "").strip()
        stock_code = str(item.get("stock_code") or "").strip()
        stock_name = str(item.get("stock_name") or "종목명 없음").strip()
        remaining_quantity = item.get("remn_qty", 0)
        exchange = str(item.get("exchange") or "KRX").strip().upper()
        if exchange not in ("KRX", "NXT", "SOR"):
            exchange = "KRX"

        if not order_number or not stock_code:
            failure_count += 1
            result_lines.append(
                f"❌ {index}. {stock_name} ({stock_code or '-'}) | "
                "주문번호 또는 종목코드 누락"
            )
            continue

        cancel_result = cancel_order(
            orig_ord_no=order_number,
            stock_code=stock_code,
            quantity=0,
            exchange=exchange,
        )

        if cancel_result.get("success"):
            success_count += 1
            cancel_order_number = cancel_result.get("ord_no") or "미발급"
            result_lines.append(
                f"✅ {index}. {stock_name} ({stock_code}) | 잔량 {remaining_quantity:,}주\n"
                f"   원주문: `{order_number}` → 취소접수: `{cancel_order_number}`"
            )
        else:
            failure_count += 1
            result_lines.append(
                f"❌ {index}. {stock_name} ({stock_code}) | 잔량 {remaining_quantity:,}주\n"
                f"   원주문: `{order_number}` | "
                f"사유: {cancel_result.get('message', '알 수 없는 오류')}"
            )

    lines = [
        "🚫 [미체결 주문 전체 취소 결과]",
        f"• 대상: {len(unique_orders)}건 | 성공: {success_count}건 | 실패: {failure_count}건",
        "",
        *result_lines,
    ]
    return "\n".join(lines)


def handle_cancel_command(args: list[str]) -> str:
    """
    'cancel' 명령어 인자를 분석하여 주문 취소(kt10003)를 실행합니다.

    :param args: 명령어 뒤에 오는 인자 목록
                 - ['pend'] -> 현재 미체결 주문의 잔량 전체 취소
                 - ['0000139'] -> 원주문번호 기준 잔량 전량 취소 (종목코드 자동 조회)
                 - ['0000139', '5'] -> 원주문번호 기준 5주 취소 (종목코드 자동 조회)
                 - ['0000139', '005930'] -> 기존 호환 (종목코드 지정, 전량 취소)
                 - ['0000139', '005930', '5'] -> 기존 호환 (종목코드 지정, 5주 취소)
    :return: 텔레그램으로 회신할 메시지 문자열
    """
    if args and args[0].strip().lower() in ("pend", "pending", "미체결"):
        if len(args) != 1:
            return "⚠️ 미체결 전체 취소 형식은 `ccl pend`입니다."
        return _cancel_pending_orders()

    if len(args) < 1:
        return (
            "ℹ️ [주문 취소 명령어 사용법]\n\n"
            "형식: `ccl pend` (현재 미체결 주문 전체 취소)\n"
            "형식: `cancel {원주문번호} [취소수량]`\n"
            "• 종목코드는 입력하지 않아도 당일 주문 내역에서 **자동으로 찾아 처리**합니다.\n"
            "• 취소수량을 생략하거나 `0`, `all`을 입력하면 **미체결 잔량 전부**를 취소합니다.\n\n"
            "사용 예시:\n"
            "• 미체결 주문 전체 취소: `ccl pend`\n"
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
