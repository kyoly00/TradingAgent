"""
트레이딩 에이전트 메인 진입점 (Main Entry Point):
프로그램의 수명 주기(Lifecycle)를 관리하며,
텔레그램 봇 리스너를 실행하여 사용자의 명령을 지속적으로 수신 및 처리합니다.
"""

import sys
from dotenv import load_dotenv

# .env 환경 변수 로드
load_dotenv()

from config.config import telegram_chat_id
from telegram.bot import TelegramBot
from telegram.tel_send import send_telegram_message
from telegram.commands.login import handle_login_command
from utils.logger import log_info, log_error, log_telegram_out


def main():
    """
    트레이딩 에이전트 프로그램 시작 함수
    """
    print("=" * 60)
    print("🚀 [TradingAgent] 키움 자동매매 에이전트 시스템 가동")
    print("=" * 60)

    # 1. 프로그램 시작 알림 텔레그램 톡 발송
    start_msg = "🚀 [TradingAgent] 키움 자동매매 시스템이 시작되었습니다.\n모의투자(paper) 모드로 자동 로그인을 진행합니다."
    log_info("프로그램 시작 알림 텔레그램 메시지 발송 중...")
    send_success = send_telegram_message(start_msg)
    log_telegram_out(chat_id=telegram_chat_id or "default", text=start_msg, success=send_success)

    # 2. 모의투자(paper) 모드로 자동 로그인 수행
    log_info("모의투자(paper) 모드 자동 로그인 수행 중...")
    login_result_msg = handle_login_command(["paper"], chat_id=telegram_chat_id)
    send_success = send_telegram_message(login_result_msg)
    log_telegram_out(chat_id=telegram_chat_id or "default", text=login_result_msg, success=send_success)

    # 3. 텔레그램 봇 인스턴스 생성 및 메시지 수신 대기 시작
    bot = TelegramBot()

    try:
        bot.start_polling()
    except KeyboardInterrupt:
        print("\n시스템을 안전하게 종료합니다.")
    except Exception as e:
        log_error(f"시스템 비정상 종료: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
