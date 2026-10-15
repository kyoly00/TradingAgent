"""보유 종목 일괄 청산 실행 로직."""

from api.account import get_account_balance
from api.order import sell_stock
from utils.logger import log_error, log_info


def sell_all_holdings() -> dict:
    """현재 보유 종목의 주문 가능 수량을 각각 시장가로 매도합니다."""
    balance_result = get_account_balance()
    if not balance_result.get("success"):
        error = balance_result.get("error") or "잔고 조회 중 알 수 없는 오류가 발생했습니다."
        log_error(f"[전체 매도 실패] 잔고 조회 실패: {error}")
        return {
            "success": False,
            "balance_error": error,
            "results": [],
            "submitted_count": 0,
            "failed_count": 0,
            "unavailable_count": 0,
        }

    results = []
    for holding in balance_result.get("holdings") or []:
        stock_code = str(holding.get("stock_code") or "").strip()
        stock_name = str(holding.get("stock_name") or "").strip()
        try:
            quantity = max(0, int(holding.get("quantity") or 0))
            raw_tradable_quantity = max(
                0,
                int(holding.get("tradable_quantity") or 0),
            )
        except (TypeError, ValueError):
            quantity = 0
            raw_tradable_quantity = 0

        if not stock_code or quantity <= 0:
            continue

        tradable_quantity = min(quantity, raw_tradable_quantity)
        unavailable_quantity = quantity - tradable_quantity

        if tradable_quantity <= 0:
            results.append({
                "success": False,
                "skipped": True,
                "stock_code": stock_code,
                "stock_name": stock_name,
                "quantity": quantity,
                "tradable_quantity": 0,
                "unavailable_quantity": quantity,
                "ord_no": None,
                "message": "주문 가능 수량이 없습니다.",
            })
            continue

        order_result = sell_stock(
            stock_code=stock_code,
            quantity=tradable_quantity,
            price=None,
        )
        results.append({
            "success": bool(order_result.get("success")),
            "skipped": False,
            "stock_code": order_result.get("stock_code") or stock_code,
            "stock_name": stock_name,
            "quantity": quantity,
            "tradable_quantity": tradable_quantity,
            "unavailable_quantity": unavailable_quantity,
            "ord_no": order_result.get("ord_no"),
            "message": order_result.get("message") or "알 수 없는 결과",
        })

    submitted_count = sum(1 for item in results if item["success"])
    unavailable_count = sum(
        1 for item in results if item.get("unavailable_quantity", 0) > 0
    )
    failed_count = sum(
        1 for item in results if not item["success"] and not item["skipped"]
    )
    if results:
        log_info(
            "[전체 매도 처리 완료] "
            f"접수 {submitted_count}건, 실패 {failed_count}건, 매도 불가 {unavailable_count}건"
        )

    return {
        "success": failed_count == 0 and unavailable_count == 0,
        "balance_error": None,
        "results": results,
        "submitted_count": submitted_count,
        "failed_count": failed_count,
        "unavailable_count": unavailable_count,
    }
