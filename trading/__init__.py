"""
매매 전략 및 실행 모듈 패키지:
스탑로스(Stop Loss & Take Profit) 등 전략 알고리즘을 관리합니다.
"""

__all__ = [
    "StopLossWatcher",
    "stop_loss_watcher",
    "GoldenCrossWatcher",
    "MovingAverageCrossDetector",
    "golden_cross_watcher",
    "DeadCrossWatcher",
    "dead_cross_watcher",
    "TrailingStopWatcher",
    "TrailingStockState",
    "trailing_stop_watcher",
]


def __getattr__(name: str):
    """전략 모듈 간 순환 import 없이 기존 공개 객체를 지연 로드합니다."""
    if name in ("StopLossWatcher", "stop_loss_watcher"):
        from .stop_loss import StopLossWatcher, stop_loss_watcher

        return {
            "StopLossWatcher": StopLossWatcher,
            "stop_loss_watcher": stop_loss_watcher,
        }[name]
    if name in (
        "GoldenCrossWatcher",
        "MovingAverageCrossDetector",
        "golden_cross_watcher",
    ):
        from .golden_cross import (
            GoldenCrossWatcher,
            MovingAverageCrossDetector,
            golden_cross_watcher,
        )

        return {
            "GoldenCrossWatcher": GoldenCrossWatcher,
            "MovingAverageCrossDetector": MovingAverageCrossDetector,
            "golden_cross_watcher": golden_cross_watcher,
        }[name]
    if name in ("DeadCrossWatcher", "dead_cross_watcher"):
        from .dead_cross import DeadCrossWatcher, dead_cross_watcher

        return {
            "DeadCrossWatcher": DeadCrossWatcher,
            "dead_cross_watcher": dead_cross_watcher,
        }[name]
    if name in (
        "TrailingStopWatcher",
        "TrailingStockState",
        "trailing_stop_watcher",
    ):
        from .trailing_stop import (
            TrailingStockState,
            TrailingStopWatcher,
            trailing_stop_watcher,
        )

        return {
            "TrailingStopWatcher": TrailingStopWatcher,
            "TrailingStockState": TrailingStockState,
            "trailing_stop_watcher": trailing_stop_watcher,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
