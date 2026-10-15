"""키움 WebSocket 주식체결(0B) 구독 클라이언트."""

import json
import threading
import time
from collections.abc import Callable
from datetime import datetime

try:
    import websocket
except ImportError:  # pragma: no cover - 실행 환경 의존 오류 안내용
    websocket = None

from api.auth import session_manager
from config.config import paper_socket_url, real_socket_url
from utils.logger import log_error, log_info

TickCallback = Callable[[str, datetime, int], None]
MessageCallback = Callable[[dict], None]
OutboundProvider = Callable[[], list[dict]]


class KiwoomRealtimeClient:
    """0B 체결 데이터를 구독하고 정규화된 틱을 콜백으로 전달합니다."""

    def __init__(self, group_number: str = "1"):
        self._group_number = group_number
        self._socket = None
        self._socket_lock = threading.Lock()

    def _get_websocket_url(self) -> str:
        base_url = paper_socket_url if session_manager.mode == "paper" else real_socket_url
        if base_url.rstrip("/").endswith("/api/websocket"):
            return base_url.rstrip("/")
        return f"{base_url.rstrip('/')}/api/websocket"

    def close(self):
        """현재 WebSocket을 닫아 대기 중인 수신을 즉시 해제합니다."""
        with self._socket_lock:
            current_socket = self._socket
        if current_socket is not None:
            try:
                current_socket.close()
            except Exception:
                pass

    def _send_json(self, payload: dict):
        with self._socket_lock:
            current_socket = self._socket
        if current_socket is None:
            raise RuntimeError("WebSocket이 연결되어 있지 않습니다.")
        current_socket.send(json.dumps(payload, ensure_ascii=False))

    def _receive_login(self, stop_event: threading.Event):
        """LOGIN 응답을 기다리고 실패 시 예외를 발생시킵니다."""
        deadline = time.monotonic() + 10
        while not stop_event.is_set():
            if time.monotonic() >= deadline:
                raise TimeoutError("WebSocket 로그인 응답 시간이 초과되었습니다.")
            try:
                raw_message = self._socket.recv()
            except websocket.WebSocketTimeoutException:
                continue
            if not raw_message:
                raise ConnectionError("WebSocket 연결이 종료되었습니다.")
            message = json.loads(raw_message)
            if message.get("trnm") == "PING":
                self._send_json(message)
                continue
            if message.get("trnm") == "LOGIN":
                if str(message.get("return_code")) != "0":
                    raise RuntimeError(message.get("return_msg") or "WebSocket 로그인 실패")
                return
        raise RuntimeError("WebSocket 로그인이 중단되었습니다.")

    def _subscribe(self, stock_codes: list[str]):
        self._send_json(
            {
                "trnm": "REG",
                "grp_no": self._group_number,
                "refresh": "0",
                "data": [{"item": stock_codes, "type": ["0B"]}],
            }
        )

    def _unsubscribe(self, stock_codes: list[str]):
        try:
            self._send_json(
                {
                    "trnm": "REMOVE",
                    "grp_no": self._group_number,
                    "refresh": "0",
                    "data": [{"item": stock_codes, "type": ["0B"]}],
                }
            )
        except Exception:
            pass

    @staticmethod
    def _parse_tick(item: dict) -> tuple[str, datetime, int] | None:
        if item.get("type") != "0B":
            return None
        values = item.get("values") or {}
        market_type = str(values.get("290") or "").strip()
        if market_type and market_type != "2":
            return None

        stock_code = str(item.get("item") or "").strip()
        trade_time = str(values.get("20") or "").strip()
        raw_price = str(values.get("10") or "").strip().replace(",", "")
        if not stock_code or len(trade_time) != 6 or not raw_price:
            return None
        try:
            price = abs(int(raw_price))
            timestamp = datetime.strptime(
                datetime.now().strftime("%Y%m%d") + trade_time,
                "%Y%m%d%H%M%S",
            )
        except (TypeError, ValueError):
            return None
        if price <= 0:
            return None
        return stock_code, timestamp, price

    def run(
        self,
        stock_codes: list[str],
        on_tick: TickCallback,
        stop_event: threading.Event,
        should_continue: Callable[[], bool],
        on_connected: Callable[[], None] | None = None,
        outbound_provider: OutboundProvider | None = None,
        on_message: MessageCallback | None = None,
    ):
        """로그인 후 실시간 구독과 공용 TR 요청·응답을 한 연결에서 처리합니다."""
        if websocket is None:
            raise RuntimeError("websocket-client 패키지가 설치되어 있지 않습니다.")
        if not stock_codes and outbound_provider is None:
            raise ValueError("구독 종목 또는 WebSocket 요청 공급자가 필요합니다.")
        if not session_manager.is_authenticated() or not session_manager.token:
            raise RuntimeError("로그인 토큰이 없거나 만료되었습니다.")

        current_socket = websocket.create_connection(self._get_websocket_url(), timeout=5)
        current_socket.settimeout(1)
        with self._socket_lock:
            self._socket = current_socket

        try:
            self._send_json({"trnm": "LOGIN", "token": session_manager.token})
            self._receive_login(stop_event)
            if stock_codes:
                self._subscribe(stock_codes)
            if on_connected is not None:
                on_connected()
            if stock_codes:
                log_info(f"[0B WebSocket 구독 시작] 종목 수: {len(stock_codes)}개")

            while not stop_event.is_set() and should_continue():
                if outbound_provider is not None:
                    for payload in outbound_provider():
                        self._send_json(payload)
                try:
                    raw_message = current_socket.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not raw_message:
                    raise ConnectionError("WebSocket 연결이 종료되었습니다.")

                message = json.loads(raw_message)
                if message.get("trnm") == "PING":
                    self._send_json(message)
                    continue
                if on_message is not None:
                    on_message(message)
                if message.get("trnm") != "REAL":
                    continue

                for item in message.get("data") or []:
                    tick = self._parse_tick(item)
                    if tick is not None:
                        on_tick(*tick)
        except Exception as exc:
            if not stop_event.is_set() and should_continue():
                log_error(f"[0B WebSocket 수신 오류] {exc}")
                raise
        finally:
            if stock_codes:
                self._unsubscribe(stock_codes)
            self.close()
            with self._socket_lock:
                self._socket = None
            if stock_codes:
                log_info("[0B WebSocket 구독 종료]")
