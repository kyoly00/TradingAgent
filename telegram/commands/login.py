"""
로그인 및 갱신 명령어 처리 모듈:
'login paper', 'login real' 명령어로 토큰 발급 및 세션을 시작하고,
'login renewal {시간}' 명령어로 토큰 갱신 예약 시간을 설정합니다.
"""

from api.auth import session_manager
from utils.settings import get_token_renewal_time, set_token_renewal_time


def handle_login_command(args: list[str], chat_id: int | str | None = None) -> str:
    """
    'login' 명령어의 인자를 분석하여 로그인 또는 갱신 시간 설정을 수행합니다.

    :param args: 명령어 뒤에 오는 인자 목록 (예: ['paper'], ['real'], ['renewal', '8:50'])
    :param chat_id: 명령어를 보낸 텔레그램 채팅방 ID
    :return: 텔레그램으로 회신할 응답 메시지 문자열
    """
    if not args:
        return (
            "⚠️ 로그인 대상 또는 동작을 지정해 주세요.\n"
            "• 모의투자 로그인: `login paper`\n"
            "• 실전투자 로그인: `login real`\n"
            "• 갱신 시각 설정: `login renewal {시간}` (예: login renewal 8:50)"
        )

    sub_cmd = args[0].strip().lower()

    # 1. 토큰 갱신 시간 설정 ('login renewal ...')
    if sub_cmd == "renewal":
        if len(args) < 2:
            current_time = get_token_renewal_time()
            return (
                f"ℹ️ [토큰 자동 갱신 시간]\n"
                f"• 현재 설정된 갱신 시각: 매일 {current_time} (기본값: 08:55)\n\n"
                "시간 변경 방법:\n"
                "`login renewal {시간(24시간제)}`\n"
                "• 예: `login renewal 8:50` (토큰 갱신 시간을 8:50으로 설정)\n"
                "• 예: `login renewal 08:55` (기본 장 시작 5분 전 설정)"
            )

        time_arg = args[1].strip()
        success, result_text = set_token_renewal_time(time_arg)
        if success:
            return (
                f"⏰ [토큰 자동 갱신 시간 변경 완료]\n"
                f"• 설정된 갱신 시각: 매일 {result_text}\n"
                "• 로그인 상태 유지 시 해당 시각에 토큰이 자동 갱신되며, 결과가 텔레그램과 터미널에 보고됩니다."
            )
        else:
            return f"⚠️ {result_text}"

    # 2. 모의/실전투자 로그인 ('login paper', 'login real')
    if sub_cmd not in ("paper", "real"):
        return (
            f"⚠️ 올바르지 않은 명령/모드입니다: '{args[0]}'\n"
            "• 모의투자: `login paper`\n"
            "• 실전투자: `login real`\n"
            "• 갱신 시간 변경: `login renewal 8:50`"
        )

    mode = sub_cmd

    # 마지막 로그인 요청한 채팅방 ID 기록 (자동 갱신 결과 발송용)
    if chat_id:
        session_manager.last_chat_id = chat_id

    # 세션 관리자를 통해 토큰 발급 시도 (au10001)
    success, message, token = session_manager.login(mode)

    mode_display = "모의투자(paper)" if mode == "paper" else "실전투자(real)"
    expires_str = (
        session_manager.expires_dt.strftime("%Y-%m-%d %H:%M:%S")
        if session_manager.expires_dt
        else "정보 없음"
    )

    # 터미널 출력 (사용자 요구사항: 토큰 및 성공 여부 터미널 출력)
    print("\n" + "=" * 60)
    print(f"[키움 OAuth2 접근토큰 발급 결과 (TR: au10001)]")
    print(f"• 투자 구분 : {mode_display}")
    print(f"• 성공 여부 : {'성공 (SUCCESS)' if success else '실패 (FAILED)'}")
    if success:
        print(f"• 토큰 타입 : {session_manager.token_type}")
        print(f"• 만료 일시 : {expires_str} ({session_manager.get_remaining_time_str()})")
        print(f"• 발급 토큰 : {token}")
    else:
        print(f"• 오류 내용 : {message}")
    print("=" * 60 + "\n")

    # 텔레그램 응답 메시지 생성
    renewal_time = get_token_renewal_time()
    if success:
        return (
            f"✅ [로그인 성공]\n"
            f"• 투자 모드: {mode_display}\n"
            f"• 접근토큰: 정상 발급 완료\n"
            f"• 만료 일시: {expires_str} ({session_manager.get_remaining_time_str()})\n"
            f"• 자동 갱신 예정: 매일 {renewal_time} (변경: login renewal {renewal_time})\n"
            f"• 세션에 토큰이 안전하게 보관되었습니다."
        )
    else:
        return (
            f"❌ [로그인 실패]\n"
            f"• 투자 모드: {mode_display}\n"
            f"• 상세 사유: {message}"
        )
