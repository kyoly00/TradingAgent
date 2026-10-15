"""
주식 주문 API 호출 모듈:
tr_docs/kt10000.json 명세를 기반으로 국내주식 매수 주문(kt10000)을 요청합니다.
시장가(trde_tp='3') 및 지정가(trde_tp='0') 매수를 지원합니다.
"""

from api.auth import session_manager
from api.account import get_account_balance
from api.http_queue import http_client
from utils.logger import log_error, log_info
from utils.settings import (
    get_max_holding_count,
    get_stock_buy_cooldown,
    record_stock_sale,
)

TR_ID_KT10000 = "kt10000"
TR_ID_KT10001 = "kt10001"
TR_ID_KT10002 = "kt10002"
TR_ID_KT10003 = "kt10003"
TR_ID_KT00007 = "kt00007"
ENDPOINT_ORDER = "/api/dostk/ordr"
ENDPOINT_ACCOUNT = "/api/dostk/acnt"


def _format_cooldown_remaining(remaining_seconds: int) -> str:
    """쿨다운 잔여 초를 읽기 쉬운 시간·분 문자열로 변환합니다."""
    hours, remainder = divmod(max(0, remaining_seconds), 3600)
    minutes = (remainder + 59) // 60
    if minutes == 60:
        hours += 1
        minutes = 0
    if hours and minutes:
        return f"약 {hours}시간 {minutes}분"
    if hours:
        return f"약 {hours}시간"
    return f"약 {max(1, minutes)}분"


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

    cooldown_blocked, remaining_seconds, sold_at = get_stock_buy_cooldown(
        clean_code,
        account_scope=str(session_manager.mode or ""),
    )
    if cooldown_blocked:
        sold_at_text = sold_at.strftime("%Y-%m-%d %H:%M:%S") if sold_at else "정보 없음"
        return {
            "success": False,
            "ord_no": None,
            "stock_code": clean_code,
            "order_type": "시장가" if price is None else "지정가",
            "quantity": quantity,
            "price": price,
            "cooldown_blocked": True,
            "remaining_seconds": remaining_seconds,
            "message": (
                "최근 매도된 종목으로 재매수 쿨다운이 적용 중입니다. "
                f"남은 시간: {_format_cooldown_remaining(remaining_seconds)} "
                f"(매도 감지: {sold_at_text})"
            ),
            "raw_data": {},
        }

    max_holding_count = get_max_holding_count()
    if max_holding_count > 0:
        balance_result = get_account_balance()
        if not balance_result.get("success"):
            return {
                "success": False,
                "ord_no": None,
                "stock_code": clean_code,
                "order_type": "시장가" if price is None else "지정가",
                "quantity": quantity,
                "price": price,
                "max_holdings_blocked": True,
                "message": (
                    "최대 보유 종목 수 확인을 위한 잔고 조회에 실패하여 "
                    f"매수 주문을 중단했습니다: {balance_result.get('error') or '알 수 없는 오류'}"
                ),
                "raw_data": {},
            }

        held_codes = set()
        for item in balance_result.get("holdings") or []:
            try:
                holding_quantity = int(item.get("quantity") or 0)
            except (TypeError, ValueError):
                continue
            holding_code = str(item.get("stock_code") or "").strip()
            if holding_quantity > 0 and holding_code:
                held_codes.add(holding_code)
        if clean_code not in held_codes and len(held_codes) >= max_holding_count:
            return {
                "success": False,
                "ord_no": None,
                "stock_code": clean_code,
                "order_type": "시장가" if price is None else "지정가",
                "quantity": quantity,
                "price": price,
                "max_holdings_blocked": True,
                "holding_count": len(held_codes),
                "max_holding_count": max_holding_count,
                "message": (
                    f"최대 보유 종목 수({max_holding_count}개)에 도달하여 "
                    "새로운 종목을 매수할 수 없습니다."
                ),
                "raw_data": {},
            }

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
        response = http_client.post(url, headers=headers, json=body, timeout=10)
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
        response = http_client.post(url, headers=headers, json=body, timeout=10)
        data = response.json()

        return_code = data.get("return_code")
        return_msg = data.get("return_msg", "")
        ord_no = data.get("ord_no", "")

        is_success = (response.status_code == 200) and (str(return_code) == "0")

        if is_success:
            if price is None and not record_stock_sale(
                clean_code,
                account_scope=str(session_manager.mode or ""),
            ):
                log_error(f"[매도 쿨다운 기록 실패] 종목: {clean_code}")
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


def _parse_int(val_str: str | None) -> int:
    """0-padding 및 부호가 포함된 문자열을 안전하게 정수로 변환합니다."""
    if not val_str:
        return 0
    try:
        clean = str(val_str).strip()
        sign = -1 if clean.startswith("-") else 1
        clean = clean.lstrip("+-").lstrip("0")
        if not clean:
            return 0
        return sign * int(clean)
    except (ValueError, TypeError):
        return 0


def _clean_stock_code(raw_code: str | None) -> str:
    """종목코드의 접두어(A: 주식, J: ELW, Q: ETN 등)를 정리하여 6자리 코드로 변환합니다."""
    if not raw_code:
        return ""
    code = str(raw_code).strip()
    if len(code) > 6 and code[0] in ("A", "J", "Q"):
        return code[1:]
    return code


def get_orders(
    qry_tp: str = "3",
    stock_code: str = "",
    order_date: str = "",
    sell_tp: str = "0",
    exchange: str = "%",
    fr_ord_no: str = "",
) -> dict:
    """
    계좌별 주문체결내역상세(kt00007)를 조회합니다.

    :param qry_tp: 조회구분 ("1": 주문순, "2": 역순, "3": 미체결, "4": 체결내역만, 기본값: "3")
    :param stock_code: 종목코드 (빈 문자열이면 전체 조회)
    :param order_date: 주문일자 YYYYMMDD (빈 문자열이면 당일)
    :param sell_tp: 매도수구분 ("0": 전체, "1": 매도, "2": 매수, 기본값: "0")
    :param exchange: 거래소구분 ("%", "KRX", "NXT", "SOR", 기본값: "%")
    :param fr_ord_no: 시작주문번호 (빈 문자열이면 전체)
    :return: 결과 딕셔너리
             {
                 'success': bool,
                 'orders': list[dict],
                 'message': str,
                 'raw_data': dict
             }
    """
    if not session_manager.is_authenticated():
        return {
            "success": False,
            "orders": [],
            "message": "로그인된 세션이 없거나 토큰이 만료되었습니다. 먼저 'login paper' 또는 'login real'을 실행해 주세요.",
            "raw_data": {},
        }

    clean_code = stock_code.strip()
    if clean_code.isdigit() and len(clean_code) < 6:
        clean_code = clean_code.zfill(6)

    host = session_manager.host
    url = f"{host}{ENDPOINT_ACCOUNT}"

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": session_manager.authorization_header,
        "cont-yn": "N",
        "next-key": "",
        "api-id": TR_ID_KT00007,
    }

    body = {
        "ord_dt": order_date.strip(),
        "qry_tp": qry_tp,
        "stk_bond_tp": "0",  # 전체
        "sell_tp": sell_tp,
        "stk_cd": clean_code,
        "fr_ord_no": fr_ord_no.strip(),
        "dmst_stex_tp": exchange,
    }

    try:
        response = http_client.post(url, headers=headers, json=body, timeout=10)
        data = response.json()

        return_code = data.get("return_code")
        return_msg = data.get("return_msg", "")

        is_success = (response.status_code == 200) and (str(return_code) == "0")

        if is_success:
            raw_list = data.get("acnt_ord_cntr_prps_dtl", [])
            orders = []
            for item in raw_list:
                normalized_order = {
                    "ord_no": item.get("ord_no", "").strip(),
                    "orig_ord_no": item.get("ori_ord", "").strip(),
                    "stock_code": _clean_stock_code(item.get("stk_cd")),
                    "stock_name": item.get("stk_nm", "").strip(),
                    "order_type": item.get("trde_tp", "").strip(),
                    "io_type": item.get("io_tp_nm", "").strip(),
                    "order_qty": _parse_int(item.get("ord_qty")),
                    "order_price": _parse_int(item.get("ord_uv")),
                    "cntr_qty": _parse_int(item.get("cntr_qty")),
                    "cntr_price": _parse_int(item.get("cntr_uv")),
                    "remn_qty": _parse_int(item.get("ord_remnq")),
                    "order_time": item.get("ord_tm", "").strip(),
                    "modify_cancel": item.get("mdfy_cncl", "").strip(),
                    "exchange": item.get("dmst_stex_tp", "").strip(),
                }
                # 모의투자 kt00007은 미체결 조회에서도 잔량 0인 체결·취소
                # 이력을 반환할 수 있으므로 실제 주문잔량이 있는 항목만 노출합니다.
                if str(qry_tp).strip() == "3" and normalized_order["remn_qty"] <= 0:
                    continue
                orders.append(normalized_order)

            log_info(f"[주문 내역 조회 성공] 조회구분: {qry_tp}, 건수: {len(orders)}건")
            return {
                "success": True,
                "orders": orders,
                "message": return_msg or "조회가 완료되었습니다.",
                "raw_data": data,
            }
        else:
            err_msg = return_msg or data.get("error_description") or f"오류 코드: {return_code}"
            log_error(f"[주문 내역 조회 실패] 코드: {return_code}, 사유: {err_msg}")
            return {
                "success": False,
                "orders": [],
                "message": err_msg,
                "raw_data": data,
            }
    except Exception as e:
        log_error(f"[주문 내역 조회 예외] 오류: {e}")
        return {
            "success": False,
            "orders": [],
            "message": f"네트워크 또는 API 호출 오류: {str(e)}",
            "raw_data": {},
        }


def find_stock_code_by_ord_no(orig_ord_no: str) -> str | None:
    """
    원주문번호를 기반으로 당일 주문 내역(미체결 우선)에서 종목코드를 자동으로 조회합니다.
    """
    if not orig_ord_no:
        return None
    clean_no = orig_ord_no.strip().lstrip("0")
    if not clean_no:
        return None

    # 1. 미체결 주문 우선 검색
    pending_res = get_orders(qry_tp="3")
    if pending_res.get("success"):
        for item in pending_res.get("orders", []):
            item_no = item.get("ord_no", "").strip().lstrip("0")
            if item_no == clean_no:
                return item.get("stock_code")

    # 2. 당일 전체 주문(역순)에서 검색
    all_res = get_orders(qry_tp="2")
    if all_res.get("success"):
        for item in all_res.get("orders", []):
            item_no = item.get("ord_no", "").strip().lstrip("0")
            if item_no == clean_no:
                return item.get("stock_code")

    return None


def modify_order(
    orig_ord_no: str,
    stock_code: str = "",
    quantity: int = 0,
    price: int = 0,
    exchange: str = "KRX",
) -> dict:
    """
    국내주식 주문 정정(kt10002)을 실행합니다.
    종목코드(stock_code)가 빈 문자열인 경우, 당일 주문 내역에서 주문번호로 자동 조회합니다.

    :param orig_ord_no: 원주문번호 (7자리 문자열 또는 숫자)
    :param stock_code: 6자리 종목코드 (생략 시 주문번호로 자동 탐색)
    :param quantity: 정정 수량 (0 입력 시 잔량 전부 정정, 기본값: 0)
    :param price: 정정 단가 (원)
    :param exchange: 거래소 구분 ('KRX', 'NXT', 'SOR', 기본값: 'KRX')
    :return: 결과 딕셔너리
    """
    if not session_manager.is_authenticated():
        return {
            "success": False,
            "ord_no": None,
            "base_orig_ord_no": orig_ord_no,
            "stock_code": stock_code,
            "quantity": quantity,
            "price": price,
            "message": "로그인된 세션이 없거나 토큰이 만료되었습니다. 먼저 'login paper' 또는 'login real'을 실행해 주세요.",
            "raw_data": {},
        }

    clean_code = stock_code.strip()
    if not clean_code:
        auto_code = find_stock_code_by_ord_no(orig_ord_no)
        if not auto_code:
            return {
                "success": False,
                "ord_no": None,
                "base_orig_ord_no": orig_ord_no,
                "stock_code": "",
                "quantity": quantity,
                "price": price,
                "message": f"주문번호({orig_ord_no})에 해당하는 종목을 당일 주문 내역에서 찾을 수 없습니다. 종목코드를 함께 입력해 주세요.",
                "raw_data": {},
            }
        clean_code = auto_code

    if clean_code.isdigit() and len(clean_code) < 6:
        clean_code = clean_code.zfill(6)

    clean_ord_no = orig_ord_no.strip()
    if clean_ord_no.isdigit() and len(clean_ord_no) < 7:
        clean_ord_no = clean_ord_no.zfill(7)

    host = session_manager.host
    url = f"{host}{ENDPOINT_ORDER}"

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": session_manager.authorization_header,
        "cont-yn": "N",
        "next-key": "",
        "api-id": TR_ID_KT10002,
    }

    body = {
        "dmst_stex_tp": exchange,
        "orig_ord_no": clean_ord_no,
        "stk_cd": clean_code,
        "mdfy_qty": str(quantity),
        "mdfy_uv": str(price),
        "mdfy_cond_uv": "",
    }

    try:
        response = http_client.post(url, headers=headers, json=body, timeout=10)
        data = response.json()

        return_code = data.get("return_code")
        return_msg = data.get("return_msg", "")
        new_ord_no = data.get("ord_no", "")
        base_no = data.get("base_orig_ord_no", clean_ord_no)

        is_success = (response.status_code == 200) and (str(return_code) == "0")

        if is_success:
            log_info(
                f"[주문 정정 성공] 원주문: {clean_ord_no}, 신규주문: {new_ord_no}, 종목: {clean_code}, "
                f"수량: {'전량' if quantity == 0 else f'{quantity:,}주'}, 단가: {price:,}원"
            )
            return {
                "success": True,
                "ord_no": new_ord_no,
                "base_orig_ord_no": base_no,
                "stock_code": clean_code,
                "quantity": quantity,
                "price": price,
                "message": return_msg or "정정주문이 완료되었습니다.",
                "raw_data": data,
            }
        else:
            err_msg = return_msg or data.get("error_description") or f"오류 코드: {return_code}"
            log_error(f"[주문 정정 실패] 원주문: {clean_ord_no}, 코드: {return_code}, 사유: {err_msg}")
            return {
                "success": False,
                "ord_no": None,
                "base_orig_ord_no": clean_ord_no,
                "stock_code": clean_code,
                "quantity": quantity,
                "price": price,
                "message": err_msg,
                "raw_data": data,
            }
    except Exception as e:
        log_error(f"[주문 정정 예외] 원주문: {clean_ord_no}, 오류: {e}")
        return {
            "success": False,
            "ord_no": None,
            "base_orig_ord_no": clean_ord_no,
            "stock_code": clean_code,
            "quantity": quantity,
            "price": price,
            "message": f"네트워크 또는 API 호출 오류: {str(e)}",
            "raw_data": {},
        }


def cancel_order(
    orig_ord_no: str,
    stock_code: str = "",
    quantity: int = 0,
    exchange: str = "KRX",
) -> dict:
    """
    국내주식 주문 취소(kt10003)를 실행합니다.
    종목코드(stock_code)가 빈 문자열인 경우, 당일 주문 내역에서 주문번호로 자동 조회합니다.

    :param orig_ord_no: 원주문번호 (7자리 문자열 또는 숫자)
    :param stock_code: 6자리 종목코드 (생략 시 주문번호로 자동 탐색)
    :param quantity: 취소 수량 (0 입력 시 잔량 전부 취소, 기본값: 0)
    :param exchange: 거래소 구분 ('KRX', 'NXT', 'SOR', 기본값: 'KRX')
    :return: 결과 딕셔너리
    """
    if not session_manager.is_authenticated():
        return {
            "success": False,
            "ord_no": None,
            "base_orig_ord_no": orig_ord_no,
            "stock_code": stock_code,
            "quantity": quantity,
            "cancelled_quantity": 0,
            "message": "로그인된 세션이 없거나 토큰이 만료되었습니다. 먼저 'login paper' 또는 'login real'을 실행해 주세요.",
            "raw_data": {},
        }

    clean_code = stock_code.strip()
    if not clean_code:
        auto_code = find_stock_code_by_ord_no(orig_ord_no)
        if not auto_code:
            return {
                "success": False,
                "ord_no": None,
                "base_orig_ord_no": orig_ord_no,
                "stock_code": "",
                "quantity": quantity,
                "cancelled_quantity": 0,
                "message": f"주문번호({orig_ord_no})에 해당하는 종목을 당일 주문 내역에서 찾을 수 없습니다. 종목코드를 함께 입력해 주세요.",
                "raw_data": {},
            }
        clean_code = auto_code

    if clean_code.isdigit() and len(clean_code) < 6:
        clean_code = clean_code.zfill(6)

    clean_ord_no = orig_ord_no.strip()
    if clean_ord_no.isdigit() and len(clean_ord_no) < 7:
        clean_ord_no = clean_ord_no.zfill(7)

    host = session_manager.host
    url = f"{host}{ENDPOINT_ORDER}"

    headers = {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": session_manager.authorization_header,
        "cont-yn": "N",
        "next-key": "",
        "api-id": TR_ID_KT10003,
    }

    body = {
        "dmst_stex_tp": exchange,
        "orig_ord_no": clean_ord_no,
        "stk_cd": clean_code,
        "cncl_qty": str(quantity),
    }

    try:
        response = http_client.post(url, headers=headers, json=body, timeout=10)
        data = response.json()

        return_code = data.get("return_code")
        return_msg = data.get("return_msg", "")
        new_ord_no = data.get("ord_no", "")
        base_no = data.get("base_orig_ord_no", clean_ord_no)
        cancelled_quantity = _parse_int(data.get("cncl_qty"))

        is_success = (response.status_code == 200) and (str(return_code) == "0")

        if is_success:
            log_info(
                f"[주문 취소 성공] 원주문: {clean_ord_no}, 신규취소접수번호: {new_ord_no}, 종목: {clean_code}, "
                f"취소수량: {'전량' if quantity == 0 else f'{quantity:,}주'}"
            )
            return {
                "success": True,
                "ord_no": new_ord_no,
                "base_orig_ord_no": base_no,
                "stock_code": clean_code,
                "quantity": quantity,
                "cancelled_quantity": cancelled_quantity,
                "message": return_msg or "취소주문이 완료되었습니다.",
                "raw_data": data,
            }
        else:
            err_msg = return_msg or data.get("error_description") or f"오류 코드: {return_code}"
            log_error(f"[주문 취소 실패] 원주문: {clean_ord_no}, 코드: {return_code}, 사유: {err_msg}")
            return {
                "success": False,
                "ord_no": None,
                "base_orig_ord_no": clean_ord_no,
                "stock_code": clean_code,
                "quantity": quantity,
                "cancelled_quantity": 0,
                "message": err_msg,
                "raw_data": data,
            }
    except Exception as e:
        log_error(f"[주문 취소 예외] 원주문: {clean_ord_no}, 오류: {e}")
        return {
            "success": False,
            "ord_no": None,
            "base_orig_ord_no": clean_ord_no,
            "stock_code": clean_code,
            "quantity": quantity,
            "cancelled_quantity": 0,
            "message": f"네트워크 또는 API 호출 오류: {str(e)}",
            "raw_data": {},
        }
