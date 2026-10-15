"""
텔레그램 메시지 전송 모듈:
config/config.py의 telegram_chat_id와 telegram_token을 사용하여
주어진 메시지를 텔레그램 채팅방으로 전송합니다.
"""

import os
import sys
from dotenv import load_dotenv

# .env 환경 변수 로드 (config 모듈 임포트 전 적용)
load_dotenv()

# 프로젝트 루트 경로를 sys.path에 추가하여 어디서 실행하든 config 모듈 임포트 가능하도록 설정
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from api.http_queue import http_client
from config.config import telegram_chat_id, telegram_token


def send_telegram_message(message: str, chat_id: str | int | None = None) -> bool:
    """
    주어진 메시지를 텔레그램 봇 API(sendMessage)를 통해 지정된 채팅방으로 전송합니다.

    :param message: 전송할 텍스트 메시지
    :param chat_id: 전송할 대상 채팅방 ID (지정하지 않을 경우 config.config의 telegram_chat_id 사용)
    :return: 전송 성공 여부 (bool)
    """
    target_chat_id = chat_id or telegram_chat_id

    if not telegram_token or not target_chat_id:
        print("오류: config/config.py에 telegram_token 또는 telegram_chat_id가 설정되어 있지 않습니다.")
        return False

    url = f"https://api.telegram.org/bot{telegram_token}/sendMessage"
    payload = {
        "chat_id": target_chat_id,
        "text": message,
    }

    try:
        response = http_client.post(url, json=payload, timeout=10)
        data = response.json()

        if data.get("ok"):
            print("텔레그램 메시지 전송 성공")
            return True
        else:
            print("텔레그램 메시지 전송 실패:", data.get("description"))
            return False
    except Exception as e:
        print("텔레그램 전송 중 오류 발생:", e)
        return False


if __name__ == "__main__":
    # 직접 실행 시 테스트 메시지 전송
    test_message = "안녕하세요! 트레이딩 에이전트 텔레그램 알림 테스트 메시지입니다."
    send_telegram_message(test_message)
