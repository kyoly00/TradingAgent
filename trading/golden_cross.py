"""1분봉 이동평균 골든크로스 감시 및 자동매수 엔진."""

import threading
from collections import deque
from collections.abc import Callable
from datetime import datetime

from api.auth import session_manager
from api.minute_chart import get_minute_chart
from realtime.engine import realtime_engine
from utils.logger import log_error, log_info
from utils.settings import (
    get_golden_cross_intervals,
    get_golden_cross_stocks,
    get_market_hours,
    set_golden_cross_auto_trade_enabled,
)

OrderExecutor = Callable[[str, int], tuple[bool, str]]
Notifier = Callable[[str], None]


class MovingAverageCrossDetector:
    """종목 하나의 1분봉 종가와 이동평균 교차 상태를 관리합니다."""

    def __init__(self, short_period: int, long_period: int):
        if short_period < 1 or long_period < 1 or short_period >= long_period:
            raise ValueError("이동평균 주기는 1 <= 단기 < 장기 조건이어야 합니다.")
        self.short_period = short_period
        self.long_period = long_period
        self._bars: deque[tuple[str, int]] = deque(maxlen=long_period)
        self._previous_short_ma: float | None = None
        self._previous_long_ma: float | None = None

    def seed(self, bars: list[dict]) -> bool:
        """과거 분봉으로 초기 이동평균 상태를 생성합니다."""
        normalized: dict[str, int] = {}
        for bar in bars:
            minute_key = str(bar.get("timestamp") or "")[:12]
            try:
                close = int(bar.get("close") or 0)
            except (TypeError, ValueError):
                continue
            if len(minute_key) == 12 and close > 0:
                normalized[minute_key] = close

        self._bars.clear()
        for minute_key in sorted(normalized)[-self.long_period :]:
            self._bars.append((minute_key, normalized[minute_key]))

        averages = self._calculate_averages()
        if averages is None:
            return False
        self._previous_short_ma, self._previous_long_ma = averages
        return True

    def _calculate_averages(self) -> tuple[float, float] | None:
        if len(self._bars) < self.long_period:
            return None
        prices = [price for _, price in self._bars]
        short_ma = sum(prices[-self.short_period :]) / self.short_period
        long_ma = sum(prices[-self.long_period :]) / self.long_period
        return short_ma, long_ma

    def update(self, timestamp: datetime, price: int) -> dict | None:
        """실시간 체결가로 현재 1분봉을 갱신하고 교차 결과를 반환합니다."""
        if price <= 0:
            return None
        minute_key = timestamp.strftime("%Y%m%d%H%M")
        if self._bars and minute_key < self._bars[-1][0]:
            return None
        if self._bars and minute_key == self._bars[-1][0]:
            self._bars[-1] = (minute_key, price)
        else:
            self._bars.append((minute_key, price))

        averages = self._calculate_averages()
        if averages is None:
            return None
        short_ma, long_ma = averages
        crossed_up = (
            self._previous_short_ma is not None
            and self._previous_long_ma is not None
            and self._previous_short_ma <= self._previous_long_ma
            and short_ma > long_ma
        )
        crossed_down = (
            self._previous_short_ma is not None
            and self._previous_long_ma is not None
            and self._previous_short_ma >= self._previous_long_ma
            and short_ma < long_ma
        )
        self._previous_short_ma = short_ma
        self._previous_long_ma = long_ma
        return {
            "crossed_up": crossed_up,
            "crossed_down": crossed_down,
            "short_ma": short_ma,
            "long_ma": long_ma,
            "price": price,
            "minute": minute_key,
        }


class GoldenCrossWatcher:
    """장 시간 동안 골든크로스를 감지해 종목별 설정 금액으로 자동매수합니다."""

    SUBSCRIBER_ID = "golden_cross"

    def __init__(self):
        self._is_running = False
        self._session_active = False
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._refresh_event = threading.Event()
        self._detectors: dict[str, MovingAverageCrossDetector] = {}
        self._targets: dict[str, dict] = {}
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
        if not get_golden_cross_stocks():
            return False, "등록된 대상 종목이 없습니다. 먼저 `gdcrs add`를 실행해 주세요."
        if self._order_executor is None:
            return False, "자동매수 주문 실행기가 설정되지 않았습니다."
        return True, ""

    def start(self, persist: bool = True) -> tuple[bool, str]:
        """감시 스레드를 시작하고 장 시작마다 실시간 세션을 자동 실행합니다."""
        if self._is_running:
            return False, "⚠️ 골든크로스 감시가 이미 실행 중입니다."
        valid, error = self._validate_start()
        if not valid:
            return False, f"⚠️ 골든크로스 감시를 시작할 수 없습니다: {error}"
        if persist and not set_golden_cross_auto_trade_enabled(True):
            return False, "⚠️ 골든크로스 활성화 설정을 저장하지 못했습니다."

        self._stop_event.clear()
        self._refresh_event.clear()
        self._last_error = None
        self._is_running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="GoldenCrossWatcherThread",
            daemon=True,
        )
        self._thread.start()

        short_period, long_period = get_golden_cross_intervals()
        target_count = len(get_golden_cross_stocks())
        log_info(
            f"[골든크로스 시작] 단기 MA: {short_period}, 장기 MA: {long_period}, "
            f"대상: {target_count}개"
        )
        return True, (
            "🚀 골든크로스 감시가 활성화되었습니다. "
            f"(단기 {short_period} / 장기 {long_period}, 대상 {target_count}개)"
        )

    def stop(self, persist: bool = True) -> tuple[bool, str]:
        """실시간 연결과 감시 스레드를 즉시 중단합니다."""
        setting_saved = True
        if persist:
            setting_saved = set_golden_cross_auto_trade_enabled(False)

        was_running = self._is_running
        self._is_running = False
        self._stop_event.set()
        realtime_engine.unsubscribe(self.SUBSCRIBER_ID)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self._thread = None
        self._session_active = False
        self._detectors = {}
        self._targets = {}
        if not setting_saved:
            log_error("[골든크로스 중단] 런타임은 중단했으나 비활성화 설정 저장에 실패했습니다.")
            return False, (
                "⚠️ 감시와 실시간 시세 수신은 중단했지만 "
                "비활성화 설정을 저장하지 못했습니다."
            )
        if was_running:
            log_info("[골든크로스 중단] 감시 루프와 WebSocket 연결이 중단되었습니다.")
            return True, "🛑 골든크로스 감시와 실시간 시세 수신을 중단했습니다."
        return False, "ℹ️ 골든크로스 감시가 실행 중이지 않습니다."

    def shutdown(self):
        """프로그램 종료 시 활성화 설정은 유지하고 런타임만 정리합니다."""
        self.stop(persist=False)

    def request_refresh(self):
        """종목·주기 변경 내용을 반영하도록 현재 실시간 세션을 재시작합니다."""
        if not self._is_running:
            return
        self._refresh_event.set()
        realtime_engine.unsubscribe(self.SUBSCRIBER_ID)

    def _is_market_open(self, now: datetime | None = None) -> bool:
        current = now or datetime.now()
        if current.weekday() >= 5:
            return False
        start_time, end_time = get_market_hours()
        current_time = current.strftime("%H:%M")
        return start_time <= current_time <= end_time

    def _initialize_detectors(self) -> list[str]:
        short_period, long_period = get_golden_cross_intervals()
        if short_period >= long_period:
            raise RuntimeError("단기 이동평균 주기는 장기 주기보다 작아야 합니다.")

        targets = get_golden_cross_stocks()
        detectors: dict[str, MovingAverageCrossDetector] = {}
        target_map: dict[str, dict] = {}
        initialization_errors = []
        for target in targets:
            stock_code = target["stock_code"]
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
            target_map.setdefault(stock_code, target)

        with self._state_lock:
            self._detectors = detectors
            self._targets = target_map
        if initialization_errors:
            self._last_error = " | ".join(initialization_errors)
            log_error(f"[골든크로스 초기화 일부 실패] {self._last_error}")
        else:
            self._last_error = None
        return list(detectors)

    def _run_loop(self):
        log_info("[골든크로스 루프] 감시 스레드 진입")
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
                self._refresh_event.clear()
                stock_codes = self._initialize_detectors()
                if not stock_codes:
                    self._last_error = self._last_error or "초기화된 감시 종목이 없습니다."
                    self._stop_event.wait(10)
                    continue

                realtime_engine.subscribe(
                    subscriber_id=self.SUBSCRIBER_ID,
                    stock_codes=stock_codes,
                    callback=self._handle_tick,
                )
                self._session_active = True
                while (
                    not self._stop_event.is_set()
                    and self._is_market_open()
                    and not self._refresh_event.is_set()
                ):
                    self._stop_event.wait(1)
            except Exception as exc:
                if not self._stop_event.is_set():
                    self._last_error = str(exc)
                    log_error(f"[골든크로스 감시 세션 오류] {exc}")
                    self._stop_event.wait(10)
            finally:
                realtime_engine.unsubscribe(self.SUBSCRIBER_ID)
                self._session_active = False

        log_info("[골든크로스 루프] 감시 스레드 정상 종료")

    def _handle_tick(self, stock_code: str, timestamp: datetime, price: int):
        if (
            not self._is_running
            or self._stop_event.is_set()
            or self._refresh_event.is_set()
        ):
            return
        detector = self._detectors.get(stock_code)
        target = self._targets.get(stock_code)
        if detector is None or target is None:
            return

        result = detector.update(timestamp, price)
        self._last_checked_at = timestamp.strftime("%Y-%m-%d %H:%M:%S")
        if not result or not result["crossed_up"]:
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
        amount = int(target["amount"])
        log_info(
            f"[골든크로스 감지] 종목: {stock_code}, 현재가: {price:,}원, "
            f"단기 MA: {result['short_ma']:.2f}, 장기 MA: {result['long_ma']:.2f}, "
            f"매수 설정금액: {amount:,}원"
        )

        if self._order_executor is None:
            self._last_error = "자동매수 주문 실행기가 설정되지 않았습니다."
            return

        try:
            success, order_message = self._order_executor(stock_code, amount)
        except Exception as exc:
            success = False
            order_message = f"❌ 골든크로스 자동매수 실행 오류: {exc}"
            log_error(f"[골든크로스 자동매수 예외] 종목: {stock_code}, 오류: {exc}")
        if success:
            self._ordered_on_date[stock_code] = trade_date
            self._last_error = None
        else:
            self._last_error = order_message

        notification = (
            "📈 [골든크로스 자동매수 신호]\n\n"
            f"• 종목코드: {stock_code}\n"
            f"• 감지시각: {self._last_checked_at}\n"
            f"• 현재가: {price:,}원\n"
            f"• 단기 MA: {result['short_ma']:.2f}\n"
            f"• 장기 MA: {result['long_ma']:.2f}\n"
            f"• 설정금액: {amount:,}원\n\n"
            f"{order_message}"
        )
        if self._notifier is not None:
            try:
                self._notifier(notification)
            except Exception as exc:
                log_error(f"[골든크로스 텔레그램 알림 실패] {exc}")

    def get_status(self) -> dict:
        """명령 및 stts 출력용 현재 감시 상태를 반환합니다."""
        short_period, long_period = get_golden_cross_intervals()
        with self._state_lock:
            monitored_codes = list(self._detectors)
        return {
            "is_running": self._is_running,
            "session_active": self._session_active,
            "short_period": short_period,
            "long_period": long_period,
            "configured_count": len(get_golden_cross_stocks()),
            "monitored_count": len(monitored_codes),
            "monitored_codes": monitored_codes,
            "last_checked_at": self._last_checked_at,
            "last_cross": self._last_cross,
            "last_error": self._last_error,
        }


golden_cross_watcher = GoldenCrossWatcher()
