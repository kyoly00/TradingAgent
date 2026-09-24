"""
설정값 확인 명령어 처리 모듈:
'stts' 명령어를 수신하면 config/data/settings.json에 저장된 모든 설정값을 조회하여
장 운영 시간(mkhr), 토큰 자동 갱신 시간 등 모든 설정 내용을 출력합니다.
"""

import json
from utils.settings import (
    get_all_settings,
    get_market_hours,
    get_token_renewal_time,
    get_take_profit_rate,
    get_stop_loss_rate,
)


from trading.stop_loss import stop_loss_watcher


def handle_stts_command(args: list[str] | None = None) -> str:
    """
    'stts' 명령어를 처리하여 settings.json의 모든 설정값을 포맷팅하여 회신합니다.

    :param args: 명령어 인자 (기본 미사용)
    :return: 텔레그램 회신 메시지 문자열
    """
    settings = get_all_settings()

    start_time, end_time = get_market_hours()
    token_renewal = get_token_renewal_time()
    tpr = get_take_profit_rate()
    slr = get_stop_loss_rate()

    # 스탑로스 워처 가동 상태 확인
    stls_status = stop_loss_watcher.get_status()
    if stls_status["is_running"]:
        stls_state = f"가동 중 🟢 ({stls_status['interval']}초 주기, {stls_status['monitored_count']}개 종목 감시)"
    else:
        stls_state = "중지됨 ⚪ (시작: `start stls`)"

    # 원본 JSON 문자열 생성 (인덴트 2 적용)
    json_str = json.dumps(settings, indent=2, ensure_ascii=False)

    lines = [
        "⚙️ [시스템 설정 현황 (settings.json)]\n",
        "📌 **주요 설정 요약**",
        f"• 🤖 스탑로스 실시간 감시: {stls_state}",
        f"• 🎯 익절 기준 (TPR): +{tpr:g}% (설정: `tpr {tpr:g}`)",
        f"• 🛡️ 손절 기준 (SLR): {slr:g}% (설정: `slr {abs(slr):g}`)",
        f"• 🕒 장 운영 시간: {start_time} ~ {end_time} (설정: `mkhr {start_time} {end_time}`)",
        f"• ⏰ 토큰 자동 갱신: 매일 {token_renewal} (설정: `login renewal {token_renewal}`)",
        "",

        "━━━━━━━━━━━━━━━━━━━",
        "📄 **전체 설정 JSON 데이터**",
        f"```json\n{json_str}\n```",
    ]

    return "\n".join(lines)
