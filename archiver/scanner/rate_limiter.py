import time
import asyncio
import random
import logging
from collections import deque
from typing import Dict

logger = logging.getLogger(__name__)


class ConservativeRateLimiter:
    """
    Conservative multi-window rate limiter for Reddit API
    More conservative than redditarr (60 QPM vs 85 QPM)
    """

    def __init__(self, config):
        self.config = config

        # Three sliding windows for burst protection
        self.windows: Dict[int, deque] = {
            60: deque(),   # 1 minute window
            10: deque(),   # 10 second window
            1: deque()     # 1 second window
        }

        # Limits per window (with safety buffer)
        self.limits = {
            60: int(config.requests_per_minute * 0.9),  # 54 requests/min
            10: int(config.requests_per_10_seconds * 0.9),  # 9 requests/10s
            1: max(1, int(config.requests_per_second * 0.9))  # 1 request/second
        }

        # Stats
        self.total_requests = 0
        self.total_wait_time = 0.0

        logger.info(
            f"Rate limiter initialized: {self.limits[60]}/min, "
            f"{self.limits[10]}/10s, {self.limits[1]}/s"
        )

    async def acquire(self):
        """
        Wait until a request can be made without violating limits.
        Checks all windows and enforces the strictest limit.
        """
        while True:
            now = time.time()
            can_proceed = True
            wait_time = 0.0

            # Check all windows
            for window_size, window in self.windows.items():
                # Remove expired timestamps
                cutoff = now - window_size
                while window and window[0] < cutoff:
                    window.popleft()

                # Check if at limit
                if len(window) >= self.limits[window_size]:
                    can_proceed = False
                    # Calculate wait time for this window
                    oldest = window[0]
                    window_wait = oldest + window_size - now + 0.1
                    wait_time = max(wait_time, window_wait)

            if can_proceed:
                # Add timestamp to all windows
                for window in self.windows.values():
                    window.append(now)

                self.total_requests += 1

                # Random jitter for human-like behavior
                jitter = random.uniform(0.1, 0.5)
                await asyncio.sleep(jitter)

                return

            # Wait before retrying
            logger.debug(f"Rate limit approaching, waiting {wait_time:.1f}s")
            self.total_wait_time += wait_time
            await asyncio.sleep(wait_time)

    async def wait_with_delay(self):
        """
        Acquire rate limit slot and add random delay.
        Combines rate limiting with human-like delays.
        """
        await self.acquire()

        # Random delay between requests
        delay = random.uniform(
            self.config.min_request_delay,
            self.config.max_request_delay
        )
        await asyncio.sleep(delay)

    def get_stats(self) -> Dict:
        """Get rate limiter statistics"""
        return {
            'total_requests': self.total_requests,
            'total_wait_time': round(self.total_wait_time, 1),
            'avg_wait_per_request': (
                round(self.total_wait_time / self.total_requests, 2)
                if self.total_requests > 0 else 0
            ),
            'current_window_counts': {
                f'{size}s': len(window)
                for size, window in self.windows.items()
            }
        }

    def reset(self):
        """Reset all windows (for testing)"""
        for window in self.windows.values():
            window.clear()
        self.total_requests = 0
        self.total_wait_time = 0.0


class ExponentialBackoff:
    """
    Exponential backoff for retry logic.
    Used when handling errors and retries.
    """

    def __init__(self, base_delay: float = 1.0, max_delay: float = 60.0, multiplier: float = 2.0):
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.attempt = 0

    async def wait(self):
        """Wait with exponential backoff and jitter"""
        if self.attempt == 0:
            delay = self.base_delay
        else:
            delay = min(
                self.base_delay * (self.multiplier ** (self.attempt - 1)),
                self.max_delay
            )

        # Add jitter (±25%)
        jitter = random.uniform(0.75, 1.25)
        actual_delay = delay * jitter

        logger.debug(f"Exponential backoff: attempt {self.attempt + 1}, waiting {actual_delay:.1f}s")
        await asyncio.sleep(actual_delay)

        self.attempt += 1

    def reset(self):
        """Reset attempt counter"""
        self.attempt = 0


class BatchPacer:
    """
    Introduces pauses between batches of subreddits.
    Breaks up systematic patterns to appear more organic.
    """

    def __init__(self, config):
        self.config = config
        self.processed_count = 0

    async def check_and_pause(self):
        """Check if batch pause is needed"""
        self.processed_count += 1

        if self.processed_count % self.config.batch_pause_interval == 0:
            pause_duration = random.uniform(
                self.config.batch_pause_min,
                self.config.batch_pause_max
            )
            logger.info(
                f"Batch pause after {self.processed_count} subreddits, "
                f"waiting {pause_duration:.0f}s"
            )
            await asyncio.sleep(pause_duration)

    def reset(self):
        """Reset counter"""
        self.processed_count = 0
