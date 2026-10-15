"""
주문 체결 및 미체결 내역 조회 명령어 처리 모듈:
'orders' (미체결 주문 조회),
'orders all' (당일 전체 주문 내역 역순 조회),
'orders {종목코드}' (특정 종목 주문 내역 조회)
명령어를 파싱하고 키움 kt00007 TR을 호출하여 결과를 회신합니다.
"""

from api.order import get_orders


def format_order_list(
    order_list: list[dict],
    title_suffix: str,
    *,
    include_controls: bool = True,
) -> str:
    """정규화된 주문 목록을 텔레그램 메시지 형식으로 변환합니다."""
    lines = [f"📋 **[{title_suffix}]** (총 {len(order_list)}건)\n"]

    for idx, item in enumerate(order_list, start=1):
        ord_no = item.get("ord_no") or "-"
        stk_nm = item.get("stock_name") or "-"
        stk_cd = item.get("stock_code") or "-"
        io_type = item.get("io_type") or "-"
        ord_type = item.get("order_type") or "-"
        ord_qty = item.get("order_qty", 0)
        cntr_qty = item.get("cntr_qty", 0)
        remn_qty = item.get("remn_qty", 0)
        ord_price = item.get("order_price", 0)
        cntr_price = item.get("cntr_price", 0)
        ord_tm = item.get("order_time") or "-"
        mdfy_cncl = item.get("modify_cancel", "").strip()

        price_disp = f"{ord_price:,}원" if ord_price > 0 else "시장가"
        status_disp = f" | {mdfy_cncl}" if mdfy_cncl else ""

        line = (
            f"**{idx}. {stk_nm}** (`{stk_cd}`) | {io_type}{status_disp}\n"
            f"• 주문번호: `{ord_no}` | 유형: {ord_type} | 시간: {ord_tm}\n"
            f"• 수량: {ord_qty:,}주 (체결: {cntr_qty:,}주, 잔량: **{remn_qty:,}주**)\n"
            f"• 주문단가: {price_disp}"
        )
        if cntr_qty > 0 and cntr_price > 0:
            line += f" | 체결단가: {cntr_price:,}원"

        lines.append(line)

    if include_controls:
        lines.append("\n💡 **주문 제어 팁**:")
        lines.append("• 정정: `modify {주문번호} {정정단가}` (또는 `modify {주문번호} {수량} {단가}`)")
        lines.append("• 취소: `cancel {주문번호}` (또는 `cancel {주문번호} {수량}`)")

    return "\n".join(lines)


def handle_orders_command(args: list[str]) -> str:
    """
    'orders' 명령어 인자를 분석하여 주문 체결/미체결 내역을 조회합니다.

    :param args: 명령어 뒤에 오는 인자 목록
                 - [] 또는 ['pending'], ['미체결'] -> 미체결 주문 목록 조회
                 - ['all'], ['전체'] -> 당일 전체 주문 체결 내역 조회
                 - ['005930'] -> 특정 종목 주문 체결 내역 조회
    :return: 텔레그램으로 회신할 메시지 문자열
    """
    qry_tp = "3"  # 기본: 미체결
    stock_code = ""
    title_suffix = "미체결 주문 내역"

    if args:
        first_arg = args[0].strip().lower()
        if first_arg in ("all", "전체", "체결"):
            qry_tp = "2"  # 당일 역순 (전체)
            title_suffix = "당일 전체 주문 내역"
        elif first_arg in ("pending", "미체결", "open"):
            qry_tp = "3"
            title_suffix = "미체결 주문 내역"
        elif first_arg.isdigit() or len(first_arg) == 6:
            stock_code = first_arg
            qry_tp = "2"  # 특정 종목 당일 주문 내역
            title_suffix = f"종목({stock_code}) 주문 내역"

    result = get_orders(qry_tp=qry_tp, stock_code=stock_code)

    if not result.get("success"):
        err_msg = result.get("message", "알 수 없는 오류")
        return f"❌ [주문 내역 조회 실패]\n\n• 사유: {err_msg}"

    order_list = result.get("orders", [])

    if not order_list:
        if qry_tp == "3":
            return "📋 현재 접수된 **미체결 주문**이 없습니다."
        elif stock_code:
            return f"📋 종목({stock_code})에 대한 당일 주문 내역이 없습니다."
        else:
            return "📋 당일 접수된 주문 내역이 없습니다."

    return format_order_list(order_list, title_suffix)
