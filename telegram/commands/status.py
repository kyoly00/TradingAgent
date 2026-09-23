"""
상태 확인 명령어 처리 모듈:
현재 세션의 로그인 상태, au10001 TR 기반 토큰 만료 일시 및 잔여 시간,
토큰 갱신 예약 시간을 종합적으로 확인합니다.
"""

from api.auth import session_manager
from utils.settings import get_token_renewal_time


def handle_status_command(args: list[str]) -> str:
    """
    현재 봇 및 API 세션 상태를 반환합니다.
    """
    renewal_time = get_token_renewal_time()

    if session_manager.is_authenticated():
        mode_str = "모의투자 (paper)" if session_manager.mode == "paper" else "실전투자 (real)"
        expires_str = (
            session_manager.expires_dt.strftime("%Y-%m-%d %H:%M:%S")
            if session_manager.expires_dt
            else "정보 없음"
        )
        remaining_str = session_manager.get_remaining_time_str()
        token_type = (session_manager.token_type or "bearer").capitalize()

        return (
            f"ℹ️ [현재 세션 상태]\n"
            f"• 인증 상태: 로그인 완료 (정상)\n"
            f"• 투자 모드: {mode_str}\n"
            f"• 토큰 타입: {token_type}\n"
            f"• 토큰 만료: {expires_str} ({remaining_str})\n"
            f"• 갱신 예약: 매일 {renewal_time}"
        )
    elif session_manager.token and session_manager.is_token_expired():
        mode_str = "모의투자 (paper)" if session_manager.mode == "paper" else "실전투자 (real)"
        return (
            f"⚠️ [현재 세션 상태 - 토큰 만료]\n"
            f"• 투자 모드: {mode_str}\n"
            f"• 인증 상태: 접근토큰이 만료되었습니다.\n"
            f"• 조치: `login {session_manager.mode}` 명령어로 토큰을 재발급받으세요."
        )
    else:
        return (
            "ℹ️ [현재 세션 상태]\n"
            "• 인증 상태: 미로그인 (토큰 없음)\n"
            f"• 토큰 갱신 예약: 매일 {renewal_time} (로그인 후 활성화)\n\n"
            "• 로그인 방법:\n"
            "  - 모의투자: `login paper`\n"
            "  - 실전투자: `login real`"
        )
