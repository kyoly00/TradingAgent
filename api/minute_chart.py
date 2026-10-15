"""키움 주식분봉차트조회요청(ka10080) API 호출 모듈."""

from datetime import datetime

from api.auth import session_manager
from api.http_queue import http_client
from utils.logger import log_error

TR_ID_KA10080 = "ka10080"
ENDPOINT_CHART = "/api/dostk/chart"
SUPPORTED_MINUTE_SCOPES = {1, 3, 5, 10, 15, 30, 45, 60}


def _parse_price(value: object) -> int:
    """부호와 쉼표가 포함된 가격을 양의 정수로 변환합니다."""
    clean_value = str(value or "").strip().replace(",", "")
    if not clean_value:
        return 0
    try:
        return abs(int(clean_value))
    except (TypeError, ValueError):
        return 0


def get_minute_chart(
    stock_code: str,
    minute_scope: int = 1,
    limit: int | None = None,
) -> dict:
    """종목의 과거 분봉을 시간 오름차순으로 조회합니다."""
    clean_code = str(stock_code).strip()
    if not session_manager.is_authenticated():
        return {
            "success": False,
            "stock_code": clean_code,
            "bars": [],
            "error": "로그인된 세션이 없거나 토큰이 만료되었습니다.",
        }

    if minute_scope not in SUPPORTED_MINUTE_SCOPES:
        return {
            "success": False,
            "stock_code": clean_code,
            "bars": [],
            "error": f"지원하지 않는 분봉 범위입니다: {minute_scope}",
        }

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": session_manager.authorization_header,
        "cont-yn": "N",
        "next-key": "",
        "api-id": TR_ID_KA10080,
    }
    body = {
        "stk_cd": clean_code,
        "tic_scope": str(minute_scope),
        "upd_stkpc_tp": "1",
        "base_dt": datetime.now().strftime("%Y%m%d"),
    }

    try:
        response = http_client.post(
            f"{session_manager.host}{ENDPOINT_CHART}",
            headers=headers,
            json=body,
            timeout=10,
        )
        data = response.json()
        return_code = data.get("return_code")
        if response.status_code != 200 or str(return_code) != "0":
            error = (
                data.get("return_msg")
                or data.get("error_description")
                or f"오류 코드: {return_code}"
            )
            log_error(f"[ka10080 분봉 조회 실패] 종목: {clean_code}, 사유: {error}")
            return {
                "success": False,
                "stock_code": clean_code,
                "bars": [],
                "error": error,
            }

        bars_by_minute: dict[str, dict] = {}
        for row in data.get("stk_min_pole_chart_qry") or []:
            timestamp = str(row.get("cntr_tm") or "").strip()
            price = _parse_price(row.get("cur_prc"))
            if len(timestamp) < 12 or price <= 0:
                continue
            minute_key = timestamp[:12]
            bars_by_minute[minute_key] = {
                "timestamp": minute_key,
                "close": price,
            }

        bars = [bars_by_minute[key] for key in sorted(bars_by_minute)]
        if limit is not None and limit > 0:
            bars = bars[-limit:]

        return {
            "success": True,
            "stock_code": data.get("stk_cd") or clean_code,
            "bars": bars,
            "error": None,
        }
    except Exception as exc:
        log_error(f"[ka10080 분봉 조회 예외] 종목: {clean_code}, 오류: {exc}")
        return {
            "success": False,
            "stock_code": clean_code,
            "bars": [],
            "error": f"네트워크 또는 API 호출 오류: {exc}",
        }
