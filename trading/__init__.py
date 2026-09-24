"""
매매 전략 및 실행 모듈 패키지:
스탑로스(Stop Loss & Take Profit) 등 전략 알고리즘을 관리합니다.
"""

from .stop_loss import StopLossWatcher, stop_loss_watcher

__all__ = [
    "StopLossWatcher",
    "stop_loss_watcher",
]
