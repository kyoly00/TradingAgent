"""
프로그램 종료 명령어 처리 모듈:
'power off' 명령어를 수신하면 시스템 종료 메시지를 반환하고
프로그램 안전 종료를 요청합니다.
"""


def handle_power_command(args: list[str]) -> tuple[str, bool]:
    """
    'power' 명령어를 처리합니다.

    :param args: 명령어 뒤 인자 목록 (예: ['off'])
    :return: (응답 메시지 str, 종료 여부 bool)
    """
    if args and args[0].strip().lower() == "off":
        return (
            "🛑 [시스템 종료]\n"
            "트레이딩 에이전트 프로그램을 안전하게 종료합니다.\n"
            "이용해 주셔서 감사합니다.",
            True,
        )

    return (
        "⚠️ 올바른 종료 명령어는 `power off` 입니다.",
        False,
    )
