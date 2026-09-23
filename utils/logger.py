"""
로깅 유틸리티 모듈:
텔레그램 메시지 송수신(시각, 입출력 구분, 채팅방 ID, 메시지 내용) 및 시스템 로그를
터미널과 파일(logs/telegram.log)에 일관된 포맷으로 기록합니다.
"""

import os
from datetime import datetime
import threading

# 로그 파일 저장 경로 설정
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "logs")
TELEGRAM_LOG_FILE = os.path.join(LOG_DIR, "telegram.log")

_log_lock = threading.Lock()


def _ensure_log_dir():
    """로그 디렉토리가 없으면 생성합니다."""
    if not os.path.exists(LOG_DIR):
        os.makedirs(LOG_DIR, exist_ok=True)


def _write_log(log_line: str):
    """터미널 출력 및 파일에 로그 라인을 기록합니다."""
    print(log_line)
    try:
        _ensure_log_dir()
        with _log_lock:
            with open(TELEGRAM_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(log_line + "\n")
    except Exception as e:
        print(f"⚠️ 로그 파일 저장 실패: {e}")


def log_telegram_in(chat_id: int | str, text: str, sender_name: str = ""):
    """
    텔레그램 수신(IN) 메시지 로그를 기록합니다.

    :param chat_id: 메시지를 보낸 사용자/채팅방 ID
    :param text: 수신된 텍스트 내용
    :param sender_name: 발신자 이름 또는 사용자명
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sender_info = f"({sender_name})" if sender_name else ""
    # 터미널 및 파일 기록 포맷
    log_line = f"[{now}] [TELEGRAM IN] ChatID: {chat_id} {sender_info} | 내용: {repr(text)}"
    _write_log(log_line)


def log_telegram_out(chat_id: int | str, text: str, success: bool = True):
    """
    텔레그램 발신(OUT) 메시지 로그를 기록합니다.

    :param chat_id: 메시지를 전송한 대상 사용자/채팅방 ID
    :param text: 전송된 텍스트 내용
    :param success: 전송 성공 여부
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    status = "SUCCESS" if success else "FAILED"
    # 긴 텍스트의 경우 한 줄로 보기 좋게 요약하거나 줄바꿈 정리
    display_text = repr(text) if len(text) <= 100 else repr(text[:97] + "...")
    log_line = f"[{now}] [TELEGRAM OUT] [{status}] ChatID: {chat_id} | 내용: {display_text}"
    _write_log(log_line)


def log_info(message: str):
    """일반 정보 로그를 기록합니다."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{now}] [INFO] {message}"
    _write_log(log_line)


def log_error(message: str):
    """에러 로그를 기록합니다."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{now}] [ERROR] {message}"
    _write_log(log_line)
