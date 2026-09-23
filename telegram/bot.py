"""
텔레그램 봇 수신 리스너 모듈:
Telegram Bot API의 getUpdates를 활용한 Long Polling 방식으로
사용자로부터 수신되는 메시지를 실시간으로 지속 감지하고 처리하며,
송수신 로그 기록, 토큰 갱신 스케줄러 관리, 시스템 종료(power off)를 처리합니다.
"""

import time
import requests
from config.config import telegram_token, telegram_chat_id
from utils.logger import log_telegram_in, log_telegram_out, log_info, log_error
from utils.scheduler import token_scheduler
from .tel_send import send_telegram_message
from .commands.dispatcher import dispatch_command


class TelegramBot:
    """
    텔레그램 봇 메시지 수신 및 명령어 디스패치 루프를 관리하는 클래스
    """

    def __init__(self):
        self.token = telegram_token
        self.default_chat_id = telegram_chat_id
        self.offset: int | None = None
        self.running: bool = False

    def start_polling(self, poll_timeout: int = 20):
        """
        텔레그램 메시지 수신을 시작하고 무한 루프로 대기합니다.
        동시에 백그라운드 토큰 자동 갱신 스케줄러를 가동합니다.

        :param poll_timeout: Long Polling 대기 시간(초)
        """
        if not self.token:
            log_error("config/config.py에 telegram_token이 설정되어 있지 않습니다.")
            return

        self.running = True
        log_info("🤖 [텔레그램 봇] 메시지 수신 대기 시작 (종료: 'power off' 또는 Ctrl+C)")
        print(f"• 기본 채팅방 ID: {self.default_chat_id or '미지정 (수신 메시지 발신자 ID로 회신)'}")
        print("• 주요 명령어: login paper, login real, login renewal 8:50, status, power off, help\n")

        # 토큰 자동 갱신 스케줄러 가동
        token_scheduler.start()

        # 봇 시작 전 텔레그램 서버 큐에 남아있던 이전 미처리 메시지 정리(Flush)
        self._flush_pending_updates()

        # 텔레그램 앱 내 명령어 자동완성 메뉴(Bot Commands) 등록
        self._register_bot_commands()

        try:
            while self.running:
                try:
                    updates = self._fetch_updates(timeout=poll_timeout)
                    for update in updates:
                        should_stop = self._handle_update(update)
                        if should_stop:
                            self.stop()
                            return
                except requests.exceptions.RequestException as e:
                    log_error(f"네트워크 오류: {e}")
                    time.sleep(3)
                except Exception as e:
                    log_error(f"폴링 루프 예외: {e}")
                    time.sleep(2)
        except KeyboardInterrupt:
            log_info("사용자 인터럽트(Ctrl+C)로 봇을 중단합니다.")
            self.stop()
        finally:
            self.stop()

    def stop(self):
        """봇 수신 루프 및 스케줄러를 안전하게 중단합니다."""
        if not self.running:
            return
        self.running = False
        token_scheduler.stop()
        log_info("🔌 [텔레그램 봇] 수신 루프 및 스케줄러가 종료되었습니다.")

    def _fetch_updates(self, timeout: int = 20) -> list[dict]:
        """
        텔레그램 getUpdates API를 호출하여 새 메시지 목록을 가져옵니다.
        """
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        params = {
            "timeout": timeout,
            "allowed_updates": ["message"],
        }
        if self.offset is not None:
            params["offset"] = self.offset

        try:
            # 네트워크 타임아웃은 poll timeout보다 5초 길게 설정
            response = requests.get(url, params=params, timeout=timeout + 5)
            if response.status_code != 200:
                log_error(f"getUpdates 응답 실패 (HTTP {response.status_code}): {response.text}")
                return []

            data = response.json()
            if not data.get("ok"):
                log_error(f"텔레그램 API 오류: {data.get('description')}")
                return []

            return data.get("result", [])
        except requests.exceptions.Timeout:
            # 롱폴링 타임아웃은 정상적인 상황이므로 빈 목록 반환
            return []
        except Exception as e:
            log_error(f"getUpdates 요청 오류: {e}")
            return []

    def _register_bot_commands(self):
        """
        텔레그램 Bot API(setMyCommands)를 호출하여
        사용자 텔레그램 채팅창에 자동완성 명령어 메뉴(/help, /srch, /buy 등)를 등록합니다.
        """
        url = f"https://api.telegram.org/bot{self.token}/setMyCommands"
        commands = [
            {"command": "help", "description": "전체 명령어 사용법 및 도움말"},
            {"command": "rsv", "description": "명령어 예약 (예: /rsv 10:00 buy 005930 5)"},
            {"command": "report", "description": "계좌 자산 및 보유 종목 잔고 조회"},
            {"command": "srch", "description": "종목 정보 조회 (예: /srch 005930)"},
            {"command": "buy", "description": "주식 매수 주문 (시장가/지정가)"},
            {"command": "sell", "description": "주식 매도 주문 (시장가/지정가)"},
            {"command": "mkhr", "description": "장 운영 시간 설정 (예: /mkhr 9:30 15:00)"},
            {"command": "stts", "description": "전체 시스템 설정값 확인"},
            {"command": "status", "description": "현재 로그인 모드 및 토큰 상태"},
            {"command": "login", "description": "키움 계정 로그인 (paper/real)"},
            {"command": "power", "description": "트레이딩 에이전트 안전 종료"},
        ]
        try:
            requests.post(url, json={"commands": commands}, timeout=5)
        except Exception as e:
            log_error(f"텔레그램 명령어 메뉴 등록 실패: {e}")

    def _flush_pending_updates(self):
        """
        봇 시작 전에 텔레그램 서버 큐에 남아있던 이전 미처리 메시지(과거의 power off 등)를
        모두 조회하여 확인(Acknowledge) 처리하고 offset을 최신 상태로 동기화합니다.
        """
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        try:
            # offset=-1로 최신 업데이트 1개를 요청하여 마지막 update_id 확인
            res = requests.get(url, params={"offset": -1, "limit": 1, "timeout": 0}, timeout=5)
            if res.status_code == 200:
                data = res.json()
                results = data.get("result", [])
                if results:
                    last_id = results[-1].get("update_id")
                    if last_id is not None:
                        self.offset = last_id + 1
                        # last_id + 1을 offset으로 한 번 더 호출해 서버 상의 모든 과거 메시지를 확인(Ack) 완료 처리
                        requests.get(url, params={"offset": self.offset, "timeout": 0}, timeout=5)
                        log_info(f"이전 대기 중이던 과거 메시지들을 정리하고 오프셋을 동기화했습니다. (최신 offset: {self.offset})")
        except Exception as e:
            log_error(f"대기 메시지 정리(flush) 중 오류: {e}")

    def _ack_offset(self):
        """
        현재 self.offset을 텔레그램 서버로 전달하여
        직전에 수신된 명령어(power off 등)를 수신 완료 상태로 확정합니다.
        """
        if self.offset is None:
            return
        url = f"https://api.telegram.org/bot{self.token}/getUpdates"
        try:
            requests.get(url, params={"offset": self.offset, "timeout": 0}, timeout=5)
        except Exception as e:
            log_error(f"오프셋 확인(Ack) 전송 실패: {e}")

    def _handle_update(self, update: dict) -> bool:
        """
        수신된 단일 업데이트 객체를 파싱하고 명령어를 처리한 뒤 응답을 회신합니다.

        :return: 프로그램 종료 요청 여부 (bool)
        """
        update_id = update.get("update_id")
        if update_id is not None:
            # 다음 업데이트를 받기 위해 offset을 update_id + 1로 갱신
            self.offset = update_id + 1

        message = update.get("message")
        if not message:
            return False

        chat = message.get("chat", {})
        chat_id = chat.get("id")
        text = message.get("text")
        sender_name = chat.get("first_name") or chat.get("title") or "사용자"

        if not text or not chat_id:
            return False

        # 1. 수신 로그 기록 (시각, 입출력 구분, 채팅방 ID, 메시지 내용)
        log_telegram_in(chat_id=chat_id, text=text, sender_name=sender_name)

        # 2. 명령어 파싱 및 실행
        reply_message, should_exit = dispatch_command(raw_text=text, chat_id=chat_id)

        # 3. 응답 메시지 발송 및 발신 로그 기록
        if reply_message:
            send_success = send_telegram_message(reply_message, chat_id=chat_id)
            log_telegram_out(chat_id=chat_id, text=reply_message, success=send_success)

        # 4. 종료 명령어('power off')인 경우 루프 종료 플래그 반환
        if should_exit:
            log_info(f"종료 명령어('power off')가 수신되어 시스템을 종료합니다. (요청자 ChatID: {chat_id})")
            # 텔레그램 서버에 이 종료 메시지 수신 완료(offset 갱신)를 즉시 통보하여 재시작 시 재실행 방지
            self._ack_offset()
            return True

        return False
