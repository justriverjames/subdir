import time
import asyncio
import random
import logging
from collections import deque
from enum import Enum
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class TaskType(Enum):
    METADATA = 'metadata'
    THREADS = 'threads'
    COMMENTS = 'comments'


class GlobalRateLimiter:
    """
    Shared rate limit pool for all workers.
    Single set of global windows ensures we never exceed Reddit's limits.
    Per-worker budget allocation prevents any one worker from starving others.
    """

    def __init__(self, config):
        self.config = config

        # Global limits (90% safety buffer)
        self.global_limits = {
            60: int(config.requests_per_minute * 0.9),   # 54/min
            10: int(config.requests_per_10_seconds * 0.9),  # 9/10s
            1: max(1, int(config.requests_per_second * 0.9))  # 1/s
        }

        # Global sliding windows (all requests, regardless of worker)
        self.global_windows: Dict[int, deque] = {
            60: deque(), 10: deque(), 1: deque()
        }

        # Per-worker sliding windows (for budget enforcement)
        self.worker_windows: Dict[TaskType, Dict[int, deque]] = {
            t: {60: deque(), 10: deque(), 1: deque()}
            for t in TaskType
        }

        # Configurable weights
        self.weights = {
            TaskType.METADATA: config.metadata_weight,
            TaskType.THREADS: config.threads_weight,
            TaskType.COMMENTS: config.comments_weight,
        }

        # Track which workers are active
        self.active_workers: set[TaskType] = set()

        # Lock for thread safety
        self._lock = asyncio.Lock()

        # Stats
        self.stats = {t: {'requests': 0, 'wait_time': 0.0} for t in TaskType}
        self.total_requests = 0
        self.total_wait_time = 0.0

        logger.info(
            f"GlobalRateLimiter: {self.global_limits[60]}/min, "
            f"{self.global_limits[10]}/10s, {self.global_limits[1]}/s"
        )
        logger.info(
            f"Budget weights: metadata={self.weights[TaskType.METADATA]:.0%}, "
            f"threads={self.weights[TaskType.THREADS]:.0%}, "
            f"comments={self.weights[TaskType.COMMENTS]:.0%}"
        )

    def register_worker(self, task_type: TaskType):
        """Mark a worker as active (affects budget redistribution)"""
        self.active_workers.add(task_type)
        logger.info(f"Worker registered: {task_type.value} (active: {[w.value for w in self.active_workers]})")

    def unregister_worker(self, task_type: TaskType):
        """Mark a worker as inactive"""
        self.active_workers.discard(task_type)
        logger.info(f"Worker unregistered: {task_type.value} (active: {[w.value for w in self.active_workers]})")

    def _effective_weight(self, task_type: TaskType) -> float:
        """
        Get effective weight for a worker, redistributing budget from inactive workers.
        If threads=0.6 and comments=0.2 but comments is off:
          threads gets 0.6/(0.6+0.2) = 0.75
        """
        if task_type not in self.active_workers:
            return 0.0

        active_total = sum(
            self.weights[t] for t in self.active_workers
        )
        if active_total == 0:
            return 0.0

        return self.weights[task_type] / active_total

    def _worker_limits(self, task_type: TaskType) -> Dict[int, int]:
        """Calculate per-worker limits based on effective weight"""
        weight = self._effective_weight(task_type)
        return {
            window: max(1, int(limit * weight))
            for window, limit in self.global_limits.items()
        }

    def _cleanup(self, windows: Dict[int, deque], now: float):
        """Remove expired timestamps from sliding windows"""
        for window_size, window in windows.items():
            cutoff = now - window_size
            while window and window[0] < cutoff:
                window.popleft()

    def _check_available(self, windows: Dict[int, deque], limits: Dict[int, int], now: float) -> float:
        """
        Check if request is allowed under given windows/limits.
        Returns 0 if allowed, otherwise seconds to wait.
        """
        self._cleanup(windows, now)
        wait = 0.0
        for window_size in windows:
            if len(windows[window_size]) >= limits[window_size]:
                oldest = windows[window_size][0]
                w = oldest + window_size - now + 0.05
                wait = max(wait, w)
        return wait

    async def acquire(self, task_type: TaskType):
        """
        Block until a request slot is available for the given worker type.
        Checks both global limits and per-worker budget.
        """
        worker_limits = self._worker_limits(task_type)

        while True:
            now = time.time()

            # Check global limits first
            global_wait = self._check_available(self.global_windows, self.global_limits, now)

            # Check per-worker budget
            worker_wait = self._check_available(
                self.worker_windows[task_type], worker_limits, now
            )

            wait = max(global_wait, worker_wait)

            if wait <= 0:
                # Record in both global and worker windows
                for windows in [self.global_windows, self.worker_windows[task_type]]:
                    for w in windows.values():
                        w.append(now)

                self.total_requests += 1
                self.stats[task_type]['requests'] += 1

                # Jitter for organic timing
                jitter = random.uniform(0.1, 0.5)
                await asyncio.sleep(jitter)
                return

            self.total_wait_time += wait
            self.stats[task_type]['wait_time'] += wait
            logger.debug(f"[{task_type.value}] Budget wait: {wait:.1f}s")
            await asyncio.sleep(wait)

    async def wait_with_delay(self, task_type: TaskType):
        """Acquire slot + human-like delay"""
        await self.acquire(task_type)
        delay = random.uniform(
            self.config.min_request_delay,
            self.config.max_request_delay
        )
        await asyncio.sleep(delay)

    def update_weights(self, metadata: float, threads: float, comments: float):
        """Update budget weights at runtime"""
        self.weights[TaskType.METADATA] = metadata
        self.weights[TaskType.THREADS] = threads
        self.weights[TaskType.COMMENTS] = comments
        logger.info(f"Weights updated: metadata={metadata:.0%}, threads={threads:.0%}, comments={comments:.0%}")

    def get_stats(self) -> Dict:
        now = time.time()
        self._cleanup(self.global_windows, now)
        return {
            'total_requests': self.total_requests,
            'total_wait_time': round(self.total_wait_time, 1),
            'active_workers': [w.value for w in self.active_workers],
            'global_usage': {
                f'{size}s': len(window)
                for size, window in self.global_windows.items()
            },
            'global_limits': {
                f'{size}s': limit
                for size, limit in self.global_limits.items()
            },
            'per_worker': {
                t.value: {
                    'requests': self.stats[t]['requests'],
                    'wait_time': round(self.stats[t]['wait_time'], 1),
                    'effective_weight': round(self._effective_weight(t), 2),
                    'limits': {
                        f'{s}s': l for s, l in self._worker_limits(t).items()
                    }
                }
                for t in TaskType
            }
        }

    def get_budget_status(self) -> Dict:
        """Simplified status for WebUI"""
        now = time.time()
        self._cleanup(self.global_windows, now)
        usage_60 = len(self.global_windows[60])
        limit_60 = self.global_limits[60]
        return {
            'usage_percent': round((usage_60 / limit_60) * 100, 1) if limit_60 else 0,
            'requests_last_minute': usage_60,
            'limit_per_minute': limit_60,
            'active_workers': [w.value for w in self.active_workers],
            'weights': {t.value: round(self._effective_weight(t), 2) for t in TaskType},
        }
