"""
종목 검색 명령어 처리 모듈:
'srch {종목코드}' 명령어로 키움 ka10001 TR을 호출하여
해당 종목의 현재가, 거래량, 시가, 고가, 저가, 전일대비를 이모지와 함께 조회 및 회신합니다.
"""

from api.stock_info import get_stock_info


def _format_price(val_str: str) -> str:
    """가격 문자열에서 부호 제거 후 천 단위 콤마와 '원'을 붙여 반환합니다."""
    try:
        clean = val_str.replace("+", "").replace("-", "").strip()
        val = int(clean)
        return f"{val:,}원"
    except (ValueError, TypeError):
        return f"{val_str}원"


def _format_qty(val_str: str) -> str:
    """거래량 문자열에서 부호 제거 후 천 단위 콤마와 '주'를 붙여 반환합니다."""
    try:
        clean = val_str.replace("+", "").replace("-", "").strip()
        val = int(clean)
        return f"{val:,}주"
    except (ValueError, TypeError):
        return f"{val_str}주"


def _format_pred_pre(pred_pre_str: str, flu_rt_str: str, pre_sig: str) -> str:
    """
    전일대비, 등락율, 대비기호를 바탕으로 이모지와 포맷팅된 문자열을 생성합니다.
    pre_sig: 1: 상한가, 2: 상승, 3: 보합, 4: 하한가, 5: 하락
    """
    try:
        clean_pre = pred_pre_str.replace("+", "").replace("-", "").strip()
        pre_val = int(clean_pre)
        flu_val = float(flu_rt_str.strip()) if flu_rt_str else 0.0
    except (ValueError, TypeError):
        return f"{pred_pre_str}원 ({flu_rt_str}%)"

    # 대비기호 또는 값 부호에 따른 이모지 및 부호 결정
    is_upper_limit = pre_sig == "1"
    is_lower_limit = pre_sig == "4"
    is_positive = pre_sig == "2" or (pre_sig not in ("3", "5") and "+" in pred_pre_str) or flu_val > 0
    is_negative = pre_sig == "5" or (pre_sig not in ("3", "2") and "-" in pred_pre_str) or flu_val < 0

    if is_upper_limit:
        return f"🚀 +{pre_val:,}원 (+{abs(flu_val):.2f}%) [상한가]"
    elif is_lower_limit:
        return f"💧 -{pre_val:,}원 (-{abs(flu_val):.2f}%) [하한가]"
    elif is_positive and pre_val > 0:
        return f"🔺 +{pre_val:,}원 (+{abs(flu_val):.2f}%)"
    elif is_negative and pre_val > 0:
        return f"🔻 -{pre_val:,}원 (-{abs(flu_val):.2f}%)"
    else:
        return f"➖ 0원 (0.00%)"


def handle_search_command(args: list[str]) -> str:
    """
    'srch' 명령어의 인자(종목코드)를 분석하여 주식 기본 정보를 조회하고
    현재가, 거래량, 시가, 고가, 저가, 전일대비를 이모지와 함께 반환합니다.

    :param args: 명령어 뒤에 오는 인자 목록 (예: ['005930'])
    :return: 텔레그램으로 회신할 메시지 문자열
    """
    if not args:
        return (
            "ℹ️ [종목 정보 조회 사용법]\n"
            "• 형식: `srch {종목코드}`\n"
            "• 예시: `srch 005930` (삼성전자)"
        )

    stock_code = args[0].strip()

    # 종목 정보 API 호출 (ka10001)
    result = get_stock_info(stock_code)

    if not result.get("success"):
        return f"❌ [종목 조회 실패]\n• 종목코드: {stock_code}\n• 사유: {result.get('error')}"

    stk_nm = result.get("stk_nm") or "종목명 미확인"
    stk_cd = result.get("stk_cd", stock_code)

    # 요청 항목 6가지 포맷팅 (현재가, 거래량, 시가, 고가, 저가, 전일대비)
    cur_prc_formatted = _format_price(result.get("cur_prc", "0"))
    pred_pre_formatted = _format_pred_pre(
        result.get("pred_pre", "0"),
        result.get("flu_rt", "0"),
        result.get("pre_sig", "3"),
    )
    trde_qty_formatted = _format_qty(result.get("trde_qty", "0"))
    open_pric_formatted = _format_price(result.get("open_pric", "0"))
    high_pric_formatted = _format_price(result.get("high_pric", "0"))
    low_pric_formatted = _format_price(result.get("low_pric", "0"))

    reply = (
        f"🔍 [종목 정보] {stk_nm} ({stk_cd})\n\n"
        f"• 💰 현재가: {cur_prc_formatted}\n"
        f"• 📈 전일대비: {pred_pre_formatted}\n"
        f"• 📊 거래량: {trde_qty_formatted}\n"
        f"• 🚪 시가: {open_pric_formatted}\n"
        f"• 🔥 고가: {high_pric_formatted}\n"
        f"• ❄️ 저가: {low_pric_formatted}"
    )

    return reply
