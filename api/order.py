"""
주식 주문 API 호출 모듈:
tr_docs/kt10000.json 명세를 기반으로 국내주식 매수 주문(kt10000)을 요청합니다.
시장가(trde_tp='3') 및 지정가(trde_tp='0') 매수를 지원합니다.
"""

import requests
from api.auth import session_manager
from utils.logger import log_error, log_info

TR_ID_KT10000 = "kt10000"
TR_ID_KT10001 = "kt10001"
ENDPOINT_ORDER = "/api/dostk/ordr"


def buy_stock(
    stock_code: str,
    quantity: int,
    price: int | None = None,
    exchange: str = "KRX",
) -> dict:
    """
    국내주식 매수 주문(kt10000)을 실행합니다.

    :param stock_code: 6자리 종목코드 (예: '005930')
    :param quantity: 주문 수량 (1주 이상)
    :param price: 지정가 주문 시 주문 단가 (원), None인 경우 시장가 주문
    :param exchange: 거래소 구분 ('KRX', 'NXT', 'SOR', 기본값: 'KRX')
    :return: 결과 딕셔너리
             {
                 'success': bool,
                 'ord_no': str | None,
                 'stock_code': str,
                 'order_type': str,  # '시장가' 또는 '지정가'
                 'quantity': int,
                 'price': int | None,
                 'message': str,
                 'raw_data': dict
             }
    """
    # 1. 로그인 세션 검증
    if not session_manager.is_authenticated():
        return {
            "success": False,
            "ord_no": None,
            "stock_code": stock_code,
            "order_type": "시장가" if price is None else "지정가",
            "quantity": quantity,
            "price": price,
            "message": "로그인된 세션이 없거나 토큰이 만료되었습니다. 먼저 'login paper' 또는 'login real'을 실행해 주세요.",
            "raw_data": {},
        }

    # 종목코드 표준화 (숫자 6자리 미만 시 zfill)
    clean_code = stock_code.strip()
    if clean_code.isdigit() and len(clean_code) < 6:
        clean_code = clean_code.zfill(6)

    # 매매구분(trde_tp) 및 단가 설정:
    # 3: 시장가, 0: 보통(지정가)
    if price is None:
        trde_tp = "3"  # 시장가
        ord_uv = ""
        order_type_desc = "시장가"
    else:
        trde_tp = "0"  # 보통 (지정가)
        ord_uv = str(price)
        order_type_desc = "지정가"

    host = session_manager.host
    url = f"{host}{ENDPOINT_ORDER}"

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": session_manager.authorization_header,
        "cont-yn": "N",
        "next-key": "",
        "api-id": TR_ID_KT10000,
    }

    body = {
        "dmst_stex_tp": exchange,
        "stk_cd": clean_code,
        "ord_qty": str(quantity),
        "ord_uv": ord_uv,
        "trde_tp": trde_tp,
        "cond_uv": "",
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=10)
        data = response.json()

        return_code = data.get("return_code")
        return_msg = data.get("return_msg", "")
        ord_no = data.get("ord_no", "")

        is_success = (response.status_code == 200) and (str(return_code) == "0")

        if is_success:
            log_info(
                f"[매수 성공] 종목: {clean_code}, 유형: {order_type_desc}, 수량: {quantity:,}주, "
                f"단가: {f'{price:,}원' if price is not None else '시장가'}, 주문번호: {ord_no}"
            )
            return {
                "success": True,
                "ord_no": ord_no,
                "stock_code": clean_code,
                "order_type": order_type_desc,
                "quantity": quantity,
                "price": price,
                "message": return_msg or "정상적으로 처리되었습니다.",
                "raw_data": data,
            }
        else:
            err_msg = return_msg or data.get("error_description") or f"오류 코드: {return_code}"
            log_error(f"[매수 실패] 종목: {clean_code}, 코드: {return_code}, 사유: {err_msg}")
            return {
                "success": False,
                "ord_no": None,
                "stock_code": clean_code,
                "order_type": order_type_desc,
                "quantity": quantity,
                "price": price,
                "message": err_msg,
                "raw_data": data,
            }
    except Exception as e:
        log_error(f"[매수 요청 예외] 종목: {clean_code}, 오류: {e}")
        return {
            "success": False,
            "ord_no": None,
            "stock_code": clean_code,
            "order_type": order_type_desc,
            "quantity": quantity,
            "price": price,
            "message": f"네트워크 또는 API 호출 오류: {str(e)}",
            "raw_data": {},
        }


def sell_stock(
    stock_code: str,
    quantity: int,
    price: int | None = None,
    exchange: str = "KRX",
) -> dict:
    """
    국내주식 매도 주문(kt10001)을 실행합니다.

    :param stock_code: 6자리 종목코드 (예: '005930')
    :param quantity: 주문 수량 (1주 이상)
    :param price: 지정가 주문 시 주문 단가 (원), None인 경우 시장가 주문
    :param exchange: 거래소 구분 ('KRX', 'NXT', 'SOR', 기본값: 'KRX')
    :return: 결과 딕셔너리
             {
                 'success': bool,
                 'ord_no': str | None,
                 'stock_code': str,
                 'order_type': str,  # '시장가' 또는 '지정가'
                 'quantity': int,
                 'price': int | None,
                 'message': str,
                 'raw_data': dict
             }
    """
    # 1. 로그인 세션 검증
    if not session_manager.is_authenticated():
        return {
            "success": False,
            "ord_no": None,
            "stock_code": stock_code,
            "order_type": "시장가" if price is None else "지정가",
            "quantity": quantity,
            "price": price,
            "message": "로그인된 세션이 없거나 토큰이 만료되었습니다. 먼저 'login paper' 또는 'login real'을 실행해 주세요.",
            "raw_data": {},
        }

    # 종목코드 표준화 (숫자 6자리 미만 시 zfill)
    clean_code = stock_code.strip()
    if clean_code.isdigit() and len(clean_code) < 6:
        clean_code = clean_code.zfill(6)

    # 매매구분(trde_tp) 및 단가 설정:
    # 3: 시장가, 0: 보통(지정가)
    if price is None:
        trde_tp = "3"  # 시장가
        ord_uv = ""
        order_type_desc = "시장가"
    else:
        trde_tp = "0"  # 보통 (지정가)
        ord_uv = str(price)
        order_type_desc = "지정가"

    host = session_manager.host
    url = f"{host}{ENDPOINT_ORDER}"

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": session_manager.authorization_header,
        "cont-yn": "N",
        "next-key": "",
        "api-id": TR_ID_KT10001,
    }

    body = {
        "dmst_stex_tp": exchange,
        "stk_cd": clean_code,
        "ord_qty": str(quantity),
        "ord_uv": ord_uv,
        "trde_tp": trde_tp,
        "cond_uv": "",
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=10)
        data = response.json()

        return_code = data.get("return_code")
        return_msg = data.get("return_msg", "")
        ord_no = data.get("ord_no", "")

        is_success = (response.status_code == 200) and (str(return_code) == "0")

        if is_success:
            log_info(
                f"[매도 성공] 종목: {clean_code}, 유형: {order_type_desc}, 수량: {quantity:,}주, "
                f"단가: {f'{price:,}원' if price is not None else '시장가'}, 주문번호: {ord_no}"
            )
            return {
                "success": True,
                "ord_no": ord_no,
                "stock_code": clean_code,
                "order_type": order_type_desc,
                "quantity": quantity,
                "price": price,
                "message": return_msg or "매도주문이 완료되었습니다.",
                "raw_data": data,
            }
        else:
            err_msg = return_msg or data.get("error_description") or f"오류 코드: {return_code}"
            log_error(f"[매도 실패] 종목: {clean_code}, 코드: {return_code}, 사유: {err_msg}")
            return {
                "success": False,
                "ord_no": None,
                "stock_code": clean_code,
                "order_type": order_type_desc,
                "quantity": quantity,
                "price": price,
                "message": err_msg,
                "raw_data": data,
            }
    except Exception as e:
        log_error(f"[매도 요청 예외] 종목: {clean_code}, 오류: {e}")
        return {
            "success": False,
            "ord_no": None,
            "stock_code": clean_code,
            "order_type": order_type_desc,
            "quantity": quantity,
            "price": price,
            "message": f"네트워크 또는 API 호출 오류: {str(e)}",
            "raw_data": {},
        }

