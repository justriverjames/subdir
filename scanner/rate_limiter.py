"""
Rate limiter implementation using sliding window algorithm.

Ensures compliance with Reddit API rate limits:
- 60 requests per minute (conservative, Reddit allows ~90)
- 15 requests per 10 seconds (burst protection)
- Exponential backoff on errors
"""

import time
import asyncio
import logging
from collections import deque
from typing import Optional


class SlidingWindowRateLimiter:
    """
    Sliding window rate limiter for Reddit API requests.

    Implements multi-window rate limiting:
    - 60 requests per 60 seconds (main limit)
    - 15 requests per 10 seconds (burst protection)
    - 3 requests per 1 second (spike protection)
    """

    def __init__(
        self,
        requests_per_minute: int = 60,
        requests_per_10s: int = 15,
        requests_per_1s: int = 3
    ):
        """
        Initialize rate limiter.

        Args:
            requests_per_minute: Maximum requests per 60 seconds
            requests_per_10s: Maximum requests per 10 seconds
            requests_per_1s: Maximum requests per 1 second
        """
        self.requests_per_minute = requests_per_minute
        self.requests_per_10s = requests_per_10s
        self.requests_per_1s = requests_per_1s

        # Sliding windows for different time periods
        self.window_60s = deque()  # 60-second window
        self.window_10s = deque()  # 10-second window
        self.window_1s = deque()   # 1-second window

        # Lock for thread safety
        self.lock = asyncio.Lock()

        # Statistics
        self.total_requests = 0
        self.total_wait_time = 0
        self.requests_blocked = 0

        logging.debug(
            f"Rate limiter initialized: {requests_per_minute}/min, "
            f"{requests_per_10s}/10s, {requests_per_1s}/s"
        )

    def _cleanup_window(self, window: deque, max_age: float):
        """
        Remove old timestamps from window.

        Args:
            window: Deque containing timestamps
            max_age: Maximum age of timestamps to keep (in seconds)
        """
        now = time.time()
        cutoff = now - max_age

        while window and window[0] < cutoff:
            window.popleft()

    def _get_wait_time(self) -> float:
        """
        Calculate how long to wait before next request is allowed.

        Returns:
            Wait time in seconds (0 if request can proceed immediately)
        """
        now = time.time()

        # Clean up old timestamps
        self._cleanup_window(self.window_60s, 60)
        self._cleanup_window(self.window_10s, 10)
        self._cleanup_window(self.window_1s, 1)

        wait_times = []

        # Check 60-second window
        if len(self.window_60s) >= self.requests_per_minute:
            oldest = self.window_60s[0]
            wait_times.append((oldest + 60) - now)

        # Check 10-second window
        if len(self.window_10s) >= self.requests_per_10s:
            oldest = self.window_10s[0]
            wait_times.append((oldest + 10) - now)

        # Check 1-second window
        if len(self.window_1s) >= self.requests_per_1s:
            oldest = self.window_1s[0]
            wait_times.append((oldest + 1) - now)

        return max(wait_times) if wait_times else 0

    async def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire permission to make a request.

        This method will block until a request slot is available or timeout is reached.

        Args:
            timeout: Maximum time to wait in seconds (None = wait indefinitely)

        Returns:
            True if acquired, False if timeout

        Raises:
            asyncio.TimeoutError: If timeout is exceeded
        """
        start_time = time.time()

        async with self.lock:
            while True:
                wait_time = self._get_wait_time()

                if wait_time <= 0:
                    # Slot available, record timestamp
                    now = time.time()
                    self.window_60s.append(now)
                    self.window_10s.append(now)
                    self.window_1s.append(now)

                    self.total_requests += 1
                    self.total_wait_time += (now - start_time)

                    return True

                # Check timeout
                if timeout is not None:
                    elapsed = time.time() - start_time
                    if elapsed + wait_time > timeout:
                        self.requests_blocked += 1
                        return False

                # Wait before retrying
                self.requests_blocked += 1
                logging.debug(f"Rate limit: waiting {wait_time:.2f}s")
                await asyncio.sleep(wait_time)

    async def wait_if_needed(self):
        """
        Wait if rate limit would be exceeded.

        Convenience method that always waits (no timeout).
        """
        await self.acquire()

    def get_stats(self) -> dict:
        """
        Get rate limiter statistics.

        Returns:
            Dictionary with statistics
        """
        avg_wait = (
            self.total_wait_time / self.total_requests
            if self.total_requests > 0
            else 0
        )

        return {
            'total_requests': self.total_requests,
            'requests_blocked': self.requests_blocked,
            'avg_wait_time': avg_wait,
            'current_60s_count': len(self.window_60s),
            'current_10s_count': len(self.window_10s),
            'current_1s_count': len(self.window_1s),
        }

    def reset(self):
        """Reset rate limiter state (for testing)."""
        self.window_60s.clear()
        self.window_10s.clear()
        self.window_1s.clear()
        self.total_requests = 0
        self.total_wait_time = 0
        self.requests_blocked = 0


class ExponentialBackoff:
    """
    Exponential backoff for retry logic.

    Implements exponential backoff with jitter for failed requests.
    """

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        multiplier: float = 2.0,
        jitter: bool = True
    ):
        """
        Initialize exponential backoff.

        Args:
            base_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            multiplier: Multiplier for each retry
            jitter: Whether to add random jitter
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.multiplier = multiplier
        self.jitter = jitter
        self.current_attempt = 0

    def get_delay(self) -> float:
        """
        Get delay for current attempt.

        Returns:
            Delay in seconds
        """
        delay = min(
            self.base_delay * (self.multiplier ** self.current_attempt),
            self.max_delay
        )

        if self.jitter:
            # Add random jitter (±25%)
            import random
            jitter_factor = random.uniform(0.75, 1.25)
            delay *= jitter_factor

        return delay

    async def wait(self):
        """Wait for the current backoff delay."""
        delay = self.get_delay()
        logging.debug(f"Exponential backoff: waiting {delay:.2f}s (attempt {self.current_attempt})")
        await asyncio.sleep(delay)
        self.current_attempt += 1

    def reset(self):
        """Reset backoff to initial state."""
        self.current_attempt = 0
