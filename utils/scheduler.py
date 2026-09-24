"""
토큰 갱신 스케줄러 모듈:
설정된 시각(기본 08:55, 장 시작 5분 전)마다 키움 OAuth2 접근토큰을 자동으로 갱신하고,
결과(새 토큰, 만료 일시, 성공 여부)를 터미널 출력 및 텔레그램 메시지로 보고합니다.
"""

import time
import threading
from datetime import datetime
from api.auth import session_manager
from utils.settings import get_token_renewal_time
from utils.logger import log_info, log_error, log_telegram_out


class TokenRenewalScheduler:
    """
    백그라운드 스레드에서 주기적으로 현재 시각을 검사하여
    설정된 시각에 세션 토큰 갱신을 실행하는 스케줄러
    """

    def __init__(self):
        self._thread: threading.Thread | None = None
        self._running: bool = False
        self._last_run_date: str | None = None  # 중복 실행 방지용 (YYYY-MM-DD HH:MM)

    def start(self):
        """스케줄러 백그라운드 스레드를 시작합니다."""
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        log_info(f"토큰 갱신 스케줄러 시작됨 (설정 시간: {get_token_renewal_time()})")

    def stop(self):
        """스케줄러 스레드를 중단합니다."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        log_info("토큰 갱신 스케줄러 중단됨")

    def _run_loop(self):
        """10초 주기로 현재 시각을 확인하는 루프"""
        while self._running:
            try:
                self._check_and_execute()
            except Exception as e:
                log_error(f"토큰 갱신 스케줄러 예외 발생: {e}")

            # 10초 대기 (종료 플래그 반응성 유지)
            for _ in range(10):
                if not self._running:
                    break
                time.sleep(1)

    def _check_and_execute(self):
        """설정 시각 도달 여부 검사 (토큰 정기 갱신 및 예약 명령어 실행)"""
        now = datetime.now()
        current_minute_key = now.strftime("%Y-%m-%d %H:%M")

        # 1. 토큰 정기 갱신 검사
        self._check_token_renewal(now, current_minute_key)

        # 2. 예약 명령어 검사 및 자동 실행
        self._check_reservations(now, current_minute_key)

    def _check_token_renewal(self, now: datetime, current_minute_key: str):
        """설정된 토큰 갱신 시각 도달 여부를 확인하고 실행합니다."""
        target_time = get_token_renewal_time()  # e.g. "08:55"
        current_time = now.strftime("%H:%M")

        # 설정된 시각과 일치하고 이번 분에 아직 실행되지 않은 경우
        if current_time == target_time and self._last_run_date != current_minute_key:
            # 로그인된 세션이 있는 경우에만 갱신 수행
            if session_manager.is_authenticated():
                self._last_run_date = current_minute_key
                self.execute_renewal(now)

    def _check_reservations(self, now: datetime, current_minute_key: str):
        """
        설정된 예약 명령어(rsv) 목록을 확인하고,
        해당 시각에 도달한 예약 명령을 실행합니다.
        (daily: 매일 평일 실행, once: 1회 실행 후 자동 삭제)
        """
        from utils.settings import load_settings, save_settings
        from telegram.commands.dispatcher import dispatch_command
        from telegram.tel_send import send_telegram_message

        settings = load_settings()
        reservations = settings.get("reservations", [])
        if not reservations:
            return

        current_time = now.strftime("%H:%M")
        is_weekend = now.weekday() >= 5  # 토요일(5), 일요일(6)

        target_chat_id = session_manager.last_chat_id
        modified = False
        remaining_reservations = []

        for rsv in reservations:
            rsv_id = rsv.get("id")
            rsv_time = rsv.get("time")
            command = rsv.get("command")
            rsv_type = rsv.get("type", "daily")
            last_run = rsv.get("last_run")

            # 시간이 일치하고 이번 분에 아직 실행되지 않은 경우
            should_run = (rsv_time == current_time) and (last_run != current_minute_key)

            # daily 예약은 주말(토/일) 제외
            if should_run and rsv_type == "daily" and is_weekend:
                should_run = False

            if should_run:
                type_name = "1회성 예약" if rsv_type == "once" else "매일 반복 예약"
                log_info(f"⏰ [예약 명령어 자동 실행] ID [{rsv_id}] ({type_name}) 실행: '{command}'")

                # 1) 예약 실행 사전 알림 전송 (사용자 요구사항)
                notice = (
                    f"⏰ [예약 실행 알림]\n"
                    f"• 예약 번호: [{rsv_id}] ({type_name})\n"
                    f"• 실행 명령어: `{command}`\n"
                    "예약 설정에 따라 명령어를 자동으로 실행합니다."
                )
                send_telegram_message(notice, chat_id=target_chat_id)
                log_telegram_out(target_chat_id or "default", notice, success=True)

                # 2) 텔레그램 명령 디스패처 호출하여 명령어 실행
                try:
                    reply_msg, should_exit = dispatch_command(raw_text=command, chat_id=target_chat_id)
                    if reply_msg:
                        send_telegram_message(reply_msg, chat_id=target_chat_id)
                        log_telegram_out(target_chat_id or "default", reply_msg, success=True)
                except Exception as e:
                    err_msg = f"❌ [예약 명령 실행 실패] '{command}' 실행 중 오류 발생: {e}"
                    log_error(err_msg)
                    send_telegram_message(err_msg, chat_id=target_chat_id)

                # 3) 실행 상태 갱신
                rsv["last_run"] = current_minute_key
                modified = True

                # once(1회성) 예약은 실행 후 목록에서 제외
                if rsv_type == "once":
                    log_info(f"🎯 1회성 예약 [{rsv_id}] 실행 완료로 자동 삭제됩니다.")
                    continue

            remaining_reservations.append(rsv)

        if modified:
            settings["reservations"] = remaining_reservations
            save_settings(settings)


    def execute_renewal(self, now: datetime | None = None):
        """
        토큰 갱신을 즉시 실행하고 터미널 및 텔레그램으로 결과를 보고합니다.
        """
        from telegram.tel_send import send_telegram_message

        if now is None:
            now = datetime.now()

        time_str = now.strftime("%Y-%m-%d %H:%M:%S")
        mode = session_manager.mode
        mode_display = "모의투자(paper)" if mode == "paper" else "실전투자(real)"

        log_info(f"정기 토큰 갱신 작업 시작 ({mode_display})")

        # 토큰 갱신 수행 (au10001)
        success, message, new_token = session_manager.renew()
        expires_str = (
            session_manager.expires_dt.strftime("%Y-%m-%d %H:%M:%S")
            if session_manager.expires_dt
            else "정보 없음"
        )
        remaining_str = session_manager.get_remaining_time_str()

        # 1. 터미널 출력 (사용자 요구사항)
        print("\n" + "=" * 60)
        print(f"🔄 [정기 토큰 자동 갱신 보고 (TR: au10001) - {time_str}]")
        print(f"• 투자 모드 : {mode_display}")
        print(f"• 갱신 결과 : {'성공 (SUCCESS)' if success else '실패 (FAILED)'}")
        if success:
            print(f"• 토큰 타입 : {session_manager.token_type}")
            print(f"• 만료 일시 : {expires_str} ({remaining_str})")
            print(f"• 신규 토큰 : {new_token}")
        else:
            print(f"• 실패 사유 : {message}")
        print("=" * 60 + "\n")

        # 2. 텔레그램 메시지 생성 및 전송
        if success:
            telegram_report = (
                f"🔄 [토큰 정기 갱신 완료]\n"
                f"• 갱신 시각: {time_str}\n"
                f"• 투자 모드: {mode_display}\n"
                f"• 만료 일시: {expires_str} ({remaining_str})\n"
                f"• 새 접근토큰이 세션에 안전하게 갱신되었습니다."
            )
        else:
            telegram_report = (
                f"⚠️ [토큰 정기 갱신 실패]\n"
                f"• 시도 시각: {time_str}\n"
                f"• 투자 모드: {mode_display}\n"
                f"• 실패 사유: {message}"
            )

        # 수신 대상 채팅방: 마지막 로그인 채팅방 또는 기본 설정 채팅방
        target_chat_id = session_manager.last_chat_id

        # 텔레그램 발송 및 로그 기록
        send_success = send_telegram_message(telegram_report, chat_id=target_chat_id)
        if target_chat_id:
            log_telegram_out(target_chat_id, telegram_report, success=send_success)


# 전역 스케줄러 싱글톤 인스턴스
token_scheduler = TokenRenewalScheduler()
