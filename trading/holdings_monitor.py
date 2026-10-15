"""장중 계좌 보유수량 변화를 감지해 매수·매도 알림을 생성하는 감시 서비스."""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from api.account import get_account_balance
from api.auth import session_manager
from utils.logger import log_error, log_info
from utils.settings import get_market_hours

Notifier = Callable[[str], object]


@dataclass(frozen=True)
class HoldingSnapshot:
    """변경 감지에 필요한 최소 보유 종목 정보."""

    stock_code: str
    stock_name: str
    quantity: int


class HoldingsChangeWatcher:
    """장중 10초마다 보유수량을 비교하여 매수·매도 변화를 알립니다."""

    def __init__(self, check_interval: int = 10):
        self._check_interval = check_interval
        self._is_running = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._notifier: Notifier | None = None
        self._previous_holdings: dict[str, HoldingSnapshot] | None = None
        self._session_key: str | None = None
        self._last_checked_at: str | None = None
        self._last_error: str | None = None

    @property
    def is_running(self) -> bool:
        return self._is_running

    def configure(self, notifier: Notifier):
        """보유수량 변경 메시지를 전달할 콜백을 설정합니다."""
        self._notifier = notifier

    def start(self) -> bool:
        """보유 종목 변경 감시 스레드를 시작합니다."""
        if self._is_running:
            return False
        self._stop_event.clear()
        self._previous_holdings = None
        self._session_key = None
        self._last_error = None
        self._is_running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="HoldingsChangeWatcherThread",
            daemon=True,
        )
        self._thread.start()
        log_info(f"[보유 종목 변경 감시 시작] 조회 주기: {self._check_interval}초")
        return True

    def stop(self):
        """보유 종목 변경 감시 스레드를 안전하게 중단합니다."""
        was_running = self._is_running
        self._is_running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self._thread = None
        self._previous_holdings = None
        self._session_key = None
        if was_running:
            log_info("[보유 종목 변경 감시 중단]")

    @staticmethod
    def _is_market_open(now: datetime | None = None) -> bool:
        current = now or datetime.now()
        if current.weekday() >= 5:
            return False
        start_time, end_time = get_market_hours()
        current_time = current.strftime("%H:%M")
        return start_time <= current_time <= end_time

    @staticmethod
    def _normalize_holdings(balance_result: dict) -> dict[str, HoldingSnapshot]:
        snapshots = {}
        for item in balance_result.get("holdings") or []:
            stock_code = str(item.get("stock_code") or "").strip()
            stock_name = str(item.get("stock_name") or "종목명 없음").strip()
            try:
                quantity = int(item.get("quantity") or 0)
            except (TypeError, ValueError):
                continue
            if len(stock_code) != 6 or not stock_code.isdigit() or quantity <= 0:
                continue
            snapshots[stock_code] = HoldingSnapshot(
                stock_code=stock_code,
                stock_name=stock_name,
                quantity=quantity,
            )
        return snapshots

    @staticmethod
    def _format_changes(
        previous: dict[str, HoldingSnapshot],
        current: dict[str, HoldingSnapshot],
    ) -> str | None:
        lines = []
        for stock_code in sorted(previous.keys() | current.keys()):
            before = previous.get(stock_code)
            after = current.get(stock_code)
            before_quantity = before.quantity if before else 0
            after_quantity = after.quantity if after else 0
            delta = after_quantity - before_quantity
            if delta == 0:
                continue

            stock_name = (
                (after.stock_name if after else "")
                or (before.stock_name if before else "")
                or "종목명 없음"
            )
            if delta > 0:
                lines.extend(
                    [
                        f"🟢 [매수 반영] {stock_name} ({stock_code})",
                        f"• 보유수량: {before_quantity:,}주 → {after_quantity:,}주 "
                        f"(+{delta:,}주)",
                    ]
                )
            else:
                lines.extend(
                    [
                        f"🔴 [매도 반영] {stock_name} ({stock_code})",
                        f"• 보유수량: {before_quantity:,}주 → {after_quantity:,}주 "
                        f"(-{abs(delta):,}주)",
                    ]
                )

        if not lines:
            return None
        return "🔔 [보유 종목 변경 감지]\n\n" + "\n\n".join(
            "\n".join(lines[index:index + 2])
            for index in range(0, len(lines), 2)
        )

    def _check_once(self):
        """계좌 잔고를 한 번 조회하고 직전 성공 조회와 보유수량을 비교합니다."""
        if not session_manager.is_authenticated():
            self._last_error = "인증 토큰 없음 또는 세션 만료"
            return

        current_session_key = str(getattr(session_manager, "mode", "") or "")
        if self._session_key != current_session_key:
            self._previous_holdings = None
            self._session_key = current_session_key

        try:
            balance_result = get_account_balance()
        except Exception as exc:
            self._last_error = f"보유 종목 조회 예외: {exc}"
            log_error(f"[보유 종목 변경 감시 오류] {exc}")
            return
        if not balance_result.get("success"):
            self._last_error = balance_result.get("error") or "보유 종목 조회 실패"
            return

        current_holdings = self._normalize_holdings(balance_result)
        previous_holdings = self._previous_holdings
        self._previous_holdings = current_holdings
        self._last_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._last_error = None

        # 최초 성공 조회는 비교 기준으로만 저장합니다.
        if previous_holdings is None:
            return

        message = self._format_changes(previous_holdings, current_holdings)
        if message is None or self._notifier is None:
            return
        try:
            notification_result = self._notifier(message)
            if notification_result is False:
                self._last_error = "변경 알림 전송 실패"
                log_error("[보유 종목 변경 알림 실패] 메시지 전송 결과가 실패입니다.")
        except Exception as exc:
            self._last_error = f"변경 알림 전송 실패: {exc}"
            log_error(f"[보유 종목 변경 알림 실패] {exc}")

    def _run_loop(self):
        while not self._stop_event.is_set():
            if self._is_market_open():
                self._check_once()
            else:
                # 다음 거래일 첫 조회가 새 기준값이 되도록 장외에는 초기화합니다.
                self._previous_holdings = None
            self._stop_event.wait(self._check_interval)


holdings_change_watcher = HoldingsChangeWatcher(check_interval=10)
