"""여러 실시간 기능이 하나의 키움 WebSocket 연결을 공유하는 공용 엔진."""

import threading
import queue
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from realtime.kiwoom_websocket import KiwoomRealtimeClient
from utils.logger import log_error, log_info

TickCallback = Callable[[str, datetime, int], None]
ClientFactory = Callable[[], KiwoomRealtimeClient]


@dataclass
class _Subscription:
    stock_codes: set[str]
    callback: TickCallback
    tick_queue: queue.Queue[tuple[str, datetime, int] | None] = field(
        default_factory=queue.Queue
    )
    active: bool = True
    worker: threading.Thread | None = None


@dataclass
class _WebSocketRequest:
    payload: dict
    expected_trnm: str
    completed: threading.Event = field(default_factory=threading.Event)
    response: dict | None = None
    error: str | None = None
    sent: bool = False


class SharedRealtimeEngine:
    """구독 종목을 통합하고 단일 WebSocket의 틱을 각 기능에 분배합니다."""

    def __init__(self, client_factory: ClientFactory | None = None):
        self._client_factory = client_factory or (
            lambda: KiwoomRealtimeClient(group_number="1")
        )
        self._subscriptions: dict[str, _Subscription] = {}
        self._requests: list[_WebSocketRequest] = []
        self._condition = threading.Condition()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._refresh_event = threading.Event()
        self._client: KiwoomRealtimeClient | None = None
        self._connected = False
        self._last_error: str | None = None

    def request(
        self,
        payload: dict,
        expected_trnm: str,
        timeout: float = 10.0,
    ) -> dict:
        """공용 연결로 WebSocket TR을 전송하고 지정한 TR 응답을 기다립니다."""
        if not isinstance(payload, dict) or not payload:
            raise ValueError("WebSocket 요청 payload가 비어 있습니다.")
        normalized_trnm = str(expected_trnm).strip()
        if not normalized_trnm:
            raise ValueError("응답 TR명이 비어 있습니다.")
        if timeout <= 0:
            raise ValueError("응답 대기 시간은 0보다 커야 합니다.")

        request = _WebSocketRequest(dict(payload), normalized_trnm)
        with self._condition:
            self._requests.append(request)
            self._ensure_thread_locked()
            self._condition.notify_all()

        if not request.completed.wait(timeout):
            with self._condition:
                if request in self._requests:
                    self._requests.remove(request)
            raise TimeoutError(
                f"WebSocket TR 응답 시간이 초과되었습니다: {normalized_trnm}"
            )
        if request.error:
            raise RuntimeError(request.error)
        if request.response is None:
            raise RuntimeError(f"WebSocket TR 응답이 비어 있습니다: {normalized_trnm}")
        return request.response

    def subscribe(
        self,
        subscriber_id: str,
        stock_codes: list[str] | set[str] | tuple[str, ...],
        callback: TickCallback,
    ):
        """기능별 종목과 틱 콜백을 등록하고 공용 연결에 반영합니다."""
        clean_id = str(subscriber_id).strip()
        if not clean_id:
            raise ValueError("subscriber_id가 비어 있습니다.")
        if not callable(callback):
            raise TypeError("callback은 호출 가능해야 합니다.")

        normalized_codes = {
            str(code).strip()
            for code in stock_codes
            if str(code).strip()
        }
        if not normalized_codes:
            raise ValueError("구독할 종목코드가 없습니다.")

        should_refresh = False
        with self._condition:
            had_subscriptions = bool(self._subscriptions)
            previous = self._subscriptions.get(clean_id)
            previous_codes = previous.stock_codes if previous else None
            if previous is None:
                subscription = _Subscription(normalized_codes, callback)
                subscription.worker = threading.Thread(
                    target=self._run_subscriber,
                    args=(clean_id, subscription),
                    name=f"RealtimeSubscriber-{clean_id}",
                    daemon=True,
                )
                self._subscriptions[clean_id] = subscription
                subscription.worker.start()
            else:
                previous.stock_codes = normalized_codes
                previous.callback = callback
            codes_changed = previous_codes != normalized_codes
            should_refresh = codes_changed and (
                previous is not None
                or had_subscriptions
                or self._client is not None
            )
            self._ensure_thread_locked()
            self._condition.notify_all()

        if should_refresh:
            self._request_reconnect()

    def unsubscribe(self, subscriber_id: str):
        """기능 구독을 제거하고 남은 구독 종목으로 공용 연결을 재구성합니다."""
        clean_id = str(subscriber_id).strip()
        with self._condition:
            removed = self._subscriptions.pop(clean_id, None)
            self._condition.notify_all()
        if removed is not None:
            removed.active = False
            removed.tick_queue.put(None)
            self._request_reconnect()

    def _ensure_thread_locked(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._refresh_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="SharedRealtimeEngineThread",
            daemon=True,
        )
        self._thread.start()

    def _request_reconnect(self):
        self._refresh_event.set()
        current_client = self._client
        if current_client is not None:
            current_client.close()

    def _get_combined_stock_codes(self) -> list[str]:
        with self._condition:
            combined = set()
            for subscription in self._subscriptions.values():
                combined.update(subscription.stock_codes)
        return sorted(combined)

    def _has_work(self) -> bool:
        with self._condition:
            return bool(self._subscriptions or self._requests)

    def _take_outbound_requests(self) -> list[dict]:
        with self._condition:
            pending = [request for request in self._requests if not request.sent]
            for request in pending:
                request.sent = True
        return [dict(request.payload) for request in pending]

    def _handle_message(self, message: dict):
        response_trnm = str(message.get("trnm") or "").strip()
        if not response_trnm:
            return
        matched: _WebSocketRequest | None = None
        with self._condition:
            for request in self._requests:
                if request.sent and request.expected_trnm == response_trnm:
                    matched = request
                    request.response = message
                    self._requests.remove(request)
                    break
        if matched is not None:
            matched.completed.set()

    def _run_loop(self):
        log_info("[공용 WebSocket 엔진] 실행 스레드 시작")
        while not self._stop_event.is_set():
            with self._condition:
                while (
                    not self._subscriptions
                    and not self._requests
                    and not self._stop_event.is_set()
                ):
                    self._connected = False
                    self._condition.wait()
                if self._stop_event.is_set():
                    break

            self._refresh_event.clear()
            stock_codes = self._get_combined_stock_codes()

            client = self._client_factory()
            self._client = client
            try:
                if self._refresh_event.is_set():
                    continue
                client.run(
                    stock_codes=stock_codes,
                    on_tick=self._dispatch_tick,
                    stop_event=self._stop_event,
                    should_continue=lambda: (
                        self._has_work()
                        and not self._refresh_event.is_set()
                    ),
                    on_connected=self._mark_connected,
                    outbound_provider=self._take_outbound_requests,
                    on_message=self._handle_message,
                )
                self._last_error = None
            except Exception as exc:
                if not self._stop_event.is_set() and not self._refresh_event.is_set():
                    self._last_error = str(exc)
                    log_error(f"[공용 WebSocket 엔진 오류] {exc}")
                    self._stop_event.wait(3)
            finally:
                self._connected = False
                self._client = None
                with self._condition:
                    for request in self._requests:
                        request.sent = False

        self._connected = False
        log_info("[공용 WebSocket 엔진] 실행 스레드 종료")

    def _mark_connected(self):
        self._connected = True

    def _dispatch_tick(self, stock_code: str, timestamp: datetime, price: int):
        self._connected = True
        with self._condition:
            subscriptions = [
                subscription
                for subscription in self._subscriptions.values()
                if stock_code in subscription.stock_codes
            ]

        for subscription in subscriptions:
            subscription.tick_queue.put((stock_code, timestamp, price))

    @staticmethod
    def _run_subscriber(subscriber_id: str, subscription: _Subscription):
        while True:
            tick = subscription.tick_queue.get()
            if tick is None:
                return
            if not subscription.active:
                continue
            try:
                subscription.callback(*tick)
            except Exception as exc:
                log_error(
                    f"[공용 WebSocket 틱 콜백 오류] 구독: {subscriber_id}, "
                    f"종목: {tick[0]}, 오류: {exc}"
                )

    def get_status(self) -> dict:
        """공용 연결과 기능별 구독 현황을 반환합니다."""
        with self._condition:
            subscribers = {
                subscriber_id: sorted(subscription.stock_codes)
                for subscriber_id, subscription in self._subscriptions.items()
            }
            pending_request_count = len(self._requests)
        combined_codes = sorted(
            {code for stock_codes in subscribers.values() for code in stock_codes}
        )
        return {
            "is_running": self._thread is not None and self._thread.is_alive(),
            "connected": self._connected,
            "subscriber_count": len(subscribers),
            "subscribers": subscribers,
            "stock_codes": combined_codes,
            "stock_count": len(combined_codes),
            "pending_request_count": pending_request_count,
            "last_error": self._last_error,
        }

    def shutdown(self):
        """프로그램 종료 시 공용 WebSocket과 엔진 스레드를 정리합니다."""
        self._stop_event.set()
        self._refresh_event.set()
        with self._condition:
            subscriptions = list(self._subscriptions.values())
            requests = list(self._requests)
            self._subscriptions.clear()
            self._requests.clear()
            self._condition.notify_all()
        for subscription in subscriptions:
            subscription.active = False
            subscription.tick_queue.put(None)
        for request in requests:
            request.error = "공용 WebSocket 엔진이 종료되었습니다."
            request.completed.set()
        current_client = self._client
        if current_client is not None:
            current_client.close()
        current_thread = self._thread
        if current_thread is not None and current_thread.is_alive():
            current_thread.join(timeout=5)
        self._thread = None
        self._client = None
        self._connected = False


realtime_engine = SharedRealtimeEngine()
