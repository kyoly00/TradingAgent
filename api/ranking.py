"""
순위 정보 조회 API 모듈:
키움 REST API의 다양한 순위 정보 TR을 호출하여 상위 종목 리스트를 조회합니다.
1. ka10032: 거래대금 상위 요청
2. ka10027: 전일대비 등락률(상승률) 상위 요청
3. ka10031: 전일 거래량 상위 요청
4. ka00198: 실시간 종목조회(인기검색) 순위 요청
"""

from api.auth import session_manager
from api.http_queue import http_client
from utils.logger import log_error, log_info

TR_ID_KA10032 = "ka10032"  # 거래대금상위
TR_ID_KA10027 = "ka10027"  # 전일대비등락률상위
TR_ID_KA10031 = "ka10031"  # 전일거래량상위
TR_ID_KA00198 = "ka00198"  # 실시간종목조회순위 (인기검색)

ENDPOINT_RANK_INFO = "/api/dostk/rkinfo"
ENDPOINT_STOCK_INFO = "/api/dostk/stkinfo"


def _parse_int(val_str: str | None) -> int:
    """부호 및 0-padding, 쉼표가 포함된 문자열을 안전하게 정수로 변환합니다."""
    if not val_str:
        return 0
    try:
        clean = str(val_str).strip().replace(",", "")
        sign = -1 if clean.startswith("-") else 1
        clean = clean.lstrip("+-").lstrip("0")
        if not clean:
            return 0
        return sign * int(clean)
    except (ValueError, TypeError):
        return 0


def _parse_float(val_str: str | None) -> float:
    """부호 및 퍼센티지, 쉼표가 포함된 소수점 문자열을 안전하게 실수로 변환합니다."""
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
    """종목코드 접두어 제거 및 6자리 정규화."""
    if not raw_code:
        return ""
    code = raw_code.strip()
    if len(code) > 6 and code[0] in ("A", "J", "Q"):
        code = code[1:]
    if code.isdigit() and len(code) < 6:
        code = code.zfill(6)
    return code


def _make_headers(tr_id: str) -> dict:
    """키움 REST API 호출용 표준 헤더를 생성합니다."""
    return {
        "Content-Type": "application/json;charset=UTF-8",
        "authorization": session_manager.authorization_header,
        "cont-yn": "N",
        "next-key": "",
        "api-id": tr_id,
    }


def get_top_trading_value(limit: int = 20) -> dict:
    """
    거래대금 상위 종목을 조회합니다 (ka10032).

    :param limit: 조회할 상위 종목 수 (기본: 20개)
    :return: 결과 딕셔너리
    """
    if not session_manager.is_authenticated():
        return {
            "success": False,
            "title": "거래대금 상위 20개",
            "items": [],
            "error": "로그인된 세션이 없거나 토큰이 만료되었습니다. 먼저 'login paper' 또는 'login real'을 실행해 주세요.",
        }

    host = session_manager.host
    url = f"{host}{ENDPOINT_RANK_INFO}"
    headers = _make_headers(TR_ID_KA10032)
    body = {
        "mrkt_tp": "000",       # 000: 전체, 001: 코스피, 101: 코스닥
        "mang_stk_incls": "0",  # 0: 관리종목 미포함
        "stex_tp": "1",         # 1: KRX
    }

    try:
        response = http_client.post(url, headers=headers, json=body, timeout=10)
        data = response.json()
        return_code = data.get("return_code")
        return_msg = data.get("return_msg", "")

        is_success = (response.status_code == 200) and (str(return_code) == "0" or return_code is None)

        if not is_success:
            err_msg = return_msg or data.get("error_description") or f"오류 코드: {return_code}"
            log_error(f"ka10032 거래대금 상위 조회 실패: {err_msg}")
            return {"success": False, "title": "거래대금 상위 20개", "items": [], "error": err_msg}

        raw_list = data.get("trde_prica_upper") or []
        items = []
        for idx, row in enumerate(raw_list[:limit], 1):
            cur_p = abs(_parse_int(row.get("cur_prc")))
            flu_rt = _parse_float(row.get("flu_rt"))
            diff_p = _parse_int(row.get("pred_pre"))
            trde_prica = _parse_int(row.get("trde_prica"))  # 백만원 단위
            now_qty = _parse_int(row.get("now_trde_qty"))

            items.append({
                "rank": idx,
                "stock_code": _clean_stock_code(row.get("stk_cd")),
                "stock_name": (row.get("stk_nm") or "").strip(),
                "current_price": cur_p,
                "fluctuation_rate": flu_rt,
                "price_diff": diff_p,
                "trading_value": trde_prica,  # 백만원
                "trading_volume": now_qty,
            })

        return {
            "success": True,
            "title": "거래대금 상위 20개",
            "items": items,
            "error": None,
        }
    except Exception as e:
        log_error(f"ka10032 API 호출 예외: {e}")
        return {"success": False, "title": "거래대금 상위 20개", "items": [], "error": f"API 호출 오류: {e}"}


def get_top_fluctuation_rate(limit: int = 20) -> dict:
    """
    상승률(전일대비 등락률) 상위 종목을 조회합니다 (ka10027).

    :param limit: 조회할 상위 종목 수 (기본: 20개)
    :return: 결과 딕셔너리
    """
    if not session_manager.is_authenticated():
        return {
            "success": False,
            "title": "상승률 상위 20개",
            "items": [],
            "error": "로그인된 세션이 없거나 토큰이 만료되었습니다. 먼저 'login paper' 또는 'login real'을 실행해 주세요.",
        }

    host = session_manager.host
    url = f"{host}{ENDPOINT_RANK_INFO}"
    headers = _make_headers(TR_ID_KA10027)
    body = {
        "mrkt_tp": "000",        # 000: 전체
        "sort_tp": "1",          # 1: 상승률
        "trde_qty_cnd": "0000",  # 전체조회
        "stk_cnd": "0",          # 0: 전체조회
        "crd_cnd": "0",          # 0: 전체조회
        "updown_incls": "1",     # 1: 상하한 포함
        "pric_cnd": "0",         # 0: 전체조회
        "trde_prica_cnd": "0",   # 0: 전체조회
        "stex_tp": "1",          # 1: KRX
    }

    try:
        response = http_client.post(url, headers=headers, json=body, timeout=10)
        data = response.json()
        return_code = data.get("return_code")
        return_msg = data.get("return_msg", "")

        is_success = (response.status_code == 200) and (str(return_code) == "0" or return_code is None)

        if not is_success:
            err_msg = return_msg or data.get("error_description") or f"오류 코드: {return_code}"
            log_error(f"ka10027 상승률 상위 조회 실패: {err_msg}")
            return {"success": False, "title": "상승률 상위 20개", "items": [], "error": err_msg}

        raw_list = data.get("pred_pre_flu_rt_upper") or []
        items = []
        for idx, row in enumerate(raw_list[:limit], 1):
            cur_p = abs(_parse_int(row.get("cur_prc")))
            flu_rt = _parse_float(row.get("flu_rt"))
            diff_p = _parse_int(row.get("pred_pre"))
            now_qty = _parse_int(row.get("now_trde_qty"))

            items.append({
                "rank": idx,
                "stock_code": _clean_stock_code(row.get("stk_cd")),
                "stock_name": (row.get("stk_nm") or "").strip(),
                "current_price": cur_p,
                "fluctuation_rate": flu_rt,
                "price_diff": diff_p,
                "trading_volume": now_qty,
            })

        return {
            "success": True,
            "title": "상승률 상위 20개",
            "items": items,
            "error": None,
        }
    except Exception as e:
        log_error(f"ka10027 API 호출 예외: {e}")
        return {"success": False, "title": "상승률 상위 20개", "items": [], "error": f"API 호출 오류: {e}"}


def get_top_trading_volume(limit: int = 20) -> dict:
    """
    거래량 상위 종목을 조회합니다 (ka10031).

    :param limit: 조회할 상위 종목 수 (기본: 20개)
    :return: 결과 딕셔너리
    """
    if not session_manager.is_authenticated():
        return {
            "success": False,
            "title": "거래량 상위 20개",
            "items": [],
            "error": "로그인된 세션이 없거나 토큰이 만료되었습니다. 먼저 'login paper' 또는 'login real'을 실행해 주세요.",
        }

    host = session_manager.host
    url = f"{host}{ENDPOINT_RANK_INFO}"
    headers = _make_headers(TR_ID_KA10031)
    body = {
        "mrkt_tp": "000",            # 000: 전체
        "qry_tp": "1",               # 1: 전일거래량 상위 100종목
        "rank_strt": "0",            # 0부터
        "rank_end": str(limit),      # limit까지
        "stex_tp": "1",              # 1: KRX
    }

    try:
        response = http_client.post(url, headers=headers, json=body, timeout=10)
        data = response.json()
        return_code = data.get("return_code")
        return_msg = data.get("return_msg", "")

        is_success = (response.status_code == 200) and (str(return_code) == "0" or return_code is None)

        if not is_success:
            err_msg = return_msg or data.get("error_description") or f"오류 코드: {return_code}"
            log_error(f"ka10031 거래량 상위 조회 실패: {err_msg}")
            return {"success": False, "title": "거래량 상위 20개", "items": [], "error": err_msg}

        raw_list = data.get("pred_trde_qty_upper") or []
        items = []
        for idx, row in enumerate(raw_list[:limit], 1):
            cur_p = abs(_parse_int(row.get("cur_prc")))
            diff_p = _parse_int(row.get("pred_pre"))
            vol = _parse_int(row.get("trde_qty"))

            # 전일 대비 등락률 계산
            prev_p = cur_p - diff_p
            flu_rt = round((diff_p / prev_p) * 100, 2) if prev_p > 0 else 0.0

            items.append({
                "rank": idx,
                "stock_code": _clean_stock_code(row.get("stk_cd")),
                "stock_name": (row.get("stk_nm") or "").strip(),
                "current_price": cur_p,
                "fluctuation_rate": flu_rt,
                "price_diff": diff_p,
                "trading_volume": vol,
            })

        return {
            "success": True,
            "title": "거래량 상위 20개",
            "items": items,
            "error": None,
        }
    except Exception as e:
        log_error(f"ka10031 API 호출 예외: {e}")
        return {"success": False, "title": "거래량 상위 20개", "items": [], "error": f"API 호출 오류: {e}"}


def get_top_search_rank(limit: int = 20) -> dict:
    """
    실시간 인기검색(종목조회) 순위 상위 종목을 조회합니다 (ka00198).

    :param limit: 조회할 상위 종목 수 (기본: 20개)
    :return: 결과 딕셔너리
    """
    if not session_manager.is_authenticated():
        return {
            "success": False,
            "title": "인기검색 상위 20개",
            "items": [],
            "error": "로그인된 세션이 없거나 토큰이 만료되었습니다. 먼저 'login paper' 또는 'login real'을 실행해 주세요.",
        }

    host = session_manager.host
    url = f"{host}{ENDPOINT_STOCK_INFO}"
    headers = _make_headers(TR_ID_KA00198)
    body = {
        "qry_tp": "4",  # 4: 당일 누적 실시간 종목조회 순위
    }

    try:
        response = http_client.post(url, headers=headers, json=body, timeout=10)
        data = response.json()
        return_code = data.get("return_code")
        return_msg = data.get("return_msg", "")

        is_success = (response.status_code == 200) and (str(return_code) == "0" or return_code is None)

        if not is_success:
            err_msg = return_msg or data.get("error_description") or f"오류 코드: {return_code}"
            log_error(f"ka00198 인기검색 순위 조회 실패: {err_msg}")
            return {"success": False, "title": "인기검색 상위 20개", "items": [], "error": err_msg}

        raw_list = data.get("item_inq_rank") or []
        items = []
        for idx, row in enumerate(raw_list[:limit], 1):
            cur_p = abs(_parse_int(row.get("past_curr_prc")))
            flu_rt = _parse_float(row.get("base_comp_chgr"))
            rank_val = _parse_int(row.get("bigd_rank")) or idx
            rank_chg = (row.get("rank_chg") or "").strip()
            rank_sign = (row.get("rank_chg_sign") or "").strip()

            chg_str = ""
            if rank_chg and rank_chg != "0":
                chg_str = f"({rank_sign}{rank_chg})"

            items.append({
                "rank": rank_val,
                "stock_code": _clean_stock_code(row.get("stk_cd")),
                "stock_name": (row.get("stk_nm") or "").strip(),
                "current_price": cur_p,
                "fluctuation_rate": flu_rt,
                "rank_change": chg_str,
            })

        return {
            "success": True,
            "title": "인기검색 상위 20개",
            "items": items,
            "error": None,
        }
    except Exception as e:
        log_error(f"ka00198 API 호출 예외: {e}")
        return {"success": False, "title": "인기검색 상위 20개", "items": [], "error": f"API 호출 오류: {e}"}
