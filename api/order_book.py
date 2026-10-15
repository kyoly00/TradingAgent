"""주식호가요청(ka10004) API 호출 및 매수호가 정규화 모듈."""

from api.auth import session_manager
from api.http_queue import http_client
from utils.logger import log_error

TR_ID_KA10004 = "ka10004"
ENDPOINT_MARKET_CONDITION = "/api/dostk/mrkcond"

BUY_PRICE_FIELDS = (
    "buy_fpr_bid",
    "buy_2th_pre_bid",
    "buy_3th_pre_bid",
    "buy_4th_pre_bid",
    "buy_5th_pre_bid",
    "buy_6th_pre_bid",
    "buy_7th_pre_bid",
    "buy_8th_pre_bid",
    "buy_9th_pre_bid",
    "buy_10th_pre_bid",
)


def _parse_price(value: object) -> int:
    """부호와 쉼표가 포함될 수 있는 호가 문자열을 양의 정수로 변환합니다."""
    clean_value = str(value if value is not None else "").replace(",", "").strip()
    if not clean_value:
        return 0
    try:
        return abs(int(clean_value))
    except (TypeError, ValueError):
        return 0


def get_order_book(stock_code: str) -> dict:
    """종목의 1~10차 매수호가를 조회합니다."""
    if not session_manager.is_authenticated():
        return {
            "success": False,
            "stock_code": stock_code,
            "buy_prices": [],
            "error": "로그인된 세션이 없거나 토큰이 만료되었습니다.",
            "raw_data": {},
        }

    clean_code = str(stock_code).strip()
    if clean_code.isdigit() and len(clean_code) < 6:
        clean_code = clean_code.zfill(6)

    url = f"{session_manager.host}{ENDPOINT_MARKET_CONDITION}"
    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": session_manager.authorization_header,
        "cont-yn": "N",
        "next-key": "",
        "api-id": TR_ID_KA10004,
    }

    try:
        response = http_client.post(
            url,
            headers=headers,
            json={"stk_cd": clean_code},
            timeout=10,
        )
        data = response.json()
        return_code = data.get("return_code")
        return_msg = data.get("return_msg", "")
        if response.status_code != 200 or str(return_code) != "0":
            error = (
                return_msg
                or data.get("error_description")
                or f"오류 코드: {return_code}"
            )
            log_error(f"ka10004 요청 실패 (종목 {clean_code}): {error}")
            return {
                "success": False,
                "stock_code": clean_code,
                "buy_prices": [],
                "error": error,
                "raw_data": data,
            }

        buy_prices = [_parse_price(data.get(field)) for field in BUY_PRICE_FIELDS]
        return {
            "success": True,
            "stock_code": clean_code,
            "buy_prices": buy_prices,
            "error": None,
            "raw_data": data,
        }
    except Exception as exc:
        log_error(f"ka10004 API 호출 중 예외 발생 (종목 {clean_code}): {exc}")
        return {
            "success": False,
            "stock_code": clean_code,
            "buy_prices": [],
            "error": f"네트워크 또는 API 호출 오류: {exc}",
            "raw_data": {},
        }
