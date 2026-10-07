"""
주식 매수 주문 명령어 처리 모듈:
'buy {종목코드} {수량}' (시장가 매수) 및
'buy {종목코드} {수량} {지정가}' (지정가 매수),
'buy {종목코드} max {금액}' (예산 내 최대 수량 시장가 매수) 명령어를 파싱하고
키움 kt10000 TR을 호출하여 결과를 회신합니다.
"""

from decimal import Decimal, InvalidOperation

from api.order import buy_stock
from api.stock_info import get_stock_info
from utils.logger import log_error, log_info


def _parse_positive_int(value: str) -> int:
    """쉼표가 포함될 수 있는 양의 정수 문자열을 변환합니다."""
    parsed = int(value.replace(",", "").strip())
    if parsed <= 0:
        raise ValueError
    return parsed


def _parse_current_price(value: object) -> int:
    """ka10001의 부호 포함 현재가 문자열을 양의 정수로 변환합니다."""
    if value is None:
        raise ValueError

    clean_value = str(value).replace(",", "").strip()
    if not clean_value:
        raise ValueError

    # ka10001 현재가는 등락 방향에 따라 +/- 부호가 붙을 수 있습니다.
    try:
        numeric_price = Decimal(clean_value)
    except InvalidOperation as exc:
        raise ValueError from exc

    if not numeric_price.is_finite() or numeric_price != numeric_price.to_integral_value():
        raise ValueError

    current_price = abs(int(numeric_price))
    if current_price <= 0:
        raise ValueError
    return current_price


def _handle_max_amount_buy(stock_code: str, amount_str: str) -> str:
    """현재가를 기준으로 예산 내 최대 주문 수량을 계산해 시장가 매수합니다."""
    try:
        max_amount = _parse_positive_int(amount_str)
    except (TypeError, ValueError):
        return f"⚠️ 최대 매수 금액이 올바른 양의 정수가 아닙니다: '{amount_str}'"

    stock_info = get_stock_info(stock_code)
    if not stock_info.get("success"):
        reason = stock_info.get("error") or "알 수 없는 오류"
        log_error(f"[최대 금액 매수 현재가 조회 실패] 종목: {stock_code}, 사유: {reason}")
        return (
            "❌ [최대 금액 매수 실패]\n\n"
            f"• 종목코드: {stock_code}\n"
            f"• 실패사유: 현재가 조회 실패 - {reason}"
        )

    try:
        current_price = _parse_current_price(stock_info.get("cur_prc"))
    except (TypeError, ValueError):
        raw_price = stock_info.get("cur_prc")
        log_error(
            f"[최대 금액 매수 현재가 파싱 실패] 종목: {stock_code}, 현재가: {raw_price!r}"
        )
        return (
            "❌ [최대 금액 매수 실패]\n\n"
            f"• 종목코드: {stock_code}\n"
            "• 실패사유: 조회된 현재가가 올바르지 않습니다."
        )

    quantity = max_amount // current_price
    if quantity <= 0:
        log_info(
            f"[최대 금액 매수 불가] 종목: {stock_code}, 최대금액: {max_amount:,}원, "
            f"조회 현재가: {current_price:,}원"
        )
        return (
            "⚠️ 지정한 금액이 현재가보다 낮아 매수할 수 없습니다.\n\n"
            f"• 최대금액: {max_amount:,}원\n"
            f"• 현재가: {current_price:,}원"
        )

    estimated_amount = current_price * quantity
    clean_code = stock_info.get("stk_cd") or stock_code
    stock_name = stock_info.get("stk_nm") or "종목명 미확인"

    log_info(
        f"[최대 금액 매수 계산] 종목: {clean_code}, 최대금액: {max_amount:,}원, "
        f"조회 현재가: {current_price:,}원, 주문수량: {quantity:,}주, "
        f"예상 주문금액: {estimated_amount:,}원"
    )
    result = buy_stock(stock_code=stock_code, quantity=quantity, price=None)
    result_code = result.get("stock_code") or clean_code
    order_number = result.get("ord_no") or "미발급"

    if result.get("success"):
        log_info(
            f"[최대 금액 매수 접수 완료] 종목: {result_code}, 수량: {quantity:,}주, "
            f"현재가 기준 예상금액: {estimated_amount:,}원, 주문번호: {order_number}"
        )
        return (
            "🛒 [최대 금액 매수 주문 접수 완료]\n\n"
            f"• 종목: {stock_name} ({result_code})\n"
            "• 주문유형: 시장가\n"
            f"• 최대금액: {max_amount:,}원\n"
            f"• 조회 현재가: {current_price:,}원\n"
            f"• 주문수량: {quantity:,}주\n"
            f"• 현재가 기준 예상금액: {estimated_amount:,}원\n"
            f"• 주문번호: {order_number}\n"
            f"• 상태: {result.get('message', '정상 접수')}\n\n"
            "※ 시장가 주문이므로 실제 체결금액은 달라질 수 있습니다."
        )

    reason = result.get("message", "알 수 없는 오류")
    log_error(
        f"[최대 금액 매수 주문 실패] 종목: {result_code}, 수량: {quantity:,}주, "
        f"현재가 기준 예상금액: {estimated_amount:,}원, 사유: {reason}"
    )
    return (
        "❌ [최대 금액 매수 주문 실패]\n\n"
        f"• 종목: {stock_name} ({result_code})\n"
        "• 주문유형: 시장가\n"
        f"• 최대금액: {max_amount:,}원\n"
        f"• 조회 현재가: {current_price:,}원\n"
        f"• 주문수량: {quantity:,}주\n"
        f"• 현재가 기준 예상금액: {estimated_amount:,}원\n"
        f"• 실패사유: {reason}"
    )


def handle_buy_command(args: list[str]) -> str:
    """
    'buy' 명령어 인자를 분석하여 수량 기반 또는 최대 금액 기반 매수 주문을 실행합니다.

    :param args: 명령어 뒤에 오는 인자 목록
                 - ['005930', '10'] -> 005930 종목 10주 시장가 매수
                 - ['005930', '10', '70000'] -> 005930 종목 10주 70,000원 지정가 매수
                 - ['005930', 'max', '1000000'] -> 100만 원 내 최대 수량 시장가 매수
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
            "  예: `buy 005930 10 70000` (삼성전자 10주 70,000원 지정가 매수)\n\n"
            "• 최대 금액 시장가 매수:\n"
            "  `buy {종목코드} max {금액}`\n"
            "  예: `buy 005930 max 1000000` (100만 원 내 최대 수량 매수)"
        )

    stock_code = args[0].strip()
    qty_str = args[1].strip()

    if qty_str.lower() == "max":
        if len(args) != 3:
            return (
                "⚠️ 최대 금액 매수 형식이 올바르지 않습니다.\n"
                "• 형식: `buy {종목코드} max {금액}`\n"
                "• 예시: `buy 005930 max 1000000`"
            )
        return _handle_max_amount_buy(stock_code, args[2].strip())

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
