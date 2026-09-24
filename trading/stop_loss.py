"""
스탑로스(Stop Loss & Take Profit) 백그라운드 감시 및 매매 엔진:
장 운영 시간 동안 계좌 잔고(kt00018)를 주기적(기본 10초)으로 감시하여,
보유 종목의 수익률이 익절 기준(tpr, 양수) 이상이거나 손절 기준(slr, 음수) 이하로
도달했을 때 전량 시장가 매도(kt10001) 주문을 실행하고 텔레그램으로 알림을 전송합니다.
"""

import threading
import time
from datetime import datetime

from api.auth import session_manager
from api.account import get_account_balance
from api.order import sell_stock
from telegram.tel_send import send_telegram_message
from utils.logger import log_info, log_error
from utils.settings import (
    get_take_profit_rate,
    get_stop_loss_rate,
    get_market_hours,
)


class StopLossWatcher:
    """
    보유 종목의 실시간 손익률을 주기적으로 감시하고
    익절(tpr) 및 손절(slr) 조건 만족 시 자동 매도를 실행하는 백그라운드 워처 클래스
    """

    def __init__(self, check_interval: int = 10):
        self._check_interval: int = check_interval
        self._is_running: bool = False
        self._thread: threading.Thread | None = None
        self._stop_event: threading.Event = threading.Event()
        self._ordered_stocks: set[str] = set()  # 최근 매도 주문 접수된 종목코드 (중복 주문 방지)
        self._monitored_stocks: list[dict] = []
        self._last_checked_at: str | None = None
        self._last_error: str | None = None

    @property
    def is_running(self) -> bool:
        """워처 실행 중 여부를 반환합니다."""
        return self._is_running

    @property
    def check_interval(self) -> int:
        """감시 주기(초)를 반환합니다."""
        return self._check_interval

    def start(self, interval: int | None = None) -> tuple[bool, str]:
        """
        스탑로스 감시 백그라운드 스레드를 가동합니다.

        :param interval: 감시 주기 (초 단위, 기본값: 10초)
        :return: (성공 여부 bool, 메시지 str)
        """
        if self._is_running:
            return False, "⚠️ 스탑로스 감시 루프가 이미 실행 중입니다."

        if interval is not None and interval > 0:
            self._check_interval = interval

        self._stop_event.clear()
        self._is_running = True
        self._ordered_stocks.clear()
        self._last_error = None

        self._thread = threading.Thread(
            target=self._run_loop,
            name="StopLossWatcherThread",
            daemon=True,
        )
        self._thread.start()

        tpr = get_take_profit_rate()
        slr = get_stop_loss_rate()
        start_msg = (
            f"스탑로스 감시 작업이 시작되었습니다. (주기: {self._check_interval}초)\n"
            f"• 익절 기준: +{tpr:g}% 이상 도달 시 익절\n"
            f"• 손절 기준: {slr:g}% 이하 도달 시 손절"
        )
        log_info(f"[스탑로스 시작] 주기: {self._check_interval}초, TPR: +{tpr}%, SLR: {slr}%")
        return True, start_msg

    def stop(self) -> tuple[bool, str]:
        """
        동작 중인 스탑로스 감시 루프를 안전하게 중단합니다.

        :return: (성공 여부 bool, 메시지 str)
        """
        if not self._is_running:
            return False, "ℹ️ 스탑로스 감시 작업이 실행 중이지 않습니다."

        self._is_running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)

        self._thread = None
        log_info("[스탑로스 중단] 스탑로스 감시 루프가 중단되었습니다.")
        return True, "🛑 스탑로스 감시 작업이 안전하게 중단되었습니다."

    def get_status(self) -> dict:
        """
        현재 스탑로스 워처의 상태 정보를 반환합니다.
        """
        tpr = get_take_profit_rate()
        slr = get_stop_loss_rate()
        return {
            "is_running": self._is_running,
            "interval": self._check_interval,
            "take_profit_rate": tpr,
            "stop_loss_rate": slr,
            "monitored_stocks": self._monitored_stocks,
            "monitored_count": len(self._monitored_stocks),
            "last_checked_at": self._last_checked_at,
            "last_error": self._last_error,
        }

    def _run_loop(self):
        """
        백그라운드에서 주기적으로 계좌 잔고를 확인하고 스탑로스를 판정하는 메인 루프
        """
        log_info("[스탑로스 루프] 감시 스레드 진입")

        while not self._stop_event.is_set():
            try:
                self._check_and_execute()
            except Exception as e:
                self._last_error = str(e)
                log_error(f"[스탑로스 루프 예외] {e}")

            # 지정된 주기(초)만큼 대기하며 중단 신호 감지
            self._stop_event.wait(self._check_interval)

        log_info("[스탑로스 루프] 감시 스레드 정상 종료")

    def _check_and_execute(self):
        """
        1회 계좌 잔고 조회(kt00018) 및 익절/손절 매도 실행 로직
        """
        # 1. 로그인 세션 확인
        if not session_manager.is_authenticated():
            self._last_error = "인증 토큰 없음 또는 세션 만료"
            return

        # 2. 계좌 잔고 조회 (kt00018)
        balance_res = get_account_balance()
        if not balance_res.get("success"):
            self._last_error = balance_res.get("error", "잔고 조회 실패")
            return

        self._last_error = None
        self._last_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        holdings = balance_res.get("holdings", [])
        self._monitored_stocks = holdings

        # 잔고에 없는 종목은 주문 접수 추적 세트에서 제거 (매도 체결 완료 반영)
        current_codes = {item["stock_code"] for item in holdings}
        self._ordered_stocks = {cd for cd in self._ordered_stocks if cd in current_codes}

        if not holdings:
            return

        # 3. 최신 익절/손절 기준치 로드
        tpr = get_take_profit_rate()   # 양수 (예: 5.0)
        slr = get_stop_loss_rate()     # 음수 (예: -10.0)

        for item in holdings:
            stk_cd = item.get("stock_code", "")
            stk_nm = item.get("stock_name", "")
            qty = item.get("quantity", 0)
            tradable_qty = item.get("tradable_quantity", qty)
            profit_rate = item.get("profit_rate", 0.0)
            pur_pric = item.get("purchase_price", 0)
            cur_prc = item.get("current_price", 0)

            # 이미 매도 주문이 접수되어 처리 대기 중이거나 매매가능수량이 0이면 스킵
            if stk_cd in self._ordered_stocks or tradable_qty <= 0 or qty <= 0:
                continue

            # ==========================================
            # ① 익절 판정: profit_rate >= tpr (양수 기준)
            # ==========================================
            if profit_rate >= tpr:
                sell_qty = tradable_qty if tradable_qty > 0 else qty
                log_info(
                    f"🎯 [스탑로스 익절 감지] {stk_nm}({stk_cd}) "
                    f"수익률: +{profit_rate:.2f}% >= 기준: +{tpr:g}%, {sell_qty}주 시장가 매도 진행"
                )
                sell_res = sell_stock(stock_code=stk_cd, quantity=sell_qty, price=None)
                if sell_res.get("success"):
                    self._ordered_stocks.add(stk_cd)
                    ord_no = sell_res.get("ord_no") or "미발급"
                    msg = (
                        f"🎯 [익절 스탑로스 실행 완료]\n\n"
                        f"• 종목: {stk_nm} ({stk_cd})\n"
                        f"• 현재 수익률: +{profit_rate:.2f}% (익절 기준: +{tpr:g}%)\n"
                        f"• 매입가: {pur_pric:,}원 ➡️ 현재가: {cur_prc:,}원\n"
                        f"• 매도 수량: {sell_qty:,}주 (시장가 전량 매도)\n"
                        f"• 주문번호: {ord_no}\n"
                        f"• 상태: 정상 접수 완료"
                    )
                    send_telegram_message(msg)
                else:
                    err = sell_res.get("message", "주문 실패")
                    log_error(f"[스탑로스 익절 매도 실패] {stk_nm}({stk_cd}): {err}")

            # ==========================================
            # ② 손절 판정: profit_rate <= slr (음수 기준)
            # 예: -12.5% <= -10.0% -> 참 (손절 실행)
            # ==========================================
            elif profit_rate <= slr:
                sell_qty = tradable_qty if tradable_qty > 0 else qty
                log_info(
                    f"🛡️ [스탑로스 손절 감지] {stk_nm}({stk_cd}) "
                    f"수익률: {profit_rate:.2f}% <= 기준: {slr:g}%, {sell_qty}주 시장가 매도 진행"
                )
                sell_res = sell_stock(stock_code=stk_cd, quantity=sell_qty, price=None)
                if sell_res.get("success"):
                    self._ordered_stocks.add(stk_cd)
                    ord_no = sell_res.get("ord_no") or "미발급"
                    msg = (
                        f"🛡️ [손절 스탑로스 실행 완료]\n\n"
                        f"• 종목: {stk_nm} ({stk_cd})\n"
                        f"• 현재 손실률: {profit_rate:.2f}% (손절 기준: {slr:g}%)\n"
                        f"• 매입가: {pur_pric:,}원 ➡️ 현재가: {cur_prc:,}원\n"
                        f"• 매도 수량: {sell_qty:,}주 (시장가 전량 매도)\n"
                        f"• 주문번호: {ord_no}\n"
                        f"• 상태: 정상 접수 완료"
                    )
                    send_telegram_message(msg)
                else:
                    err = sell_res.get("message", "주문 실패")
                    log_error(f"[스탑로스 손절 매도 실패] {stk_nm}({stk_cd}): {err}")


# 글로벌 싱글톤 인스턴스 제공
stop_loss_watcher = StopLossWatcher(check_interval=10)
