"""
주식 주문 정정 명령어 처리 모듈:
'modify {원주문번호} {정정단가}' (잔량 전량 단가 변경),
'modify {원주문번호} {정정수량} {정정단가}' (일부 수량 단가 변경),
'modify {원주문번호} {종목코드} {정정수량} {정정단가}' (기존 호환)
명령어를 파싱하고 키움 kt10002 TR을 호출하여 정정 결과를 회신합니다.
종목코드가 생략되면 당일 미체결/주문 내역에서 주문번호로 자동 조회합니다.
"""

from api.order import modify_order


def handle_modify_command(args: list[str]) -> str:
    """
    'modify' 명령어 인자를 분석하여 주문 정정(kt10002)을 실행합니다.

    :param args: 명령어 뒤에 오는 인자 목록
                 - ['0000139', '71000'] -> 잔량 전량을 71,000원으로 정정 (종목코드 자동 조회)
                 - ['0000139', '5', '71000'] -> 5주를 71,000원으로 정정 (종목코드 자동 조회)
                 - ['0000139', '005930', '0', '71000'] -> 종목코드 지정, 전량 정정
                 - ['0000139', '005930', '5', '71000'] -> 종목코드 지정, 5주 정정
    :return: 텔레그램으로 회신할 메시지 문자열
    """
    if len(args) < 2:
        return (
            "ℹ️ [주문 정정 명령어 사용법]\n\n"
            "형식: `modify {원주문번호} [정정수량] {정정단가}`\n"
            "• 종목코드는 입력하지 않아도 당일 주문 내역에서 **자동으로 찾아 처리**합니다.\n"
            "• 정정수량을 생략하거나 `0`, `all`을 입력하면 **미체결 잔량 전부**를 정정합니다.\n\n"
            "사용 예시:\n"
            "• 잔량 전량 단가 변경: `modify 0000139 71000`\n"
            "• 일부(5주) 단가 변경: `modify 0000139 5 71000`\n"
            "• 종목코드 직접 지정: `modify 0000139 005930 0 71000`\n\n"
            "💡 주문번호 확인은 `orders` 명령어로 가능합니다."
        )

    orig_ord_no = args[0].strip()
    stock_code = ""
    quantity = 0

    if len(args) == 2:
        # modify {원주문번호} {정정단가} -> 잔량 전량 정정
        price_str = args[1].strip()
    elif len(args) == 3:
        # modify {원주문번호} {정정수량} {정정단가}
        qty_str = args[1].strip().lower()
        price_str = args[2].strip()
        if qty_str in ("0", "all", "전체", "잔량"):
            quantity = 0
        else:
            try:
                quantity = int(qty_str)
                if quantity < 0:
                    return "⚠️ 정정 수량은 0(전량) 이상이어야 합니다."
            except ValueError:
                return f"⚠️ 정정 수량이 올바른 숫자가 아닙니다: '{args[1]}'"
    else:
        # len(args) >= 4: modify {원주문번호} {종목코드} {정정수량} {정정단가}
        stock_code = args[1].strip()
        qty_str = args[2].strip().lower()
        price_str = args[3].strip()
        if qty_str in ("0", "all", "전체", "잔량"):
            quantity = 0
        else:
            try:
                quantity = int(qty_str)
                if quantity < 0:
                    return "⚠️ 정정 수량은 0(전량) 이상이어야 합니다."
            except ValueError:
                return f"⚠️ 정정 수량이 올바른 숫자가 아닙니다: '{args[2]}'"

    # 정정 단가 검증
    try:
        price = int(price_str)
        if price <= 0:
            return "⚠️ 정정 단가는 0원보다 커야 합니다."
    except ValueError:
        return f"⚠️ 정정 단가가 올바른 숫자가 아닙니다: '{price_str}'"

    # 정정 API 호출 (kt10002)
    result = modify_order(
        orig_ord_no=orig_ord_no,
        stock_code=stock_code,
        quantity=quantity,
        price=price,
    )

    clean_code = result.get("stock_code") or stock_code or "자동조회"
    qty_disp = "전량(잔량 전부)" if quantity == 0 else f"{quantity:,}주"
    price_disp = f"{price:,}원"

    if result.get("success"):
        new_ord_no = result.get("ord_no") or "미발급"
        base_no = result.get("base_orig_ord_no") or orig_ord_no
        return (
            f"✏️ [주문 정정 접수 완료]\n\n"
            f"• 원주문번호: `{base_no}`\n"
            f"• 신규주문번호: `{new_ord_no}`\n"
            f"• 종목코드: `{clean_code}`\n"
            f"• 정정수량: {qty_disp}\n"
            f"• 정정단가: {price_disp}\n"
            f"• 상태: {result.get('message', '정상 접수')}"
        )
    else:
        return (
            f"❌ [주문 정정 실패]\n\n"
            f"• 원주문번호: `{orig_ord_no}`\n"
            f"• 종목코드: `{clean_code}`\n"
            f"• 정정수량: {qty_disp}\n"
            f"• 정정단가: {price_disp}\n"
            f"• 실패사유: {result.get('message', '알 수 없는 오류')}"
        )
