"""
상위 20개 종목 순위 조회 명령어 처리 모듈:
- 'rank': 순위 조회 메뉴 안내 (1: 거래대금, 2: 상승률, 3: 거래량, 4: 인기검색)
- 'rank 1': 거래대금 상위 20개 조회 (ka10032)
- 'rank 2': 상승률 상위 20개 조회 (ka10027)
- 'rank 3': 거래량 상위 20개 조회 (ka10031)
- 'rank 4': 실시간 인기검색 상위 20개 조회 (ka00198)
- 'rank {번호} cmd {개수} {명령}': 순위 종목코드를 명령 템플릿에 넣어 일괄 실행
"""

import re
from collections.abc import Callable

from api.ranking import (
    get_top_trading_value,
    get_top_fluctuation_rate,
    get_top_trading_volume,
    get_top_search_rank,
)
from utils.logger import log_error, log_info


CommandExecutor = Callable[[str], tuple[str, bool]]


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
        "• `rank 4` 또는 `/rank 4` (인기검색 순위)\n\n"
        "⚙️ **순위 종목 대상 명령 일괄 실행**:\n"
        "• `rank {번호} cmd {개수} {명령 템플릿}`\n"
        "• 종목코드 위치에는 `( )` 또는 `()`를 입력합니다.\n"
        "• 예: `rank 4 cmd 15 gdcrs add ( ) 100000`"
    )


def _get_rank_result(choice: str, limit: int) -> tuple[str, dict] | None:
    """순위 번호에 맞는 API를 호출하고 표시 이름과 결과를 반환합니다."""
    if choice == "1":
        return "거래대금 상위", get_top_trading_value(limit=limit)
    if choice == "2":
        return "상승률 상위", get_top_fluctuation_rate(limit=limit)
    if choice == "3":
        return "거래량 상위", get_top_trading_volume(limit=limit)
    if choice == "4":
        return "인기검색 순위", get_top_search_rank(limit=limit)
    return None


def _is_failed_reply(reply: str) -> bool:
    """기존 명령 응답의 실패 표식으로 일괄 실행 성공 여부를 판별합니다."""
    return reply.lstrip().startswith(("⚠️", "❌", "❓"))


def _summarize_reply(reply: str) -> str:
    """종목별 실행 결과에서 첫 번째 비어 있지 않은 줄만 짧게 추출합니다."""
    first_line = next((line.strip() for line in reply.splitlines() if line.strip()), "응답 없음")
    if len(first_line) > 80:
        return first_line[:77] + "..."
    return first_line


def _handle_rank_batch_command(
    choice: str,
    args: list[str],
    command_executor: CommandExecutor | None,
) -> str:
    """순위 상위 종목코드를 명령 템플릿에 치환하여 순차 실행합니다."""
    usage = (
        "• 형식: `rank {번호} cmd {개수} {명령 템플릿}`\n"
        "• 예시: `rank 4 cmd 15 gdcrs add ( ) 100000`"
    )
    if len(args) < 2:
        return f"⚠️ 순위 종목 명령 실행 형식이 올바르지 않습니다.\n{usage}"

    count_text = args[0].strip()
    if not count_text.isdigit():
        return f"⚠️ 실행 개수는 1~20 사이의 정수여야 합니다: '{count_text}'"

    count = int(count_text)
    if not 1 <= count <= 20:
        return f"⚠️ 실행 개수는 1~20 사이여야 합니다: {count}"

    command_template = " ".join(args[1:]).strip()
    placeholder_pattern = re.compile(r"\(\s*\)")
    placeholder_count = len(placeholder_pattern.findall(command_template))
    if placeholder_count != 1:
        return (
            "⚠️ 명령 템플릿에는 종목코드 자리 `( )` 또는 `()`를 정확히 한 번 넣어 주세요.\n"
            f"{usage}"
        )

    template_command = command_template.split(maxsplit=1)[0].lstrip("/").lower()
    if template_command in ("rank", "power"):
        return "⚠️ rank 일괄 실행에서는 `rank` 재호출과 `power` 명령을 사용할 수 없습니다."

    if command_executor is None:
        return "❌ 명령 실행기를 사용할 수 없어 순위 종목 명령을 실행하지 못했습니다."

    rank_result = _get_rank_result(choice, limit=count)
    if rank_result is None:
        return f"⚠️ 올바른 순위 번호를 입력해 주세요: '{choice}' (1~4)"

    rank_name, result = rank_result
    if not result.get("success"):
        return f"⚠️ [{rank_name} 조회 실패]\n• 사유: {result.get('error')}"

    items = result.get("items") or []
    if not items:
        return f"ℹ️ {rank_name} 데이터가 존재하지 않아 실행할 명령이 없습니다."

    target_items = items[:count]
    result_lines = []
    success_count = 0
    failure_count = 0

    for index, item in enumerate(target_items, start=1):
        stock_code = str(item.get("stock_code") or "").strip()
        stock_name = str(item.get("stock_name") or "종목명 미확인").strip()
        if not stock_code:
            failure_count += 1
            result_lines.append(f"{index}. ❌ 종목코드 없음 | 실행하지 않음")
            continue

        command = placeholder_pattern.sub(stock_code, command_template)
        try:
            reply, should_exit = command_executor(command)
            if should_exit:
                failure_count += 1
                summary = "종료 요청 명령은 일괄 실행할 수 없습니다."
                status_icon = "❌"
            elif _is_failed_reply(reply):
                failure_count += 1
                summary = _summarize_reply(reply)
                status_icon = "❌"
            else:
                success_count += 1
                summary = _summarize_reply(reply)
                status_icon = "✅"

            result_lines.append(
                f"{index}. {status_icon} {stock_name} ({stock_code}) | {summary}"
            )
            log_info(f"[rank cmd 실행] 종목: {stock_code}, 명령: '{command}', 결과: {summary}")
        except Exception as exc:
            failure_count += 1
            result_lines.append(f"{index}. ❌ {stock_name} ({stock_code}) | 실행 오류: {exc}")
            log_error(f"[rank cmd 실행 예외] 종목: {stock_code}, 명령: '{command}', 오류: {exc}")

    executed_count = len(target_items)
    header = (
        f"⚙️ [순위 종목 명령 실행 결과 - {rank_name}]\n\n"
        f"• 요청/대상: {count}개 / {executed_count}개\n"
        f"• 성공: {success_count}개 | 실패: {failure_count}개\n"
        f"• 명령 템플릿: `{command_template}`\n"
    )
    return header + "\n" + "\n".join(result_lines)


def handle_rank_command(
    args: list[str],
    command_executor: CommandExecutor | None = None,
) -> str:
    """
    'rank' 명령어 및 'rank {번호}' 입력을 분석하여 해당 순위 정보를 회신합니다.

    :param args: 명령어 뒤 인자 목록 (예: [], ['1'], ['2'], ['3'], ['4'])
    :param command_executor: rank cmd에서 치환된 명령을 실행할 디스패처 콜백
    :return: 텔레그램 응답 메시지
    """
    # 1. 인자가 없는 경우 -> 메뉴 안내
    if not args:
        return get_rank_menu_text()

    choice = args[0].strip()

    if len(args) >= 2 and args[1].strip().lower() == "cmd":
        return _handle_rank_batch_command(choice, args[2:], command_executor)

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
