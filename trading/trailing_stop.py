"""공용 WebSocket 시세를 이용한 보유 종목 트레일링 스탑 자동매도 엔진."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from api.account import get_account_balance
from api.auth import session_manager
from realtime.engine import realtime_engine
from utils.logger import log_error, log_info
from utils.settings import (
    get_market_hours,
    get_trailing_stop_settings,
    set_trailing_stop_auto_trade_enabled,
)

OrderExecutor = Callable[[str, int], tuple[bool, str]]
Notifier = Callable[[str], None]


@dataclass
class TrailingStockState:
    stock_code: str
    stock_name: str
    purchase_price: int
    quantity: int
    tradable_quantity: int
    peak_price: int = 0
    current_price: int = 0
    profit_rate: float = 0.0
    drawdown_rate: float = 0.0
    activated: bool = False
    order_pending: bool = False
    order_submitted: bool = False
    last_order_attempt: float = 0.0


class TrailingStopWatcher:
    """최소 수익률 이후 고점 대비 하락을 감지해 보유수량을 전량 매도합니다."""

    SUBSCRIBER_ID = "trailing_stop"
    BALANCE_SYNC_INTERVAL = 10
    ORDER_RETRY_INTERVAL = 5

    def __init__(self):
        self._is_running = False
        self._session_active = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._settings_refresh_event = threading.Event()
        self._states: dict[str, TrailingStockState] = {}
        self._order_executor: OrderExecutor | None = None
        self._notifier: Notifier | None = None
        self._drop_rate = 3.5
        self._min_profit_rate = 5.0
        self._last_balance_sync_at: str | None = None
        self._last_tick_at: str | None = None
        self._last_trigger: dict | None = None
        self._last_error: str | None = None
        self._state_lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._is_running

    def configure(
        self,
        order_executor: OrderExecutor,
        notifier: Notifier | None = None,
    ):
        self._order_executor = order_executor
        self._notifier = notifier

    def reload_settings(self):
        """저장된 트레일링 스탑 기준을 실행 중인 감시에 즉시 반영합니다."""
        drop_rate, min_profit_rate = get_trailing_stop_settings()
        with self._state_lock:
            self._drop_rate = drop_rate
            self._min_profit_rate = min_profit_rate
        self._settings_refresh_event.set()

    def _validate_start(self) -> tuple[bool, str]:
        drop_rate, min_profit_rate = get_trailing_stop_settings()
        if drop_rate <= 0 or min_profit_rate <= 0:
            return False, "트레일링 스탑 기준은 각각 0보다 커야 합니다."
        if self._order_executor is None:
            return False, "자동매도 주문 실행기가 설정되지 않았습니다."
        return True, ""

    def start(self, persist: bool = True) -> tuple[bool, str]:
        if self._is_running:
            return False, "⚠️ 트레일링 스탑 감시가 이미 실행 중입니다."
        valid, error = self._validate_start()
        if not valid:
            return False, f"⚠️ 트레일링 스탑 감시를 시작할 수 없습니다: {error}"
        if persist and not set_trailing_stop_auto_trade_enabled(True):
            return False, "⚠️ 트레일링 스탑 활성화 설정을 저장하지 못했습니다."

        self.reload_settings()
        self._stop_event.clear()
        self._settings_refresh_event.clear()
        self._last_error = None
        self._is_running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="TrailingStopWatcherThread",
            daemon=True,
        )
        self._thread.start()
        log_info(
            f"[트레일링 스탑 시작] 고점 대비 하락률: {self._drop_rate:g}%, "
            f"최소 발동 수익률: {self._min_profit_rate:g}%"
        )
        return True, (
            "🚀 트레일링 스탑 감시가 활성화되었습니다. "
            f"(고점 대비 {self._drop_rate:g}% / 최소 수익률 {self._min_profit_rate:g}%)"
        )

    def stop(self, persist: bool = True) -> tuple[bool, str]:
        setting_saved = True
        if persist:
            setting_saved = set_trailing_stop_auto_trade_enabled(False)

        was_running = self._is_running
        self._is_running = False
        self._stop_event.set()
        realtime_engine.unsubscribe(self.SUBSCRIBER_ID)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self._session_active = False
        with self._state_lock:
            self._states = {}

        if not setting_saved:
            return False, (
                "⚠️ 감시와 실시간 시세 수신은 중단했지만 "
                "비활성화 설정을 저장하지 못했습니다."
            )
        if was_running:
            log_info("[트레일링 스탑 중단] 공용 WebSocket 구독을 해제했습니다.")
            return True, "🛑 트레일링 스탑 감시를 중단했습니다."
        return False, "ℹ️ 트레일링 스탑 감시가 실행 중이지 않습니다."

    def shutdown(self):
        self.stop(persist=False)

    def _is_market_open(self, now: datetime | None = None) -> bool:
        current = now or datetime.now()
        if current.weekday() >= 5:
            return False
        start_time, end_time = get_market_hours()
        current_time = current.strftime("%H:%M")
        return start_time <= current_time <= end_time

    @staticmethod
    def _normalize_holdings(balance_result: dict) -> list[dict]:
        normalized = []
        for item in balance_result.get("holdings") or []:
            stock_code = str(item.get("stock_code") or "").strip()
            try:
                quantity = int(item.get("quantity") or 0)
                tradable_quantity = int(item.get("tradable_quantity") or 0)
                purchase_price = int(item.get("purchase_price") or 0)
            except (TypeError, ValueError):
                continue
            if (
                len(stock_code) != 6
                or not stock_code.isdigit()
                or quantity <= 0
                or purchase_price <= 0
            ):
                continue
            normalized.append(
                {
                    "stock_code": stock_code,
                    "stock_name": str(item.get("stock_name") or "").strip(),
                    "quantity": quantity,
                    "tradable_quantity": tradable_quantity,
                    "purchase_price": purchase_price,
                }
            )
        return normalized

    def _sync_holdings(self) -> bool:
        try:
            balance_result = get_account_balance()
        except Exception as exc:
            self._last_error = f"보유 종목 조회 예외: {exc}"
            log_error(f"[트레일링 스탑 잔고 동기화 오류] {exc}")
            return False
        if not balance_result.get("success"):
            self._last_error = balance_result.get("error") or "보유 종목 조회 실패"
            log_error(f"[트레일링 스탑 잔고 동기화 실패] {self._last_error}")
            return False

        holdings = self._normalize_holdings(balance_result)
        current_codes = {item["stock_code"] for item in holdings}
        with self._state_lock:
            for stock_code in list(self._states):
                if stock_code not in current_codes:
                    self._states.pop(stock_code, None)
            for item in holdings:
                stock_code = item["stock_code"]
                state = self._states.get(stock_code)
                if state is None:
                    state = TrailingStockState(**item)
                    self._states[stock_code] = state
                else:
                    position_changed = (
                        state.purchase_price != item["purchase_price"]
                        or state.quantity != item["quantity"]
                    )
                    state.stock_name = item["stock_name"]
                    state.purchase_price = item["purchase_price"]
                    state.quantity = item["quantity"]
                    state.tradable_quantity = item["tradable_quantity"]
                    if position_changed:
                        state.peak_price = 0
                        state.current_price = 0
                        state.profit_rate = 0.0
                        state.drawdown_rate = 0.0
                        state.activated = False
                        state.order_pending = False
                        state.order_submitted = False
                        state.last_order_attempt = 0.0

        self._last_balance_sync_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._last_error = None
        try:
            if current_codes:
                realtime_engine.subscribe(
                    subscriber_id=self.SUBSCRIBER_ID,
                    stock_codes=current_codes,
                    callback=self._handle_tick,
                )
                self._session_active = True
            else:
                realtime_engine.unsubscribe(self.SUBSCRIBER_ID)
                self._session_active = False
        except Exception as exc:
            self._session_active = False
            self._last_error = f"공용 WebSocket 구독 오류: {exc}"
            log_error(f"[트레일링 스탑 WebSocket 구독 오류] {exc}")
            return False
        return True

    def _clear_market_session(self):
        realtime_engine.unsubscribe(self.SUBSCRIBER_ID)
        self._session_active = False
        with self._state_lock:
            self._states = {}

    def _run_loop(self):
        log_info("[트레일링 스탑 루프] 감시 스레드 진입")
        while not self._stop_event.is_set():
            if not self._is_market_open():
                self._clear_market_session()
                self._stop_event.wait(10)
                continue
            if not session_manager.is_authenticated():
                self._last_error = "로그인 토큰이 없거나 만료되었습니다."
                self._clear_market_session()
                self._stop_event.wait(10)
                continue

            self.reload_settings()
            self._settings_refresh_event.clear()
            self._sync_holdings()
            next_sync = time.monotonic() + self.BALANCE_SYNC_INTERVAL

            while (
                not self._stop_event.is_set()
                and self._is_market_open()
                and session_manager.is_authenticated()
            ):
                now = time.monotonic()
                if self._settings_refresh_event.is_set():
                    self.reload_settings()
                    self._settings_refresh_event.clear()
                if now >= next_sync:
                    self._sync_holdings()
                    next_sync = now + self.BALANCE_SYNC_INTERVAL
                self._stop_event.wait(1)

            self._clear_market_session()

        self._clear_market_session()
        log_info("[트레일링 스탑 루프] 감시 스레드 정상 종료")

    def _get_current_sell_quantity(
        self,
        stock_code: str,
    ) -> tuple[int, dict | None, str | None]:
        try:
            balance_result = get_account_balance()
        except Exception as exc:
            log_error(f"[트레일링 스탑 주문 전 잔고 조회 오류] {stock_code}: {exc}")
            return 0, None, f"보유 종목 조회 예외: {exc}"
        if not balance_result.get("success"):
            return 0, None, balance_result.get("error") or "보유 종목 조회 실패"
        for holding in self._normalize_holdings(balance_result):
            if holding["stock_code"] != stock_code:
                continue
            quantity = int(holding["tradable_quantity"])
            if quantity <= 0:
                return 0, holding, "현재 매매가능수량이 없습니다."
            return quantity, holding, None
        return 0, None, "현재 계좌에서 해당 보유 종목을 찾을 수 없습니다."

    def _handle_tick(self, stock_code: str, timestamp: datetime, price: int):
        print(
            f"[TRST 0B] {timestamp.strftime('%H:%M:%S')} {stock_code} {price:,}원",
            flush=True,
        )
        self._last_tick_at = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        if not self._is_running or self._stop_event.is_set() or price <= 0:
            return

        should_sell = False
        signal_snapshot: dict | None = None
        with self._state_lock:
            state = self._states.get(stock_code)
            if state is None or state.order_submitted:
                return
            state.current_price = price
            state.profit_rate = (
                (price - state.purchase_price) / state.purchase_price
            ) * 100
            if price > state.peak_price:
                state.peak_price = price
            if not state.activated and state.profit_rate >= self._min_profit_rate:
                state.activated = True
            state.drawdown_rate = (
                ((state.peak_price - price) / state.peak_price) * 100
                if state.peak_price > 0
                else 0.0
            )
            retry_ready = (
                time.monotonic() - state.last_order_attempt
                >= self.ORDER_RETRY_INTERVAL
            )
            if (
                state.activated
                and state.drawdown_rate >= self._drop_rate
                and not state.order_pending
                and retry_ready
            ):
                state.order_pending = True
                state.last_order_attempt = time.monotonic()
                should_sell = True
                signal_snapshot = {
                    "stock_name": state.stock_name,
                    "purchase_price": state.purchase_price,
                    "peak_price": state.peak_price,
                    "current_price": price,
                    "profit_rate": state.profit_rate,
                    "drawdown_rate": state.drawdown_rate,
                    "drop_rate": self._drop_rate,
                    "min_profit_rate": self._min_profit_rate,
                }

        if not should_sell or signal_snapshot is None:
            return
        self._execute_trailing_sell(stock_code, timestamp, signal_snapshot)

    def _execute_trailing_sell(
        self,
        stock_code: str,
        timestamp: datetime,
        signal: dict,
    ):
        quantity, holding, balance_error = self._get_current_sell_quantity(stock_code)
        stock_name = (holding or {}).get("stock_name") or signal["stock_name"]
        if balance_error:
            success = False
            order_message = f"❌ 트레일링 스탑 자동매도 보류: {balance_error}"
        elif self._order_executor is None:
            success = False
            order_message = "❌ 자동매도 주문 실행기가 설정되지 않았습니다."
        else:
            try:
                success, order_message = self._order_executor(stock_code, quantity)
            except Exception as exc:
                success = False
                order_message = f"❌ 트레일링 스탑 자동매도 실행 오류: {exc}"
                log_error(f"[트레일링 스탑 자동매도 예외] {stock_code}: {exc}")

        with self._state_lock:
            state = self._states.get(stock_code)
            if state is not None:
                state.order_pending = False
                state.order_submitted = success
        if success:
            self._last_error = None
        else:
            self._last_error = order_message

        self._last_trigger = {
            "stock_code": stock_code,
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "quantity": quantity,
            **signal,
        }
        display_name = f"{stock_name} ({stock_code})" if stock_name else stock_code
        notification = (
            "📉 [트레일링 스탑 자동매도 신호]\n\n"
            f"• 종목: {display_name}\n"
            f"• 감지시각: {self._last_trigger['timestamp']}\n"
            f"• 매입가: {signal['purchase_price']:,}원\n"
            f"• 추적 고점: {signal['peak_price']:,}원\n"
            f"• 현재가: {signal['current_price']:,}원\n"
            f"• 현재 수익률: {signal['profit_rate']:.2f}%\n"
            f"• 고점 대비 하락률: {signal['drawdown_rate']:.2f}% "
            f"(기준 {signal['drop_rate']:g}%)\n"
            f"• 최소 발동 수익률: {signal['min_profit_rate']:g}%\n"
            f"• 매도 수량: {quantity:,}주 (매매가능수량 전부)\n\n"
            f"{order_message}"
        )
        log_info(
            f"[트레일링 스탑 신호] {display_name}, 고점 {signal['peak_price']:,}원, "
            f"현재가 {signal['current_price']:,}원, 하락률 {signal['drawdown_rate']:.2f}%"
        )
        if self._notifier is not None:
            try:
                self._notifier(notification)
            except Exception as exc:
                log_error(f"[트레일링 스탑 텔레그램 알림 실패] {exc}")

    def get_status(self) -> dict:
        with self._state_lock:
            stocks = [
                {
                    "stock_code": state.stock_code,
                    "stock_name": state.stock_name,
                    "peak_price": state.peak_price,
                    "current_price": state.current_price,
                    "profit_rate": state.profit_rate,
                    "drawdown_rate": state.drawdown_rate,
                    "activated": state.activated,
                    "order_submitted": state.order_submitted,
                }
                for state in self._states.values()
            ]
            drop_rate = self._drop_rate
            min_profit_rate = self._min_profit_rate
        return {
            "is_running": self._is_running,
            "session_active": self._session_active,
            "drop_rate": drop_rate,
            "min_profit_rate": min_profit_rate,
            "monitored_count": len(stocks),
            "stocks": stocks,
            "last_balance_sync_at": self._last_balance_sync_at,
            "last_tick_at": self._last_tick_at,
            "last_trigger": self._last_trigger,
            "last_error": self._last_error,
        }


trailing_stop_watcher = TrailingStopWatcher()
