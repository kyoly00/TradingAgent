"""
장 운영 시간 설정 명령어 처리 모듈:
'mkhr {시작시간} {종료시간}' 명령어로 한국 주식 시장 정규 거래 시간(기본: 09:00 ~ 15:30)을
24시간제로 설정하고 config/data/settings.json에 저장합니다.
"""

from utils.settings import get_market_hours, set_market_hours


def handle_mkhr_command(args: list[str]) -> str:
    """
    'mkhr' 명령어를 처리하여 장 운영 시간을 조회하거나 새로 설정합니다.

    :param args: 명령어 뒤에 오는 인자 목록 (예: ['9:30', '15:00'])
    :return: 텔레그램 회신 메시지 문자열
    """
    # 1. 인자가 없는 경우: 현재 설정된 장 시간 안내
    if not args:
        start_time, end_time = get_market_hours()
        return (
            "🕒 [현재 장 운영 시간]\n\n"
            f"• 설정 시간: {start_time} ~ {end_time} (24시간제)\n"
            "• 기본값: 09:00 ~ 15:30 (정규 주식 거래 시간)\n\n"
            "변경 방법:\n"
            "`mkhr {시작시간} {종료시간}`\n"
            "• 예시: `mkhr 9:30 15:00`\n"
            "• 예시: `mkhr 09:00 15:30`"
        )

    # 2. 인자가 2개가 아닌 경우
    if len(args) != 2:
        return (
            "⚠️ 올바른 형식으로 입력해 주세요.\n\n"
            "• 사용법: `mkhr {시작시간} {종료시간}`\n"
            "• 예시: `mkhr 9:30 15:00` (9시 30분 ~ 15시 00분)"
        )

    start_arg = args[0].strip()
    end_arg = args[1].strip()

    # 3. 장 운영 시간 검증 및 저장
    success, result_msg = set_market_hours(start_arg, end_arg)

    if success:
        return (
            "🕒 [장 운영 시간 변경 완료]\n\n"
            f"• 설정된 장 시간: {result_msg} (24시간제)\n"
            "• 설정이 `config/data/settings.json`에 성공적으로 저장되었습니다."
        )
    else:
        return f"⚠️ [장 시간 설정 실패]\n• 사유: {result_msg}"
