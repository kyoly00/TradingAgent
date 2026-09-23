"""
주식 매수 주문 명령어 처리 모듈:
'buy {종목코드} {수량}' (시장가 매수) 및
'buy {종목코드} {수량} {지정가}' (지정가 매수) 명령어를 파싱하고
키움 kt10000 TR을 호출하여 결과를 회신합니다.
"""

from api.order import buy_stock


def handle_buy_command(args: list[str]) -> str:
    """
    'buy' 명령어 인자를 분석하여 시장가 또는 지정가 매수 주문을 실행합니다.

    :param args: 명령어 뒤에 오는 인자 목록
                 - ['005930', '10'] -> 005930 종목 10주 시장가 매수
                 - ['005930', '10', '70000'] -> 005930 종목 10주 70,000원 지정가 매수
    :return: 텔레그램으로 회신할 메시지 문자열
    """
    if len(args) < 2:
        return (
            "ℹ️ [주식 매수 주문 사용법]\n\n"
            "• 시장가 매수:\n"
            "  `buy {종목코드} {수량}`\n"
            "  예: `buy 005930 10` (삼성전자 10주 시장가 매수)\n\n"
            "• 지정가 매수:\n"
            "  `buy {종목코드} {수량} {지정가}`\n"
            "  예: `buy 005930 10 70000` (삼성전자 10주 70,000원 지정가 매수)"
        )

    stock_code = args[0].strip()
    qty_str = args[1].strip()

    # 1. 수량 유효성 검증
    try:
        quantity = int(qty_str)
        if quantity <= 0:
            return "⚠️ 주문 수량은 1주 이상이어야 합니다."
    except ValueError:
        return f"⚠️ 주문 수량이 올바른 숫자가 아닙니다: '{qty_str}'"

    # 2. 지정가 가격 유효성 검증 (3번째 인자가 있는 경우)
    price: int | None = None
    if len(args) >= 3:
        price_str = args[2].strip()
        try:
            price = int(price_str)
            if price <= 0:
                return "⚠️ 지정가 주문 단가는 0원보다 커야 합니다."
        except ValueError:
            return f"⚠️ 지정가 단가가 올바른 숫자가 아닙니다: '{price_str}'"

    # 3. 매수 주문 API 호출 (kt10000)
    result = buy_stock(stock_code=stock_code, quantity=quantity, price=price)

    # 4. 결과 메시지 구성
    order_type_str = result.get("order_type", "시장가")
    clean_code = result.get("stock_code", stock_code)
    ord_no = result.get("ord_no") or "미발급"
    price_display = f"{price:,}원" if price is not None else "시장가"

    if result.get("success"):
        return (
            f"🛒 [매수 주문 접수 완료]\n\n"
            f"• 종목코드: {clean_code}\n"
            f"• 주문유형: {order_type_str}\n"
            f"• 주문수량: {quantity:,}주\n"
            f"• 주문단가: {price_display}\n"
            f"• 주문번호: {ord_no}\n"
            f"• 상태: {result.get('message', '정상 접수')}"
        )
    else:
        return (
            f"❌ [매수 주문 실패]\n\n"
            f"• 종목코드: {clean_code}\n"
            f"• 주문유형: {order_type_str}\n"
            f"• 주문수량: {quantity:,}주\n"
            f"• 주문단가: {price_display}\n"
            f"• 실패사유: {result.get('message', '알 수 없는 오류')}"
        )
