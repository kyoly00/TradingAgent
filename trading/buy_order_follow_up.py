"""매수 주문의 미체결 잔량을 취소하거나 시장가까지 추적하는 서비스."""

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from api.order import buy_stock, cancel_order, get_orders, modify_order
from api.order_book import get_order_book
from utils.logger import log_error
from utils.settings import get_buy_order_timeout_settings

Notifier = Callable[[str], object]


@dataclass
class TrackedBuyOrder:
    """후속 처리 중인 단일 매수 주문 상태."""

    order_number: str
    stock_code: str
    interval: int
    action: str
    before_order_numbers: set[str]


class BuyOrderFollowUpManager:
    """설정된 시간이 지난 매수 미체결 주문에 후속 처리를 수행합니다."""

    def __init__(self):
        self._notifier: Notifier | None = None
        self._lock = threading.Lock()
        self._jobs: dict[str, tuple[threading.Thread, threading.Event]] = {}

    def configure(self, notifier: Notifier | None = None):
        self._notifier = notifier

    @staticmethod
    def _normalize_order_number(order_number: object) -> str:
        value = str(order_number or "").strip()
        normalized = value.lstrip("0")
        return normalized or ("0" if value else "")

    def submit_buy_order(
        self,
        stock_code: str,
        quantity: int,
        price: int | None = None,
    ) -> dict:
        """설정 활성 시 주문 직전 미체결 목록을 저장하고 매수 주문을 추적합니다."""
        seconds, action = get_buy_order_timeout_settings()
        before_order_numbers: set[str] = set()
        if seconds > 0:
            before_result = get_orders(qry_tp="3")
            if before_result.get("success"):
                before_order_numbers = {
                    self._normalize_order_number(item.get("ord_no"))
                    for item in before_result.get("orders", [])
                    if item.get("ord_no")
                }

        result = buy_stock(stock_code=stock_code, quantity=quantity, price=price)
        if seconds <= 0 or not result.get("success"):
            return result

        order_number = str(result.get("ord_no") or "").strip()
        clean_code = str(result.get("stock_code") or stock_code).strip()
        if not order_number:
            log_error(
                f"[매수 미체결 추적 등록 실패] 종목: {clean_code}, 주문번호가 없습니다."
            )
            return result

        self._track(
            TrackedBuyOrder(
                order_number=order_number,
                stock_code=clean_code,
                interval=seconds,
                action=action,
                before_order_numbers=before_order_numbers,
            )
        )
        return result

    def _track(self, order: TrackedBuyOrder):
        job_key = self._normalize_order_number(order.order_number)
        if job_key in order.before_order_numbers:
            log_error(
                f"[매수 미체결 추적 등록 중단] 주문번호({order.order_number})가 "
                "주문 전 미체결 목록에 이미 존재합니다."
            )
            return
        stop_event = threading.Event()
        thread = threading.Thread(
            target=self._run_job,
            args=(job_key, order, stop_event),
            name=f"BuyOrderFollowUp-{order.order_number}",
            daemon=True,
        )
        with self._lock:
            previous = self._jobs.pop(job_key, None)
            if previous is not None:
                previous[1].set()
            self._jobs[job_key] = (thread, stop_event)
        thread.start()

    def _run_job(
        self,
        job_key: str,
        order: TrackedBuyOrder,
        stop_event: threading.Event,
    ):
        try:
            while not stop_event.wait(order.interval):
                if not self._process_once(order):
                    return
        except Exception as exc:
            log_error(
                f"[매수 미체결 후속 처리 예외] 주문: {order.order_number}, 오류: {exc}"
            )
        finally:
            with self._lock:
                current = self._jobs.get(job_key)
                if current is not None and current[1] is stop_event:
                    self._jobs.pop(job_key, None)

    def _find_pending_order(self, order: TrackedBuyOrder) -> tuple[dict | None, str | None]:
        result = get_orders(qry_tp="3")
        if not result.get("success"):
            return None, result.get("message") or "미체결 주문 조회 실패"

        target_number = self._normalize_order_number(order.order_number)
        for item in result.get("orders", []):
            item_number = self._normalize_order_number(item.get("ord_no"))
            if item_number == target_number:
                return item, None
        return None, None

    @staticmethod
    def _exchange_of(item: dict) -> str:
        exchange = str(item.get("exchange") or "KRX").strip().upper()
        return exchange if exchange in ("KRX", "NXT", "SOR") else "KRX"

    def _process_once(self, order: TrackedBuyOrder) -> bool:
        """한 차례 후속 처리를 수행하고 반복 필요 여부를 반환합니다."""
        pending_order, query_error = self._find_pending_order(order)
        if query_error:
            log_error(
                f"[매수 미체결 조회 실패] 주문: {order.order_number}, 사유: {query_error}"
            )
            return True
        if pending_order is None:
            return False

        remaining_quantity = int(pending_order.get("remn_qty") or 0)
        if remaining_quantity <= 0:
            return False
        stock_name = str(pending_order.get("stock_name") or "종목명 없음").strip()
        exchange = self._exchange_of(pending_order)

        if order.action == "cancel":
            result = cancel_order(
                orig_ord_no=order.order_number,
                stock_code=order.stock_code,
                quantity=0,
                exchange=exchange,
            )
            if result.get("success"):
                self._notify(
                    "🚫 [매수 미체결 자동 취소]\n\n"
                    f"• 종목: {stock_name} ({order.stock_code})\n"
                    f"• 원주문번호: `{order.order_number}`\n"
                    f"• 미체결 잔량: {remaining_quantity:,}주\n"
                    f"• 대기 시간: {order.interval}초\n"
                    f"• 취소접수번호: `{result.get('ord_no') or '미발급'}`"
                )
                return False
            log_error(
                f"[매수 미체결 자동 취소 실패] 주문: {order.order_number}, "
                f"사유: {result.get('message', '알 수 없는 오류')}"
            )
            return True

        return self._raise_toward_market(
            order,
            pending_order,
            stock_name,
            remaining_quantity,
            exchange,
        )

    def _raise_toward_market(
        self,
        order: TrackedBuyOrder,
        pending_order: dict,
        stock_name: str,
        remaining_quantity: int,
        exchange: str,
    ) -> bool:
        current_price = int(pending_order.get("order_price") or 0)
        if current_price <= 0:
            # 이미 시장가 주문이면 더 올릴 단계가 없습니다.
            return False

        order_book = get_order_book(order.stock_code)
        if not order_book.get("success"):
            log_error(
                f"[매수 호가 상향 조회 실패] 주문: {order.order_number}, "
                f"사유: {order_book.get('error', '알 수 없는 오류')}"
            )
            return True

        higher_prices = sorted(
            {
                int(price)
                for price in order_book.get("buy_prices", [])
                if int(price or 0) > current_price
            }
        )
        if higher_prices:
            next_price = higher_prices[0]
            result = modify_order(
                orig_ord_no=order.order_number,
                stock_code=order.stock_code,
                quantity=0,
                price=next_price,
                exchange=exchange,
            )
            if not result.get("success"):
                log_error(
                    f"[매수 호가 자동 상향 실패] 주문: {order.order_number}, "
                    f"사유: {result.get('message', '알 수 없는 오류')}"
                )
                return True

            previous_order_number = order.order_number
            order.order_number = str(result.get("ord_no") or order.order_number).strip()
            self._notify(
                "⬆️ [매수 미체결 호가 자동 상향]\n\n"
                f"• 종목: {stock_name} ({order.stock_code})\n"
                f"• 미체결 잔량: {remaining_quantity:,}주\n"
                f"• 주문단가: {current_price:,}원 → {next_price:,}원\n"
                f"• 주문번호: `{previous_order_number}` → `{order.order_number}`"
            )
            return True

        return self._replace_with_market_order(
            order,
            stock_name,
            remaining_quantity,
            exchange,
        )

    def _replace_with_market_order(
        self,
        order: TrackedBuyOrder,
        stock_name: str,
        remaining_quantity: int,
        exchange: str,
    ) -> bool:
        cancel_result = cancel_order(
            orig_ord_no=order.order_number,
            stock_code=order.stock_code,
            quantity=0,
            exchange=exchange,
        )
        if not cancel_result.get("success"):
            log_error(
                f"[시장가 전환 전 취소 실패] 주문: {order.order_number}, "
                f"사유: {cancel_result.get('message', '알 수 없는 오류')}"
            )
            return True

        cancelled_quantity = int(cancel_result.get("cancelled_quantity") or 0)
        if cancelled_quantity <= 0:
            cancelled_quantity = remaining_quantity

        market_result = buy_stock(
            stock_code=order.stock_code,
            quantity=cancelled_quantity,
            price=None,
            exchange=exchange,
        )
        if market_result.get("success"):
            self._notify(
                "🚀 [매수 미체결 시장가 전환]\n\n"
                f"• 종목: {stock_name} ({order.stock_code})\n"
                f"• 전환 수량: {cancelled_quantity:,}주\n"
                f"• 취소한 주문: `{order.order_number}`\n"
                f"• 시장가 주문번호: `{market_result.get('ord_no') or '미발급'}`"
            )
        else:
            message = (
                "❌ [매수 미체결 시장가 전환 실패]\n\n"
                f"• 종목: {stock_name} ({order.stock_code})\n"
                f"• 취소된 수량: {cancelled_quantity:,}주\n"
                f"• 실패사유: {market_result.get('message', '알 수 없는 오류')}"
            )
            self._notify(message)
            log_error(message.replace("\n", " "))
        return False

    def _notify(self, message: str):
        if self._notifier is None:
            return
        try:
            result = self._notifier(message)
            if result is False:
                log_error("[매수 미체결 후속 처리 알림 실패]")
        except Exception as exc:
            log_error(f"[매수 미체결 후속 처리 알림 예외] {exc}")

    def cancel_all(self):
        """현재 대기 중인 모든 후속 처리 작업을 중단합니다."""
        with self._lock:
            jobs = list(self._jobs.values())
            self._jobs.clear()
        for _, stop_event in jobs:
            stop_event.set()

    def shutdown(self):
        """프로그램 종료 시 모든 후속 처리 작업을 중단하고 짧게 대기합니다."""
        with self._lock:
            jobs = list(self._jobs.values())
            self._jobs.clear()
        for _, stop_event in jobs:
            stop_event.set()
        deadline = time.monotonic() + 3
        for thread, _ in jobs:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            if thread.is_alive():
                thread.join(timeout=remaining)


buy_order_follow_up_manager = BuyOrderFollowUpManager()


def submit_buy_order(
    stock_code: str,
    quantity: int,
    price: int | None = None,
) -> dict:
    """모든 매수 경로가 사용하는 후속 처리 연동 주문 함수입니다."""
    return buy_order_follow_up_manager.submit_buy_order(
        stock_code=stock_code,
        quantity=quantity,
        price=price,
    )
