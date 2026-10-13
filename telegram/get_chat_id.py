"""
텔레그램 Chat ID 확인 스크립트:
config/config.py의 telegram_token을 사용하여 최신 수신 메시지로부터 chat_id를 조회하고 출력합니다.
"""

import os
import sys

from dotenv import load_dotenv

# .env 환경 변수 로드 (config 모듈 임포트 전 적용)
load_dotenv()

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from api.http_queue import http_client
from config.config import telegram_token


def get_latest_chat_id() -> int | None:
    """
    텔레그램 봇 API의 getUpdates 메서드를 호출하여
    해당 채팅방의 최신 메시지로부터 chat_id를 찾아내어 출력합니다.
    """
    if not telegram_token:
        print("오류: config/config.py에 telegram_token이 설정되어 있지 않습니다.")
        return None

    url = f"https://api.telegram.org/bot{telegram_token}/getUpdates"

    try:
        response = http_client.get(url, timeout=10)
        data = response.json()

        if not data.get("ok"):
            print("텔레그램 API 호출 실패:", data.get("description"))
            return None

        results = data.get("result", [])
        if not results:
            print("최근 수신된 메시지가 없습니다.")
            print("텔레그램 봇 채팅방에 아무 메시지(/start 또는 텍스트)를 한 번 전송한 후 다시 실행해 주세요.")
            return None

        # 가장 최근 수신된 업데이트 정보 추출
        latest_update = results[-1]
        message = (
            latest_update.get("message")
            or latest_update.get("channel_post")
            or latest_update.get("edited_message")
            or latest_update.get("my_chat_member")
        )

        if not message:
            print("업데이트에서 메시지 정보를 찾을 수 없습니다:", latest_update)
            return None

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        chat_type = chat.get("type", "알 수 없음")
        chat_name = chat.get("first_name") or chat.get("title") or "이름 없음"

        print("=" * 50)
        print(f"채팅방/발신자: {chat_name} (유형: {chat_type})")
        print(f"chat_id: {chat_id}")
        print("=" * 50)

        return chat_id

    except Exception as e:
        print("chat_id 조회 중 오류가 발생했습니다:", e)
        return None


if __name__ == "__main__":
    get_latest_chat_id()
