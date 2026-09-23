"""
계좌 자산 및 보유 종목 현황 리포트 명령어 처리 모듈:
'report' 또는 'r' 명령어를 수신하면 키움 kt00018 TR을 호출하여
자금 현황(추정예탁자산, 총매입금액, 총평가금액, 총평가손익, 총수익률)과
보유 종목(종목번호, 종목명, 보유수량, 매입가, 현재가, 수익률)을 이모지와 함께 회신합니다.
"""

from api.account import get_account_balance


def _format_money(val: int) -> str:
    """정수 금액을 천 단위 콤마와 '원'을 붙여 반환합니다."""
    return f"{val:,}원"


def _format_pl(pl_val: int, rt_val: float) -> str:
    """손익금액과 수익률을 이모지와 부호가 포함된 문자열로 포맷팅합니다."""
    if rt_val > 0 or pl_val > 0:
        return f"🔺 +{pl_val:,}원 (+{abs(rt_val):.2f}%)"
    elif rt_val < 0 or pl_val < 0:
        return f"🔻 -{abs(pl_val):,}원 (-{abs(rt_val):.2f}%)"
    else:
        return "➖ 0원 (0.00%)"


def _format_rate(rt_val: float) -> str:
    """수익률을 이모지와 부호가 포함된 문자열로 포맷팅합니다."""
    if rt_val > 0:
        return f"🔺 +{abs(rt_val):.2f}%"
    elif rt_val < 0:
        return f"🔻 -{abs(rt_val):.2f}%"
    else:
        return "➖ 0.00%"


def handle_report_command(args: list[str] | None = None) -> str:
    """
    'report' 또는 'r' 명령어를 처리하여 계좌 자산 현황과 보유 종목 목록을 반환합니다.

    :param args: 명령어 인자 (기본 미사용)
    :return: 텔레그램 메시지 문자열
    """
    result = get_account_balance(qry_tp="1", exchange="KRX")

    if not result.get("success"):
        return f"❌ [계좌 조회 실패]\n• 사유: {result.get('error', '알 수 없는 오류')}"

    # 1. 자금 현황 요약
    tot_pur = _format_money(result["tot_pur_amt"])
    tot_evlt = _format_money(result["tot_evlt_amt"])
    prsm_asset = _format_money(result["prsm_dpst_aset_amt"])
    tot_pl_str = _format_pl(result["tot_evlt_pl"], result["tot_prft_rt"])

    report_lines = [
        "📊 [내 계좌 자산 현황]",
        f"• 💵 추정예탁자산: {prsm_asset}",
        f"• 💰 총매입금액: {tot_pur}",
        f"• 📈 총평가금액: {tot_evlt}",
        f"• 🎯 총평가손익: {tot_pl_str}",
        "",
        "━━━━━━━━━━━━━━━━━━━",
    ]

    # 2. 보유 종목 리스트
    holdings = result.get("holdings", [])
    count = len(holdings)

    if count == 0:
        report_lines.append("📦 [보유 종목 내역]\n• 현재 보유 중인 종목이 없습니다.")
    else:
        report_lines.append(f"📦 [보유 종목 내역] (총 {count}종목)\n")
        for idx, item in enumerate(holdings, start=1):
            stk_nm = item.get("stock_name") or "종목명 없음"
            stk_cd = item.get("stock_code") or "------"
            qty = f"{item.get('quantity', 0):,}주"
            pur_prc = _format_money(item.get("purchase_price", 0))
            cur_prc = _format_money(item.get("current_price", 0))
            prft_rt_str = _format_rate(item.get("profit_rate", 0.0))

            item_block = (
                f"{idx}️⃣ {stk_nm} ({stk_cd})\n"
                f"   • 보유수량: {qty}\n"
                f"   • 매입가: {pur_prc}\n"
                f"   • 현재가: {cur_prc}\n"
                f"   • 수익률: {prft_rt_str}"
            )
            report_lines.append(item_block)
            if idx < count:
                report_lines.append("")

    return "\n".join(report_lines)
