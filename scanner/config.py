"""
Configuration management for subreddit scanner.

Handles loading configuration from environment variables and CLI arguments.
"""

import os
import logging
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv


@dataclass
class Config:
    """Configuration for subreddit scanner."""

    # Reddit API credentials
    reddit_client_id: str
    reddit_client_secret: str
    reddit_username: str
    reddit_password: str

    # User agent for Reddit API (follows Reddit's required format)
    # Format: platform:app_id:version (description; url by /u/username)
    user_agent: str = "python:com.github.subdir:v1.0.0 (Subreddit Discovery Tool; https://github.com/justriverjames/subdir by /u/YOUR_USERNAME)"

    # Database configuration
    db_path: str = "subreddit_scanner.db"

    # Logging configuration
    log_dir: str = "logs"
    log_level: str = "INFO"

    # Rate limiting configuration (balanced for 2025 Reddit API)
    # Official limit: 100 QPM, but enforced closer to 60 QPM
    rate_limit_per_minute: int = 60  # Balanced rate (between old 85 and ultra-conservative 50)
    rate_limit_per_10s: int = 12  # Burst protection
    rate_limit_per_1s: int = 2  # Spike protection

    # Processing configuration (adds human-like delays)
    min_request_delay: float = 1.5  # Minimum delay between requests (seconds)
    max_request_delay: float = 3.0  # Maximum delay between requests (seconds)
    subreddit_cooldown: int = 2  # Base cooldown
    max_retries: int = 3

    # Anti-detection features
    shuffle_order: bool = True  # Randomize subreddit processing order
    request_diversity: bool = True  # Mix in non-metadata requests
    batch_pause_interval: int = 100  # Pause every N subreddits (less frequent)
    batch_pause_min: float = 20.0  # Minimum pause duration (seconds)
    batch_pause_max: float = 40.0  # Maximum pause duration (seconds)

    # Auto-terminate thresholds (stop before getting banned)
    max_consecutive_403: int = 10  # Stop after N consecutive 403s
    max_total_429: int = 3  # Stop after N total 429s (rate limit hits)

    # Resume configuration
    resume: bool = False
    force_refresh: bool = False

    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> 'Config':
        """
        Create configuration from environment variables.

        Args:
            env_file: Optional path to .env file

        Returns:
            Config instance

        Raises:
            ValueError: If required credentials are missing
        """
        # Load environment variables from .env file
        if env_file:
            env_path = Path(env_file)
            if env_path.exists():
                load_dotenv(env_path)
                logging.info(f"Loaded environment from {env_file}")
        else:
            # Try to load from default .env location (project root)
            project_root = Path(__file__).parent
            default_env = project_root / ".env"
            if default_env.exists():
                load_dotenv(default_env)
                logging.info(f"Loaded environment from {default_env}")

        # Get required credentials
        client_id = os.getenv('REDDIT_CLIENT_ID')
        client_secret = os.getenv('REDDIT_CLIENT_SECRET')
        username = os.getenv('REDDIT_USERNAME')
        password = os.getenv('REDDIT_PASSWORD')

        # Validate credentials
        if not all([client_id, client_secret, username, password]):
            missing = []
            if not client_id:
                missing.append('REDDIT_CLIENT_ID')
            if not client_secret:
                missing.append('REDDIT_CLIENT_SECRET')
            if not username:
                missing.append('REDDIT_USERNAME')
            if not password:
                missing.append('REDDIT_PASSWORD')

            raise ValueError(
                f"Missing required Reddit API credentials: {', '.join(missing)}\n"
                f"Please set these environment variables or create a .env file."
            )

        return cls(
            reddit_client_id=client_id,
            reddit_client_secret=client_secret,
            reddit_username=username,
            reddit_password=password,
            user_agent=os.getenv('USER_AGENT', f"python:com.github.subdir:v1.0.0 (Subreddit Discovery Tool; https://github.com/justriverjames/subdir by /u/{username})"),
            db_path=os.getenv('SCANNER_DB_PATH', 'subreddit_scanner.db'),
            log_dir=os.getenv('SCANNER_LOG_DIR', 'logs'),
            log_level=os.getenv('LOG_LEVEL', 'INFO'),
        )

    def update_from_args(self, **kwargs):
        """
        Update configuration from CLI arguments.

        Args:
            **kwargs: Keyword arguments to update
        """
        for key, value in kwargs.items():
            if value is not None and hasattr(self, key):
                setattr(self, key, value)
                logging.debug(f"Config updated: {key} = {value}")

    def validate(self):
        """
        Validate configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        # Validate rate limits
        if self.rate_limit_per_minute < 1:
            raise ValueError("rate_limit_per_minute must be >= 1")

        if self.rate_limit_per_10s > self.rate_limit_per_minute:
            raise ValueError("rate_limit_per_10s cannot exceed rate_limit_per_minute")

        if self.rate_limit_per_1s > self.rate_limit_per_10s:
            raise ValueError("rate_limit_per_1s cannot exceed rate_limit_per_10s")

        # Validate paths
        db_path = Path(self.db_path)
        if db_path.exists() and not db_path.is_file():
            raise ValueError(f"Database path exists but is not a file: {self.db_path}")

        log_dir = Path(self.log_dir)
        if log_dir.exists() and not log_dir.is_dir():
            raise ValueError(f"Log directory path exists but is not a directory: {self.log_dir}")

        # Validate processing config
        if self.subreddit_cooldown < 0:
            raise ValueError("subreddit_cooldown must be >= 0")

        if self.max_retries < 0:
            raise ValueError("max_retries must be >= 0")

    def __str__(self) -> str:
        """String representation (without exposing credentials)."""
        return (
            f"Config(\n"
            f"  user_agent={self.user_agent}\n"
            f"  db_path={self.db_path}\n"
            f"  log_dir={self.log_dir}\n"
            f"  log_level={self.log_level}\n"
            f"  rate_limit={self.rate_limit_per_minute}/min\n"
            f"  subreddit_cooldown={self.subreddit_cooldown}s\n"
            f"  max_retries={self.max_retries}\n"
            f")"
        )
