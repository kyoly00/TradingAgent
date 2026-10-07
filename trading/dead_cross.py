"""보유 종목의 1분봉 데드크로스 감시 및 자동매도 엔진."""

import threading
from collections.abc import Callable
from datetime import datetime

from api.account import get_account_balance
from api.auth import session_manager
from api.minute_chart import get_minute_chart
from realtime.kiwoom_websocket import KiwoomRealtimeClient
from trading.golden_cross import MovingAverageCrossDetector
from utils.logger import log_error, log_info
from utils.settings import (
    get_golden_cross_intervals,
    get_market_hours,
    set_dead_cross_auto_trade_enabled,
)

OrderExecutor = Callable[[str, int], tuple[bool, str]]
Notifier = Callable[[str], None]


class DeadCrossWatcher:
    """장 시간 동안 보유 종목의 데드크로스를 감지해 전량 자동매도합니다."""

    def __init__(self):
        self._is_running = False
        self._session_active = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._client: KiwoomRealtimeClient | None = None
        self._detectors: dict[str, MovingAverageCrossDetector] = {}
        self._holdings: dict[str, dict] = {}
        self._ordered_on_date: dict[str, str] = {}
        self._order_executor: OrderExecutor | None = None
        self._notifier: Notifier | None = None
        self._last_checked_at: str | None = None
        self._last_cross: dict | None = None
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
        """주문 실행과 사용자 알림 콜백을 주입합니다."""
        self._order_executor = order_executor
        self._notifier = notifier

    def _validate_start(self) -> tuple[bool, str]:
        short_period, long_period = get_golden_cross_intervals()
        if short_period >= long_period:
            return False, "단기 이동평균 주기는 장기 주기보다 작아야 합니다."
        if self._order_executor is None:
            return False, "자동매도 주문 실행기가 설정되지 않았습니다."
        return True, ""

    def start(self, persist: bool = True) -> tuple[bool, str]:
        """감시 스레드를 시작하고 장 시작마다 실시간 세션을 자동 실행합니다."""
        if self._is_running:
            return False, "⚠️ 데드크로스 감시가 이미 실행 중입니다."
        valid, error = self._validate_start()
        if not valid:
            return False, f"⚠️ 데드크로스 감시를 시작할 수 없습니다: {error}"
        if persist and not set_dead_cross_auto_trade_enabled(True):
            return False, "⚠️ 데드크로스 활성화 설정을 저장하지 못했습니다."

        self._stop_event.clear()
        self._last_error = None
        self._is_running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="DeadCrossWatcherThread",
            daemon=True,
        )
        self._thread.start()

        short_period, long_period = get_golden_cross_intervals()
        log_info(f"[데드크로스 시작] 단기 MA: {short_period}, 장기 MA: {long_period}")
        return True, (
            "🚀 데드크로스 감시가 활성화되었습니다. "
            f"(단기 {short_period} / 장기 {long_period}, 보유 종목 자동 조회)"
        )

    def stop(self, persist: bool = True) -> tuple[bool, str]:
        """실시간 연결과 감시 스레드를 즉시 중단합니다."""
        setting_saved = True
        if persist:
            setting_saved = set_dead_cross_auto_trade_enabled(False)

        was_running = self._is_running
        self._is_running = False
        self._stop_event.set()
        current_client = self._client
        if current_client is not None:
            current_client.close()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self._session_active = False
        with self._state_lock:
            self._detectors = {}
            self._holdings = {}

        if not setting_saved:
            log_error("[데드크로스 중단] 런타임은 중단했으나 비활성화 설정 저장에 실패했습니다.")
            return False, (
                "⚠️ 감시와 실시간 시세 수신은 중단했지만 "
                "비활성화 설정을 저장하지 못했습니다."
            )
        if was_running:
            log_info("[데드크로스 중단] 감시 루프와 WebSocket 연결이 중단되었습니다.")
            return True, "🛑 데드크로스 감시와 실시간 시세 수신을 중단했습니다."
        return False, "ℹ️ 데드크로스 감시가 실행 중이지 않습니다."

    def shutdown(self):
        """프로그램 종료 시 활성화 설정은 유지하고 런타임만 정리합니다."""
        self.stop(persist=False)

    def _is_market_open(self, now: datetime | None = None) -> bool:
        current = now or datetime.now()
        if current.weekday() >= 5:
            return False
        start_time, end_time = get_market_hours()
        current_time = current.strftime("%H:%M")
        return start_time <= current_time <= end_time

    @staticmethod
    def _tradable_holdings(balance_result: dict) -> list[dict]:
        holdings = []
        for item in balance_result.get("holdings") or []:
            stock_code = str(item.get("stock_code") or "").strip()
            try:
                quantity = int(item.get("quantity") or 0)
                tradable_quantity = int(item.get("tradable_quantity") or 0)
            except (TypeError, ValueError):
                continue
            if len(stock_code) != 6 or not stock_code.isdigit() or quantity <= 0:
                continue
            normalized = dict(item)
            normalized["stock_code"] = stock_code
            normalized["quantity"] = quantity
            normalized["tradable_quantity"] = tradable_quantity
            holdings.append(normalized)
        return holdings

    def _initialize_detectors(self) -> list[str]:
        short_period, long_period = get_golden_cross_intervals()
        if short_period >= long_period:
            raise RuntimeError("단기 이동평균 주기는 장기 주기보다 작아야 합니다.")

        balance_result = get_account_balance()
        if not balance_result.get("success"):
            raise RuntimeError(balance_result.get("error") or "보유 종목 조회에 실패했습니다.")
        holdings = self._tradable_holdings(balance_result)
        detectors: dict[str, MovingAverageCrossDetector] = {}
        holding_map: dict[str, dict] = {}
        initialization_errors = []

        for holding in holdings:
            stock_code = holding["stock_code"]
            chart_result = get_minute_chart(
                stock_code=stock_code,
                minute_scope=1,
                limit=long_period + 1,
            )
            if not chart_result.get("success"):
                initialization_errors.append(
                    f"{stock_code}: {chart_result.get('error', '분봉 조회 실패')}"
                )
                continue

            detector = MovingAverageCrossDetector(short_period, long_period)
            if not detector.seed(chart_result.get("bars") or []):
                initialization_errors.append(
                    f"{stock_code}: 장기 이동평균 계산에 필요한 분봉이 부족합니다."
                )
                continue
            detectors[stock_code] = detector
            holding_map[stock_code] = holding

        with self._state_lock:
            self._detectors = detectors
            self._holdings = holding_map
        if initialization_errors:
            self._last_error = " | ".join(initialization_errors)
            log_error(f"[데드크로스 초기화 일부 실패] {self._last_error}")
        else:
            self._last_error = None
        return list(detectors)

    def _run_loop(self):
        log_info("[데드크로스 루프] 감시 스레드 진입")
        while not self._stop_event.is_set():
            if not self._is_market_open():
                self._session_active = False
                self._stop_event.wait(10)
                continue
            if not session_manager.is_authenticated():
                self._last_error = "로그인 토큰이 없거나 만료되었습니다."
                self._stop_event.wait(10)
                continue

            try:
                stock_codes = self._initialize_detectors()
                if not stock_codes:
                    self._last_error = self._last_error or "매도 가능한 보유 종목이 없습니다."
                    self._stop_event.wait(10)
                    continue

                self._client = KiwoomRealtimeClient(group_number="2")
                self._session_active = True
                self._client.run(
                    stock_codes=stock_codes,
                    on_tick=self._handle_tick,
                    stop_event=self._stop_event,
                    should_continue=self._is_market_open,
                )
            except Exception as exc:
                if not self._stop_event.is_set():
                    self._last_error = str(exc)
                    log_error(f"[데드크로스 감시 세션 오류] {exc}")
                    self._stop_event.wait(10)
            finally:
                self._session_active = False
                self._client = None

        log_info("[데드크로스 루프] 감시 스레드 정상 종료")

    def _get_current_sell_quantity(self, stock_code: str) -> tuple[int, dict | None, str | None]:
        """주문 직전 잔고를 재조회하여 실제 매매가능수량을 반환합니다."""
        balance_result = get_account_balance()
        if not balance_result.get("success"):
            return 0, None, balance_result.get("error") or "보유 종목 조회에 실패했습니다."
        for holding in self._tradable_holdings(balance_result):
            if holding["stock_code"] != stock_code:
                continue
            quantity = int(holding.get("tradable_quantity") or 0)
            if quantity <= 0:
                return 0, holding, "현재 매매가능수량이 없습니다."
            return quantity, holding, None
        return 0, None, "현재 계좌에서 해당 보유 종목을 찾을 수 없습니다."

    def _handle_tick(self, stock_code: str, timestamp: datetime, price: int):
        if not self._is_running or self._stop_event.is_set():
            return
        detector = self._detectors.get(stock_code)
        if detector is None:
            return

        result = detector.update(timestamp, price)
        self._last_checked_at = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        if not result or not result["crossed_down"]:
            return

        trade_date = timestamp.strftime("%Y%m%d")
        if self._ordered_on_date.get(stock_code) == trade_date:
            return

        self._last_cross = {
            "stock_code": stock_code,
            "timestamp": self._last_checked_at,
            "price": price,
            "short_ma": result["short_ma"],
            "long_ma": result["long_ma"],
        }
        sell_quantity, holding, balance_error = self._get_current_sell_quantity(stock_code)
        stock_name = (holding or self._holdings.get(stock_code) or {}).get("stock_name", "")
        log_info(
            f"[데드크로스 감지] 종목: {stock_name}({stock_code}), 현재가: {price:,}원, "
            f"단기 MA: {result['short_ma']:.2f}, 장기 MA: {result['long_ma']:.2f}, "
            f"매도가능수량: {sell_quantity:,}주"
        )

        if balance_error:
            success = False
            order_message = f"❌ 데드크로스 자동매도 보류: {balance_error}"
        elif self._order_executor is None:
            success = False
            order_message = "❌ 자동매도 주문 실행기가 설정되지 않았습니다."
        else:
            try:
                success, order_message = self._order_executor(stock_code, sell_quantity)
            except Exception as exc:
                success = False
                order_message = f"❌ 데드크로스 자동매도 실행 오류: {exc}"
                log_error(f"[데드크로스 자동매도 예외] 종목: {stock_code}, 오류: {exc}")

        if success:
            self._ordered_on_date[stock_code] = trade_date
            self._last_error = None
        else:
            self._last_error = order_message

        display_name = f"{stock_name} ({stock_code})" if stock_name else stock_code
        notification = (
            "📉 [데드크로스 자동매도 신호]\n\n"
            f"• 종목: {display_name}\n"
            f"• 감지시각: {self._last_checked_at}\n"
            f"• 현재가: {price:,}원\n"
            f"• 단기 MA: {result['short_ma']:.2f}\n"
            f"• 장기 MA: {result['long_ma']:.2f}\n"
            f"• 매도 수량: {sell_quantity:,}주 (매매가능수량 전부)\n\n"
            f"{order_message}"
        )
        if self._notifier is not None:
            try:
                self._notifier(notification)
            except Exception as exc:
                log_error(f"[데드크로스 텔레그램 알림 실패] {exc}")

    def get_status(self) -> dict:
        """명령 및 stts 출력용 현재 감시 상태를 반환합니다."""
        short_period, long_period = get_golden_cross_intervals()
        with self._state_lock:
            monitored_codes = list(self._detectors)
            holdings = [dict(item) for item in self._holdings.values()]
        return {
            "is_running": self._is_running,
            "session_active": self._session_active,
            "short_period": short_period,
            "long_period": long_period,
            "monitored_count": len(monitored_codes),
            "monitored_codes": monitored_codes,
            "holdings": holdings,
            "last_checked_at": self._last_checked_at,
            "last_cross": self._last_cross,
            "last_error": self._last_error,
        }


dead_cross_watcher = DeadCrossWatcher()
