"""
계좌 정보 조회 API 모듈:
tr_docs/kt00018.json 명세를 기반으로 계좌평가잔고내역(kt00018)을 요청하여
총매입금액, 총평가금액, 총평가손익, 총수익률, 추정예탁자산 및 보유 종목 잔고 리스트를 반환합니다.
"""

from api.auth import session_manager
from api.http_queue import http_client
from utils.logger import log_error, log_info

TR_ID_KT00018 = "kt00018"
ENDPOINT_ACCOUNT_BALANCE = "/api/dostk/acnt"


def _parse_int(val_str: str | None) -> int:
    """0-padding 및 부호가 포함된 문자열을 안전하게 정수로 변환합니다."""
    if not val_str:
        return 0
    try:
        clean = str(val_str).strip().replace(",", "")
        # 부호 판별
        sign = -1 if clean.startswith("-") else 1
        clean = clean.lstrip("+-").lstrip("0")
        if not clean:
            return 0
        return sign * int(clean)
    except (ValueError, TypeError):
        return 0


def _parse_float(val_str: str | None) -> float:
    """수익률 등 소수점/부호/퍼센트 문자열을 안전하게 실수로 변환합니다."""
    if not val_str:
        return 0.0
    try:
        clean = str(val_str).strip().replace("%", "").replace(",", "")
        if not clean:
            return 0.0
        return float(clean)
    except (ValueError, TypeError):
        return 0.0



def _clean_stock_code(raw_code: str | None) -> str:
    """종목코드의 접두어(A: 주식, J: ELW, Q: ETN 등)를 정리하여 6자리 코드로 변환합니다."""
    if not raw_code:
        return ""
    code = raw_code.strip()
    if len(code) > 6 and code[0] in ("A", "J", "Q"):
        return code[1:]
    return code


def get_account_balance(qry_tp: str = "1", exchange: str = "KRX") -> dict:
    """
    키움 REST API kt00018 TR을 호출하여 계좌 평가 잔고 및 보유 종목 내역을 조회합니다.

    :param qry_tp: 조회구분 ("1": 합산, "2": 개별)
    :param exchange: 거래소 구분 ("KRX", "NXT")
    :return: 결과 딕셔너리
             {
                 'success': bool,
                 'tot_pur_amt': int,          # 총매입금액 (원)
                 'tot_evlt_amt': int,         # 총평가금액 (원)
                 'tot_evlt_pl': int,          # 총평가손익 (원)
                 'tot_prft_rt': float,        # 총수익률 (%)
                 'prsm_dpst_aset_amt': int,   # 추정예탁자산 (원)
                 'holdings': list[dict],      # 보유 종목 리스트
                 'error': str | None,
                 'raw_data': dict
             }
    """
    # 1. 로그인 세션 검증
    if not session_manager.is_authenticated():
        return {
            "success": False,
            "error": "로그인된 세션이 없거나 토큰이 만료되었습니다. 먼저 'login paper' 또는 'login real'을 실행해 주세요.",
            "raw_data": {},
        }

    host = session_manager.host
    url = f"{host}{ENDPOINT_ACCOUNT_BALANCE}"

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": session_manager.authorization_header,
        "cont-yn": "N",
        "next-key": "",
        "api-id": TR_ID_KT00018,
    }

    body = {
        "qry_tp": qry_tp,
        "dmst_stex_tp": exchange,
    }

    try:
        response = http_client.post(url, headers=headers, json=body, timeout=10)
        data = response.json()

        return_code = data.get("return_code")
        return_msg = data.get("return_msg", "")

        is_success = (response.status_code == 200) and (str(return_code) == "0")

        if is_success:
            raw_holdings = data.get("acnt_evlt_remn_indv_tot") or []
            holdings = []

            for item in raw_holdings:
                stk_cd = _clean_stock_code(item.get("stk_cd"))
                stk_nm = (item.get("stk_nm") or "").strip()
                rmnd_qty = _parse_int(item.get("rmnd_qty"))
                trde_able_qty = _parse_int(item.get("trde_able_qty"))
                pur_pric = _parse_int(item.get("pur_pric"))
                cur_prc = _parse_int(item.get("cur_prc"))
                profit_rate = _parse_float(item.get("prft_rt"))

                # 보정: 만약 profit_rate가 0.0인데 pur_pric과 cur_prc가 유효하게 존재하고 다를 때 계산값 활용
                if profit_rate == 0.0 and pur_pric > 0 and cur_prc > 0 and cur_prc != pur_pric:
                    profit_rate = round(((cur_prc - pur_pric) / pur_pric) * 100, 2)

                # 보유수량이 0 이상인 실제 보유 종목만 필터링
                if rmnd_qty > 0 or stk_nm:
                    holdings.append({
                        "stock_code": stk_cd,
                        "stock_name": stk_nm,
                        "quantity": rmnd_qty,
                        "tradable_quantity": trde_able_qty,
                        "purchase_price": pur_pric,
                        "current_price": cur_prc,
                        "profit_rate": profit_rate,
                        "eval_profit": _parse_int(item.get("evltv_prft")),
                        "eval_amount": _parse_int(item.get("evlt_amt")),
                    })


            return {
                "success": True,
                "tot_pur_amt": _parse_int(data.get("tot_pur_amt")),
                "tot_evlt_amt": _parse_int(data.get("tot_evlt_amt")),
                "tot_evlt_pl": _parse_int(data.get("tot_evlt_pl")),
                "tot_prft_rt": _parse_float(data.get("tot_prft_rt")),
                "prsm_dpst_aset_amt": _parse_int(data.get("prsm_dpst_aset_amt")),
                "holdings": holdings,
                "error": None,
                "raw_data": data,
            }
        else:
            err_msg = return_msg or data.get("error_description") or f"오류 코드: {return_code}"
            log_error(f"kt00018 잔고 조회 실패 (코드 {return_code}): {err_msg}")
            return {
                "success": False,
                "error": err_msg,
                "raw_data": data,
            }
    except Exception as e:
        log_error(f"kt00018 API 호출 중 예외 발생: {e}")
        return {
            "success": False,
            "error": f"네트워크 또는 API 호출 오류: {str(e)}",
            "raw_data": {},
        }
