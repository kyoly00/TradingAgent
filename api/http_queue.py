"""프로그램의 모든 HTTP 요청을 조정하는 전역 속도 제한 대기열."""

import threading
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import requests

PAPER_API_HOST = "mockapi.kiwoom.com"
PAPER_TR_INTERVAL_SECONDS = 1.05


def _freeze(value: Any) -> Any:
    """요청 인자를 순서와 무관하게 비교 가능한 불변 구조로 변환합니다."""
    if isinstance(value, Mapping):
        items = ((_freeze(key), _freeze(item)) for key, item in value.items())
        return ("mapping", tuple(sorted(items, key=repr)))
    if isinstance(value, (list, tuple)):
        return ("sequence", tuple(_freeze(item) for item in value))
    if isinstance(value, (set, frozenset)):
        return ("set", tuple(sorted((_freeze(item) for item in value), key=repr)))
    if isinstance(value, bytearray):
        return ("bytes", bytes(value))
    try:
        hash(value)
    except TypeError:
        return ("object", type(value).__qualname__, repr(value))
    return ("value", type(value).__qualname__, value)


@dataclass
class _QueuedRequest:
    key: Any
    method: str
    url: str
    kwargs: dict[str, Any]
    completed: threading.Event = field(default_factory=threading.Event)
    response: Any = None
    error: BaseException | None = None


class HttpRequestQueue:
    """HTTP 요청 시작을 제한하고 대기·실행 중인 완전 중복 요청을 병합합니다."""

    def __init__(
        self,
        max_requests: int = 4,
        interval_seconds: float = 1.0,
        paper_tr_interval_seconds: float = PAPER_TR_INTERVAL_SECONDS,
        request_executor: Callable[..., Any] | None = None,
    ):
        if max_requests < 1:
            raise ValueError("max_requests는 1 이상이어야 합니다.")
        if interval_seconds <= 0:
            raise ValueError("interval_seconds는 0보다 커야 합니다.")
        if paper_tr_interval_seconds <= 0:
            raise ValueError("모의투자 TR 호출 간격은 0보다 커야 합니다.")

        self._max_requests = max_requests
        self._interval_seconds = interval_seconds
        self._paper_tr_interval_seconds = paper_tr_interval_seconds
        self._request_executor = request_executor or requests.request
        self._queue: deque[_QueuedRequest] = deque()
        self._pending_by_key: dict[Any, _QueuedRequest] = {}
        self._dispatch_times: deque[float] = deque()
        self._last_paper_tr_dispatch: dict[str, float] = {}
        self._condition = threading.Condition()
        self._dispatcher = threading.Thread(
            target=self._dispatch_loop,
            name="HttpRequestQueueDispatcher",
            daemon=True,
        )
        self._dispatcher.start()

    @staticmethod
    def _make_key(method: str, url: str, kwargs: dict[str, Any]) -> Any:
        return method.upper(), str(url), _freeze(kwargs)

    @staticmethod
    def _paper_tr_id(url: str, kwargs: dict[str, Any]) -> str:
        """모의투자 요청이면 api-id를 반환하고 그 외에는 빈 문자열을 반환합니다."""
        if PAPER_API_HOST not in str(url).lower():
            return ""
        headers = kwargs.get("headers")
        if not isinstance(headers, Mapping):
            return ""
        for key, value in headers.items():
            if str(key).strip().lower() == "api-id":
                return str(value or "").strip().lower()
        return ""

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        """요청을 대기열에 넣고 실행 결과 또는 실행 예외를 호출자에게 전달합니다."""
        normalized_method = str(method).strip().upper()
        if not normalized_method:
            raise ValueError("HTTP 메서드가 비어 있습니다.")
        key = self._make_key(normalized_method, url, kwargs)

        with self._condition:
            queued_request = self._pending_by_key.get(key)
            if queued_request is None:
                queued_request = _QueuedRequest(
                    key=key,
                    method=normalized_method,
                    url=str(url),
                    kwargs=dict(kwargs),
                )
                self._queue.append(queued_request)
                self._pending_by_key[key] = queued_request
                self._condition.notify()

        queued_request.completed.wait()
        if queued_request.error is not None:
            raise queued_request.error
        return queued_request.response

    def get(self, url: str, **kwargs: Any) -> Any:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> Any:
        return self.request("POST", url, **kwargs)

    def put(self, url: str, **kwargs: Any) -> Any:
        return self.request("PUT", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> Any:
        return self.request("PATCH", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> Any:
        return self.request("DELETE", url, **kwargs)

    def _dispatch_loop(self):
        while True:
            with self._condition:
                while not self._queue:
                    self._condition.wait()

                now = time.monotonic()
                cutoff = now - self._interval_seconds
                while self._dispatch_times and self._dispatch_times[0] <= cutoff:
                    self._dispatch_times.popleft()

                queued_request = self._queue[0]
                wait_seconds = 0.0
                if len(self._dispatch_times) >= self._max_requests:
                    wait_seconds = max(
                        wait_seconds,
                        self._dispatch_times[0] + self._interval_seconds - now,
                    )

                paper_tr_id = self._paper_tr_id(
                    queued_request.url,
                    queued_request.kwargs,
                )
                last_paper_dispatch = self._last_paper_tr_dispatch.get(paper_tr_id)
                if paper_tr_id and last_paper_dispatch is not None:
                    wait_seconds = max(
                        wait_seconds,
                        last_paper_dispatch + self._paper_tr_interval_seconds - now,
                    )

                if wait_seconds > 0:
                    self._condition.wait(timeout=max(wait_seconds, 0.001))
                    continue

                queued_request = self._queue.popleft()
                self._dispatch_times.append(now)
                if paper_tr_id:
                    self._last_paper_tr_dispatch[paper_tr_id] = now

            worker = threading.Thread(
                target=self._execute,
                args=(queued_request,),
                name="HttpRequestQueueWorker",
                daemon=True,
            )
            worker.start()

    def _execute(self, queued_request: _QueuedRequest):
        try:
            queued_request.response = self._request_executor(
                queued_request.method,
                queued_request.url,
                **queued_request.kwargs,
            )
        except BaseException as exc:
            queued_request.error = exc
        finally:
            with self._condition:
                queued_request.completed.set()
                if self._pending_by_key.get(queued_request.key) is queued_request:
                    self._pending_by_key.pop(queued_request.key, None)
                self._condition.notify_all()


http_client = HttpRequestQueue(max_requests=4, interval_seconds=1.0)
