"""
텔레그램 연동 패키지:
봇 메시지 수신/리스너, 전송 및 명령어 처리 기능을 제공합니다.
"""

__all__ = ["send_telegram_message", "TelegramBot", "dispatch_command"]


def __getattr__(name: str):
    """순환 import를 피하면서 기존 패키지 공개 API를 지연 로드합니다."""
    if name == "send_telegram_message":
        from .tel_send import send_telegram_message

        return send_telegram_message
    if name == "TelegramBot":
        from .bot import TelegramBot

        return TelegramBot
    if name == "dispatch_command":
        from .commands.dispatcher import dispatch_command

        return dispatch_command
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
