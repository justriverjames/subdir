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


class TieredRateLimiter:
    """
    Rate limiter with tier-based budget allocation.
    Posts tier gets majority of budget, comments tier gets the rest.
    """

    def __init__(self, config):
        self.config = config

        # Base limits (total available)
        self.base_limits = {
            60: int(config.requests_per_minute * 0.9),
            10: int(config.requests_per_10_seconds * 0.9),
            1: max(1, int(config.requests_per_second * 0.9))
        }

        # Per-tier sliding windows (posts=1, comments=2 internally)
        self.tier_windows = {
            1: {60: deque(), 10: deque(), 1: deque()},
            2: {60: deque(), 10: deque(), 1: deque()}
        }

        # Budget allocation
        self.tier_budgets = {
            1: config.posts_weight,
            2: config.comments_weight
        }

        # Stats per tier
        self.tier_stats = {
            1: {'requests': 0, 'wait_time': 0.0},
            2: {'requests': 0, 'wait_time': 0.0}
        }

        # Track if tiers are active (for dynamic reallocation)
        self.tier_active = {1: False, 2: False}
        self.last_tier_activity = {1: 0.0, 2: 0.0}

        logger.info(
            f"Tiered rate limiter: posts={self.tier_budgets[1]:.0%}, "
            f"comments={self.tier_budgets[2]:.0%}"
        )

    def _get_tier_limits(self, tier: int) -> Dict[int, int]:
        """Calculate limits for a specific tier based on budget"""
        budget = self.tier_budgets[tier]
        return {
            window: max(1, int(limit * budget))
            for window, limit in self.base_limits.items()
        }

    def update_budgets(self, posts_weight: float, comments_weight: float):
        """Dynamically update budget allocation"""
        self.tier_budgets[1] = posts_weight
        self.tier_budgets[2] = comments_weight
        logger.info(f"Budget updated: posts={posts_weight:.0%}, comments={comments_weight:.0%}")

    def reallocate_if_idle(self):
        """Reallocate budget if one tier is idle"""
        now = time.time()
        posts_idle = (now - self.last_tier_activity[1]) > 60
        comments_idle = (now - self.last_tier_activity[2]) > 60

        if posts_idle and not comments_idle:
            # Give all budget to comments
            self.tier_budgets = {1: 0.1, 2: 0.9}
        elif comments_idle and not posts_idle:
            # Give all budget to posts
            self.tier_budgets = {1: 0.9, 2: 0.1}
        else:
            # Reset to configured values
            self.tier_budgets = {
                1: self.config.posts_weight,
                2: self.config.comments_weight
            }

    async def acquire(self, tier: int):
        """Wait until a request can be made for the specified tier"""
        tier_limits = self._get_tier_limits(tier)
        windows = self.tier_windows[tier]

        while True:
            now = time.time()
            can_proceed = True
            wait_time = 0.0

            for window_size, window in windows.items():
                cutoff = now - window_size
                while window and window[0] < cutoff:
                    window.popleft()

                if len(window) >= tier_limits[window_size]:
                    can_proceed = False
                    oldest = window[0]
                    window_wait = oldest + window_size - now + 0.1
                    wait_time = max(wait_time, window_wait)

            if can_proceed:
                for window in windows.values():
                    window.append(now)

                self.tier_stats[tier]['requests'] += 1
                self.last_tier_activity[tier] = now
                self.tier_active[tier] = True

                # Jitter
                jitter = random.uniform(0.1, 0.5)
                await asyncio.sleep(jitter)
                return

            self.tier_stats[tier]['wait_time'] += wait_time
            await asyncio.sleep(wait_time)

    async def wait_with_delay(self, tier: int):
        """Acquire rate limit slot and add delay"""
        await self.acquire(tier)
        delay = random.uniform(
            self.config.min_request_delay,
            self.config.max_request_delay
        )
        await asyncio.sleep(delay)

    def get_stats(self) -> Dict:
        """Get combined stats"""
        return {
            'posts': self.tier_stats[1].copy(),
            'comments': self.tier_stats[2].copy(),
            'budgets': self.tier_budgets.copy(),
            'total_requests': sum(s['requests'] for s in self.tier_stats.values())
        }


class AntiDetection:
    """
    Anti-detection utilities for organic-looking behavior.
    Handles breaks, shuffling, and timing variations.
    """

    def __init__(self, config):
        self.config = config
        self.subs_since_break = 0
        self.next_break_at = self._pick_next_break()
        self.break_count = 0

    def _pick_next_break(self) -> int:
        """Randomly pick when the next break should happen"""
        return random.randint(
            self.config.break_after_subs_min,
            self.config.break_after_subs_max
        )

    async def maybe_take_break(self) -> bool:
        """Check if we should take a break, and take it if so"""
        self.subs_since_break += 1

        if self.subs_since_break < self.next_break_at:
            return False

        # Time for a break
        self.break_count += 1
        self.subs_since_break = 0
        self.next_break_at = self._pick_next_break()

        # Decide break type
        if random.random() < self.config.long_break_probability:
            duration = random.uniform(
                self.config.long_break_duration_min,
                self.config.long_break_duration_max
            )
            logger.info(f"Taking long break #{self.break_count}: {duration/60:.1f} minutes")
        else:
            duration = random.uniform(
                self.config.break_duration_min,
                self.config.break_duration_max
            )
            logger.info(f"Taking break #{self.break_count}: {duration:.0f} seconds")

        await asyncio.sleep(duration)
        return True

    def shuffle_with_bias(self, items: list, key: str = 'subscribers') -> list:
        """Shuffle items but keep roughly ordered by key"""
        if not self.config.shuffle_order or not items:
            return items

        # Sort by key first (descending)
        sorted_items = sorted(
            items,
            key=lambda x: x.get(key) or 0,
            reverse=True
        )

        # Random adjacent swaps
        for i in range(len(sorted_items) - 1):
            if random.random() < self.config.shuffle_swap_probability:
                sorted_items[i], sorted_items[i+1] = sorted_items[i+1], sorted_items[i]

        return sorted_items

    async def random_delay(self, min_s: float, max_s: float):
        """Random delay with gaussian noise for organic timing"""
        base = random.uniform(min_s, max_s)
        # Add gaussian noise (small variance)
        noise = random.gauss(0, base * 0.1)
        delay = max(0.5, base + noise)
        await asyncio.sleep(delay)

    def get_stats(self) -> Dict:
        return {
            'break_count': self.break_count,
            'subs_since_break': self.subs_since_break,
            'next_break_in': self.next_break_at - self.subs_since_break
        }
