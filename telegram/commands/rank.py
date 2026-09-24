"""
상위 20개 종목 순위 조회 명령어 처리 모듈:
- 'rank': 순위 조회 메뉴 안내 (1: 거래대금, 2: 상승률, 3: 거래량, 4: 인기검색)
- 'rank 1': 거래대금 상위 20개 조회 (ka10032)
- 'rank 2': 상승률 상위 20개 조회 (ka10027)
- 'rank 3': 거래량 상위 20개 조회 (ka10031)
- 'rank 4': 실시간 인기검색 상위 20개 조회 (ka00198)
"""

from api.ranking import (
    get_top_trading_value,
    get_top_fluctuation_rate,
    get_top_trading_volume,
    get_top_search_rank,
)


def _format_price_diff(diff: int, rate: float) -> str:
    """전일대비 가격 및 등락률 포맷팅."""
    sign = "+" if rate > 0 else ("" if rate == 0 else "")
    emoji = "🔺" if rate > 0 else ("🔹" if rate < 0 else "➖")
    return f"{sign}{rate:.2f}% {emoji}"


def _format_trading_value(val_million: int) -> str:
    """거래대금(백만원)을 억원/조원 단위로 가독성 있게 포맷팅."""
    if val_million >= 1_000_000:
        cho = val_million / 1_000_000
        return f"{cho:.1f}조원"
    elif val_million >= 100:
        eok = val_million // 100
        return f"{eok:,}억원"
    else:
        return f"{val_million:,}백만원"


def _format_rank_1_output(res: dict) -> str:
    """거래대금 상위 20개 포맷팅."""
    items = res.get("items", [])
    if not items:
        return "ℹ️ 거래대금 상위 데이터가 존재하지 않습니다."

    lines = [
        "💰 **[거래대금 상위 20개 종목]**\n",
    ]
    for item in items:
        rank = item["rank"]
        nm = item["stock_name"]
        cd = item["stock_code"]
        cur_p = item["current_price"]
        flu_rt = item["fluctuation_rate"]
        val_str = _format_trading_value(item["trading_value"])
        vol = item["trading_volume"]
        rate_str = _format_price_diff(item["price_diff"], flu_rt)

        lines.append(
            f"**{rank:2d}. {nm}** (`{cd}`)\n"
            f"   • {cur_p:,}원 ({rate_str}) | 대금: {val_str} ({vol:,}주)"
        )
    return "\n".join(lines)


def _format_rank_2_output(res: dict) -> str:
    """상승률 상위 20개 포맷팅."""
    items = res.get("items", [])
    if not items:
        return "ℹ️ 상승률 상위 데이터가 존재하지 않습니다."

    lines = [
        "🚀 **[상승률(등락률) 상위 20개 종목]**\n",
    ]
    for item in items:
        rank = item["rank"]
        nm = item["stock_name"]
        cd = item["stock_code"]
        cur_p = item["current_price"]
        flu_rt = item["fluctuation_rate"]
        vol = item["trading_volume"]
        rate_str = _format_price_diff(item["price_diff"], flu_rt)

        lines.append(
            f"**{rank:2d}. {nm}** (`{cd}`)\n"
            f"   • {cur_p:,}원 ({rate_str}) | 거래량: {vol:,}주"
        )
    return "\n".join(lines)


def _format_rank_3_output(res: dict) -> str:
    """거래량 상위 20개 포맷팅."""
    items = res.get("items", [])
    if not items:
        return "ℹ️ 거래량 상위 데이터가 존재하지 않습니다."

    lines = [
        "📊 **[거래량 상위 20개 종목]**\n",
    ]
    for item in items:
        rank = item["rank"]
        nm = item["stock_name"]
        cd = item["stock_code"]
        cur_p = item["current_price"]
        flu_rt = item["fluctuation_rate"]
        vol = item["trading_volume"]
        rate_str = _format_price_diff(item["price_diff"], flu_rt)

        lines.append(
            f"**{rank:2d}. {nm}** (`{cd}`)\n"
            f"   • {cur_p:,}원 ({rate_str}) | 거래량: {vol:,}주"
        )
    return "\n".join(lines)


def _format_rank_4_output(res: dict) -> str:
    """실시간 인기검색 상위 20개 포맷팅."""
    items = res.get("items", [])
    if not items:
        return "ℹ️ 인기검색 순위 데이터가 존재하지 않습니다."

    lines = [
        "🔥 **[실시간 인기검색 상위 20개 종목]**\n",
    ]
    for item in items:
        rank = item["rank"]
        nm = item["stock_name"]
        cd = item["stock_code"]
        cur_p = item["current_price"]
        flu_rt = item["fluctuation_rate"]
        chg = item.get("rank_change", "")
        chg_disp = f" {chg}" if chg else ""
        rate_str = _format_price_diff(0, flu_rt)

        lines.append(
            f"**{rank:2d}. {nm}** (`{cd}`){chg_disp}\n"
            f"   • {cur_p:,}원 ({rate_str})"
        )
    return "\n".join(lines)


def get_rank_menu_text() -> str:
    """'rank' 입력 시 안내할 4가지 순위 메뉴 텍스트를 반환합니다."""
    return (
        "🏆 **[국내주식 상위 20개 순위 조회 메뉴]**\n\n"
        "조회하실 순위 기준의 번호를 입력해 주세요:\n"
        "1. 💰 거래대금 상위 20개 (`rank 1`)\n"
        "2. 🚀 상승률 상위 20개 (`rank 2`)\n"
        "3. 📊 거래량 상위 20개 (`rank 3`)\n"
        "4. 🔥 인기검색 상위 20개 (`rank 4`)\n\n"
        "💡 **사용 예시**:\n"
        "• `rank 1` 또는 `/rank 1` (거래대금 순위)\n"
        "• `rank 2` 또는 `/rank 2` (상승률 순위)\n"
        "• `rank 3` 또는 `/rank 3` (거래량 순위)\n"
        "• `rank 4` 또는 `/rank 4` (인기검색 순위)"
    )


def handle_rank_command(args: list[str]) -> str:
    """
    'rank' 명령어 및 'rank {번호}' 입력을 분석하여 해당 순위 정보를 회신합니다.

    :param args: 명령어 뒤 인자 목록 (예: [], ['1'], ['2'], ['3'], ['4'])
    :return: 텔레그램 응답 메시지
    """
    # 1. 인자가 없는 경우 -> 메뉴 안내
    if not args:
        return get_rank_menu_text()

    choice = args[0].strip()

    # 2. 번호별 조회 실행
    if choice == "1":
        res = get_top_trading_value(limit=20)
        if not res["success"]:
            return f"⚠️ [거래대금 상위 조회 실패]\n• 사유: {res.get('error')}"
        return _format_rank_1_output(res)

    elif choice == "2":
        res = get_top_fluctuation_rate(limit=20)
        if not res["success"]:
            return f"⚠️ [상승률 상위 조회 실패]\n• 사유: {res.get('error')}"
        return _format_rank_2_output(res)

    elif choice == "3":
        res = get_top_trading_volume(limit=20)
        if not res["success"]:
            return f"⚠️ [거래량 상위 조회 실패]\n• 사유: {res.get('error')}"
        return _format_rank_3_output(res)

    elif choice == "4":
        res = get_top_search_rank(limit=20)
        if not res["success"]:
            return f"⚠️ [인기검색 순위 조회 실패]\n• 사유: {res.get('error')}"
        return _format_rank_4_output(res)

    else:
        return (
            f"⚠️ 올바른 순위 번호를 입력해 주세요: '{choice}'\n\n"
            "사용 가능한 번호:\n"
            "• `rank 1` : 거래대금 상위 20개\n"
            "• `rank 2` : 상승률 상위 20개\n"
            "• `rank 3` : 거래량 상위 20개\n"
            "• `rank 4` : 인기검색 상위 20개\n\n"
            "메뉴를 다시 보시려면 `rank`를 입력하세요."
        )
