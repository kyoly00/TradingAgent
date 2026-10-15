"""
주식 매도 주문 명령어 처리 모듈:
'sell {종목코드} {수량}' (시장가 매도) 및
'sell {종목코드} {수량} {지정가}' (지정가 매도) 명령어를 파싱하고
키움 kt10001 TR을 호출하여 매도 주문을 접수하고 결과를 회신합니다.
"""

from api.order import sell_stock
from trading.liquidation import sell_all_holdings


def _format_sell_all_result(result: dict) -> str:
    """전체 매도 실행 결과를 텔레그램 메시지로 구성합니다."""
    if result.get("balance_error"):
        return (
            "❌ [전체 시장가 매도 실패]\n\n"
            f"• 잔고 조회 실패: {result['balance_error']}"
        )

    items = result.get("results") or []
    if not items:
        return "ℹ️ 현재 매도할 보유 종목이 없습니다."

    lines = [
        "💰 [보유 종목 전체 시장가 매도 결과]",
        "",
        f"• 주문 접수: {result.get('submitted_count', 0)}건",
        f"• 주문 실패: {result.get('failed_count', 0)}건",
        f"• 잔여 수량 존재: {result.get('unavailable_count', 0)}종목",
        "",
    ]
    for item in items:
        stock_label = item.get("stock_name") or item.get("stock_code")
        stock_code = item.get("stock_code") or "코드 없음"
        if item.get("success"):
            line = (
                f"✅ {stock_label} ({stock_code}) · "
                f"매도 {item.get('tradable_quantity', 0):,}주/"
                f"보유 {item.get('quantity', 0):,}주 · "
                f"주문번호 {item.get('ord_no') or '미발급'}"
            )
            unavailable_quantity = item.get("unavailable_quantity", 0)
            if unavailable_quantity > 0:
                line += f" · ⚠️ 주문 불가 잔여 {unavailable_quantity:,}주"
            lines.append(line)
        elif item.get("skipped"):
            lines.append(
                f"⚠️ {stock_label} ({stock_code}) · "
                f"매도 불가: {item.get('message', '주문 가능 수량 없음')}"
            )
        else:
            lines.append(
                f"❌ {stock_label} ({stock_code}) · "
                f"{item.get('tradable_quantity', 0):,}주 · "
                f"{item.get('message', '알 수 없는 오류')}"
            )
    return "\n".join(lines)


def handle_sell_command(args: list[str]) -> str:
    """
    'sell' 명령어 인자를 분석하여 시장가 또는 지정가 매도 주문을 실행합니다.

    :param args: 명령어 뒤에 오는 인자 목록
                 - ['all'] -> 모든 보유 종목의 주문 가능 수량 시장가 매도
                 - ['005930', '10'] -> 005930 종목 10주 시장가 매도
                 - ['005930', '10', '70000'] -> 005930 종목 10주 70,000원 지정가 매도
    :return: 텔레그램으로 회신할 메시지 문자열
    """
    if args and args[0].strip().lower() == "all":
        if len(args) != 1:
            return "⚠️ 전체 매도 형식은 `sell all`입니다."
        return _format_sell_all_result(sell_all_holdings())

    if len(args) < 2:
        return (
            "ℹ️ [주식 매도 주문 사용법]\n\n"
            "• 보유 종목 전체 시장가 매도:\n"
            "  `sell all`\n\n"
            "• 시장가 매도:\n"
            "  `sell {종목코드} {수량}`\n"
            "  예: `sell 005930 10` (삼성전자 10주 시장가 매도)\n\n"
            "• 지정가 매도:\n"
            "  `sell {종목코드} {수량} {지정가}`\n"
            "  예: `sell 005930 10 70000` (삼성전자 10주 70,000원 지정가 매도)"
        )

    stock_code = args[0].strip()
    qty_str = args[1].strip()

    # 1. 수량 유효성 검증
    try:
        quantity = int(qty_str)
        if quantity <= 0:
            return "⚠️ 매도 주문 수량은 1주 이상이어야 합니다."
    except ValueError:
        return f"⚠️ 매도 주문 수량이 올바른 숫자가 아닙니다: '{qty_str}'"

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

    # 3. 매도 주문 API 호출 (kt10001)
    result = sell_stock(stock_code=stock_code, quantity=quantity, price=price)

    # 4. 결과 메시지 구성
    order_type_str = result.get("order_type", "시장가")
    clean_code = result.get("stock_code", stock_code)
    ord_no = result.get("ord_no") or "미발급"
    price_display = f"{price:,}원" if price is not None else "시장가"

    if result.get("success"):
        return (
            f"💰 [매도 주문 접수 완료]\n\n"
            f"• 종목코드: {clean_code}\n"
            f"• 주문유형: {order_type_str}\n"
            f"• 주문수량: {quantity:,}주\n"
            f"• 주문단가: {price_display}\n"
            f"• 주문번호: {ord_no}\n"
            f"• 상태: {result.get('message', '매도주문 접수 완료')}"
        )
    else:
        return (
            f"❌ [매도 주문 실패]\n\n"
            f"• 종목코드: {clean_code}\n"
            f"• 주문유형: {order_type_str}\n"
            f"• 주문수량: {quantity:,}주\n"
            f"• 주문단가: {price_display}\n"
            f"• 실패사유: {result.get('message', '알 수 없는 오류')}"
        )
