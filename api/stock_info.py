"""
주식기본정보요청(ka10001) API 호출 모듈:
tr_docs/ka10001.json 명세를 기반으로 종목코드를 전달받아
키움 REST API(/api/dostk/stkinfo)를 호출하여 종목의 현재가, 거래량, 시가, 고가, 저가, 전일대비 등을 조회합니다.
"""

from api.auth import session_manager
from api.http_queue import http_client
from utils.logger import log_error, log_info

TR_ID_KA10001 = "ka10001"
ENDPOINT_STOCK_INFO = "/api/dostk/stkinfo"


def get_stock_info(stock_code: str) -> dict:
    """
    주어진 종목 코드에 해당하는 주식 기본 정보를 조회합니다.

    :param stock_code: 6자리 주식 종목코드 (예: '005930')
    :return: 조회 결과 딕셔너리
             {
                 'success': bool,
                 'stk_cd': str,
                 'stk_nm': str,
                 'cur_prc': str,
                 'trde_qty': str,
                 'open_pric': str,
                 'high_pric': str,
                 'low_pric': str,
                 'pred_pre': str,
                 'flu_rt': str,
                 'pre_sig': str,
                 'error': str | None,
                 'raw_data': dict
             }
    """
    # 1. 로그인 세션 및 토큰 유효성 검사
    if not session_manager.is_authenticated():
        return {
            "success": False,
            "error": "로그인된 세션이 없거나 토큰이 만료되었습니다. 먼저 'login paper' 또는 'login real'을 실행해 주세요.",
            "raw_data": {},
        }

    # 종목코드 표준화 (공백 제거 및 숫자형 6자리 미만 시 zfill)
    clean_code = stock_code.strip()
    if clean_code.isdigit() and len(clean_code) < 6:
        clean_code = clean_code.zfill(6)

    host = session_manager.host
    url = f"{host}{ENDPOINT_STOCK_INFO}"

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": session_manager.authorization_header,
        "cont-yn": "N",
        "next-key": "",
        "api-id": TR_ID_KA10001,
    }

    body = {
        "stk_cd": clean_code,
    }

    try:
        response = http_client.post(url, headers=headers, json=body, timeout=10)
        data = response.json()

        return_code = data.get("return_code")
        return_msg = data.get("return_msg", "")

        # 키움 TR 표준 성공 판정: HTTP 200 및 return_code == 0
        if response.status_code == 200 and str(return_code) == "0":
            return {
                "success": True,
                "stk_cd": data.get("stk_cd", clean_code),
                "stk_nm": data.get("stk_nm", "").strip(),
                "cur_prc": data.get("cur_prc", "0"),
                "trde_qty": data.get("trde_qty", "0"),
                "open_pric": data.get("open_pric", "0"),
                "high_pric": data.get("high_pric", "0"),
                "low_pric": data.get("low_pric", "0"),
                "pred_pre": data.get("pred_pre", "0"),
                "flu_rt": data.get("flu_rt", "0"),
                "pre_sig": data.get("pre_sig", "3"),
                "error": None,
                "raw_data": data,
            }
        else:
            err_msg = return_msg or data.get("error_description") or f"오류 코드: {return_code}"
            log_error(f"ka10001 요청 실패 (코드 {return_code}): {err_msg}")
            return {
                "success": False,
                "stk_cd": clean_code,
                "error": err_msg,
                "raw_data": data,
            }
    except Exception as e:
        log_error(f"ka10001 API 호출 중 예외 발생: {e}")
        return {
            "success": False,
            "stk_cd": clean_code,
            "error": f"네트워크 또는 API 호출 오류: {str(e)}",
            "raw_data": {},
        }
