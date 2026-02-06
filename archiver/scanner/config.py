import os
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)


@dataclass
class ArchiverConfig:
    """Configuration for Reddit archiver scanner"""

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

    # Two-tier processing (toggle between threads or comments, not both)
    scanner_mode: str = 'threads'  # threads, comments
    posts_weight: float = 0.8
    comments_weight: float = 0.2
    comments_batch_size: int = 5
    comments_cooldown: float = 300.0  # 5 min between comment batches

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

    @classmethod
    def from_env(cls) -> 'ArchiverConfig':
        """Load configuration from environment variables"""

        # Required credentials
        required = [
            'REDDIT_CLIENT_ID',
            'REDDIT_CLIENT_SECRET',
            'REDDIT_USERNAME',
            'REDDIT_PASSWORD'
        ]

        missing = [k for k in required if not os.getenv(k)]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        # User agent
        username = os.getenv('REDDIT_USERNAME')
        user_agent = os.getenv('USER_AGENT', f'linux:reddit-archiver:v1.0 (by /u/{username})')

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

            # Two-tier processing
            scanner_mode=os.getenv('SCANNER_MODE', 'threads'),
            posts_weight=float(os.getenv('POSTS_WEIGHT', '0.8')),
            comments_weight=float(os.getenv('COMMENTS_WEIGHT', '0.2')),
            comments_batch_size=int(os.getenv('COMMENTS_BATCH_SIZE', '5')),
            comments_cooldown=float(os.getenv('COMMENTS_COOLDOWN', '300.0')),

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

        logger.info("Configuration loaded from environment")
        logger.info(f"Scanner mode: {config.scanner_mode}")
        logger.info(f"Rate budget: posts={config.posts_weight:.0%}, comments={config.comments_weight:.0%}")
        logger.info(f"Rate limits: {config.requests_per_minute}/min, {config.requests_per_10_seconds}/10s")
        logger.info(f"Min subscribers: {config.min_subscribers}")

        return config

    def validate(self):
        """Validate configuration values"""
        errors = []

        # Check rate limits are sensible
        if self.requests_per_minute > 90:
            errors.append("requests_per_minute too high (max 90 to stay safe)")

        if self.requests_per_10_seconds > 15:
            errors.append("requests_per_10_seconds too high (max 15)")

        # Check delays
        if self.min_request_delay < 0.5:
            errors.append("min_request_delay too low (min 0.5s)")

        if self.max_request_delay < self.min_request_delay:
            errors.append("max_request_delay must be >= min_request_delay")

        # Check processing limits
        if self.max_posts_per_subreddit < 100:
            errors.append("max_posts_per_subreddit too low (min 100)")

        if self.max_posts_per_subreddit > 2000:
            errors.append("max_posts_per_subreddit too high (max 2000 for top+hot)")

        # Two-tier settings
        if self.scanner_mode not in ('threads', 'comments'):
            errors.append("scanner_mode must be 'threads' or 'comments'")

        if not (0.0 <= self.posts_weight <= 1.0):
            errors.append("posts_weight must be between 0.0 and 1.0")

        if not (0.0 <= self.comments_weight <= 1.0):
            errors.append("comments_weight must be between 0.0 and 1.0")

        if errors:
            raise ValueError(f"Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors))

        logger.info("Configuration validated successfully")
