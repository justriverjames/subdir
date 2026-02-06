import os
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ArchiverConfig:
    """Configuration for Reddit archiver"""

    # Reddit API credentials
    reddit_client_id: str
    reddit_client_secret: str
    reddit_username: str
    reddit_password: str
    user_agent: str

    # PostgreSQL connection
    postgres_host: str = 'localhost'
    postgres_port: int = 5432
    postgres_db: str = 'reddit_archiver'
    postgres_user: str = 'archiver'
    postgres_password: str = ''

    # Processing configuration
    min_subscribers: int = 5000
    max_posts_per_subreddit: int = 2000
    max_comments_per_post: int = 500
    max_comment_depth: int = 5
    filter_bots: bool = True

    # Rate limiting (conservative)
    requests_per_minute: int = 60
    requests_per_10_seconds: int = 10
    requests_per_second: int = 2

    # Delays (human-like behavior)
    min_request_delay: float = 1.5
    max_request_delay: float = 3.0
    subreddit_cooldown: float = 2.0

    # Subreddit processing pauses (safety)
    subreddit_pause_min: float = 30.0
    subreddit_pause_max: float = 60.0

    # Batch processing
    batch_pause_interval: int = 50
    batch_pause_min: float = 45.0
    batch_pause_max: float = 90.0

    # Safety limits
    max_consecutive_403: int = 5
    max_total_429: int = 2

    # Worker enable flags
    metadata_enabled: bool = True
    threads_enabled: bool = True
    comments_enabled: bool = False

    # Budget weights (configurable, redistributed when workers are disabled)
    metadata_weight: float = 0.2
    threads_weight: float = 0.6
    comments_weight: float = 0.2

    # Comments batch config
    comments_batch_size: int = 5
    comments_cooldown: float = 300.0  # 5 min between comment batches

    # Metadata worker config
    csv_path: str = ''
    scanner_db_path: str = ''
    stale_threshold_days: int = 30

    # Anti-detection
    break_after_subs_min: int = 10
    break_after_subs_max: int = 25
    break_duration_min: float = 60.0
    break_duration_max: float = 300.0
    long_break_probability: float = 0.05
    long_break_duration_min: float = 900.0
    long_break_duration_max: float = 3600.0
    shuffle_order: bool = True
    shuffle_swap_probability: float = 0.3

    # Logging
    log_level: str = 'INFO'

    # Legacy (kept for backward compat, ignored by orchestrator)
    scanner_mode: str = 'threads'
    posts_weight: float = 0.8

    @classmethod
    def from_env(cls) -> 'ArchiverConfig':
        """Load configuration from environment variables"""

        required = [
            'REDDIT_CLIENT_ID',
            'REDDIT_CLIENT_SECRET',
            'REDDIT_USERNAME',
            'REDDIT_PASSWORD'
        ]

        missing = [k for k in required if not os.getenv(k)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        username = os.getenv('REDDIT_USERNAME')
        user_agent = os.getenv('USER_AGENT', f'linux:subdir-archiver:v1.0 (by /u/{username})')

        config = cls(
            # Reddit API
            reddit_client_id=os.getenv('REDDIT_CLIENT_ID'),
            reddit_client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
            reddit_username=os.getenv('REDDIT_USERNAME'),
            reddit_password=os.getenv('REDDIT_PASSWORD'),
            user_agent=user_agent,

            # PostgreSQL
            postgres_host=os.getenv('POSTGRES_HOST', 'localhost'),
            postgres_port=int(os.getenv('POSTGRES_PORT', '5432')),
            postgres_db=os.getenv('POSTGRES_DB', 'reddit_archiver'),
            postgres_user=os.getenv('POSTGRES_USER', 'archiver'),
            postgres_password=os.getenv('POSTGRES_PASSWORD', ''),

            # Processing
            min_subscribers=int(os.getenv('MIN_SUBSCRIBERS', '5000')),
            max_posts_per_subreddit=int(os.getenv('MAX_POSTS_PER_SUBREDDIT', '2000')),
            max_comments_per_post=int(os.getenv('MAX_COMMENTS_PER_POST', '500')),
            max_comment_depth=int(os.getenv('MAX_COMMENT_DEPTH', '5')),
            filter_bots=os.getenv('FILTER_BOTS', 'true').lower() == 'true',

            # Rate limiting
            requests_per_minute=int(os.getenv('REQUESTS_PER_MINUTE', '60')),
            requests_per_10_seconds=int(os.getenv('REQUESTS_PER_10_SECONDS', '10')),
            requests_per_second=int(os.getenv('REQUESTS_PER_SECOND', '2')),

            # Subreddit pauses
            subreddit_pause_min=float(os.getenv('SUBREDDIT_PAUSE_MIN', '30.0')),
            subreddit_pause_max=float(os.getenv('SUBREDDIT_PAUSE_MAX', '60.0')),

            # Worker toggles
            metadata_enabled=os.getenv('METADATA_ENABLED', 'true').lower() == 'true',
            threads_enabled=os.getenv('THREADS_ENABLED', 'true').lower() == 'true',
            comments_enabled=os.getenv('COMMENTS_ENABLED', 'false').lower() == 'true',

            # Budget weights
            metadata_weight=float(os.getenv('METADATA_WEIGHT', '0.2')),
            threads_weight=float(os.getenv('THREADS_WEIGHT', '0.6')),
            comments_weight=float(os.getenv('COMMENTS_WEIGHT', '0.2')),

            # Comments
            comments_batch_size=int(os.getenv('COMMENTS_BATCH_SIZE', '5')),
            comments_cooldown=float(os.getenv('COMMENTS_COOLDOWN', '300.0')),

            # Metadata worker
            csv_path=os.getenv('CSV_PATH', ''),
            scanner_db_path=os.getenv('SCANNER_DB_PATH', ''),
            stale_threshold_days=int(os.getenv('STALE_THRESHOLD_DAYS', '30')),

            # Anti-detection
            break_after_subs_min=int(os.getenv('BREAK_AFTER_SUBS_MIN', '10')),
            break_after_subs_max=int(os.getenv('BREAK_AFTER_SUBS_MAX', '25')),
            break_duration_min=float(os.getenv('BREAK_DURATION_MIN', '60.0')),
            break_duration_max=float(os.getenv('BREAK_DURATION_MAX', '300.0')),
            long_break_probability=float(os.getenv('LONG_BREAK_PROBABILITY', '0.05')),
            shuffle_order=os.getenv('SHUFFLE_ORDER', 'true').lower() == 'true',

            # Logging
            log_level=os.getenv('LOG_LEVEL', 'INFO')
        )

        active = []
        if config.metadata_enabled:
            active.append('metadata')
        if config.threads_enabled:
            active.append('threads')
        if config.comments_enabled:
            active.append('comments')

        logger.info("Configuration loaded")
        logger.info(f"Workers: {', '.join(active)}")
        logger.info(f"Weights: metadata={config.metadata_weight:.0%}, threads={config.threads_weight:.0%}, comments={config.comments_weight:.0%}")
        logger.info(f"Rate limits: {config.requests_per_minute}/min, {config.requests_per_10_seconds}/10s")
        logger.info(f"Min subscribers: {config.min_subscribers}")

        return config

    def validate(self):
        """Validate configuration values"""
        errors = []

        if self.requests_per_minute > 90:
            errors.append("requests_per_minute too high (max 90)")

        if self.requests_per_10_seconds > 15:
            errors.append("requests_per_10_seconds too high (max 15)")

        if self.min_request_delay < 0.5:
            errors.append("min_request_delay too low (min 0.5s)")

        if self.max_request_delay < self.min_request_delay:
            errors.append("max_request_delay must be >= min_request_delay")

        if self.max_posts_per_subreddit < 100:
            errors.append("max_posts_per_subreddit too low (min 100)")

        if self.max_posts_per_subreddit > 2000:
            errors.append("max_posts_per_subreddit too high (max 2000)")

        # Weight validation
        for name, w in [('metadata', self.metadata_weight),
                        ('threads', self.threads_weight),
                        ('comments', self.comments_weight)]:
            if not (0.0 <= w <= 1.0):
                errors.append(f"{name}_weight must be between 0.0 and 1.0")

        if errors:
            raise ValueError("Config validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

        logger.info("Configuration validated")
