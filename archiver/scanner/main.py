import asyncio
import logging
import sys
from pathlib import Path

from config import ArchiverConfig
from database import Database
from reddit_client import RedditAPIClient
from rate_limiter import ConservativeRateLimiter, BatchPacer
from processors.metadata import MetadataProcessor
from processors.posts import PostsProcessor
from processors.comments import CommentsProcessor
from processors.media import MediaProcessor


# Setup logging
def setup_logging(level: str = 'INFO'):
    logging.basicConfig(
        level=getattr(logging, level),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


logger = logging.getLogger(__name__)


class ArchiverScanner:
    """Main scanner orchestrator - fetches everything like redditarr"""

    def __init__(self, config: ArchiverConfig):
        self.config = config
        self.db = None
        self.reddit = None
        self.rate_limiter = None
        self.batch_pacer = None

        # Processors
        self.metadata_processor = None
        self.posts_processor = None
        self.comments_processor = None
        self.media_processor = None

    async def initialize(self):
        """Initialize all components"""
        logger.info("Initializing Reddit Archiver Scanner")
        logger.info("=" * 60)
        logger.info("Comprehensive archiver - posts, comments, media URLs")
        logger.info("=" * 60)

        # Database connection
        self.db = Database(self.config)
        self.db.connect()

        if not self.db.test_connection():
            raise Exception("Database connection failed")

        logger.info("✓ Database connection established")

        # Rate limiter
        self.rate_limiter = ConservativeRateLimiter(self.config)
        self.batch_pacer = BatchPacer(self.config)

        # Reddit client
        self.reddit = RedditAPIClient(self.config, self.rate_limiter)
        await self.reddit.__aenter__()

        logger.info("✓ Reddit API authenticated")

        # Processors
        self.metadata_processor = MetadataProcessor(self.reddit, self.db)
        self.posts_processor = PostsProcessor(self.reddit, self.db, self.config)
        self.comments_processor = CommentsProcessor(self.reddit, self.db, self.config)
        self.media_processor = MediaProcessor(self.db)

        logger.info("✓ All processors initialized")
        logger.info("")

    async def shutdown(self):
        """Clean shutdown"""
        logger.info("")
        logger.info("Shutting down scanner")

        if self.reddit:
            await self.reddit.__aexit__(None, None, None)

        if self.db:
            self.db.close()

        logger.info("✓ Scanner shutdown complete")

    async def process_subreddit(self, subreddit_name: str) -> bool:
        """
        Complete archival: metadata → posts → comments → media URLs.

        Returns:
            True if successful, False otherwise
        """
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"Processing r/{subreddit_name}")
        logger.info("=" * 60)

        # Phase 1: Metadata
        logger.info(f"[1/4] Fetching metadata for r/{subreddit_name}")
        self.db.update_processing_state(subreddit_name, 'metadata')

        success = await self.metadata_processor.process_subreddit(subreddit_name)

        if not success:
            logger.warning(f"Skipping r/{subreddit_name} - metadata fetch failed")
            return False

        # Phase 2: Posts (top 1000 + hot 1000, merged/deduplicated)
        logger.info(f"[2/4] Fetching posts for r/{subreddit_name}")
        self.db.update_processing_state(subreddit_name, 'posts')

        posts_count = await self.posts_processor.process_subreddit(subreddit_name)

        if posts_count == 0:
            logger.warning(f"No posts found for r/{subreddit_name}")

        # Phase 3: Comments (materialized paths, bot filtering)
        logger.info(f"[3/4] Fetching comments for r/{subreddit_name}")
        self.db.update_processing_state(subreddit_name, 'comments')

        comments_count = await self.comments_processor.process_subreddit_posts(subreddit_name)

        # Phase 4: Media URLs (extract, don't download)
        logger.info(f"[4/4] Extracting media URLs for r/{subreddit_name}")
        self.db.update_processing_state(subreddit_name, 'media')

        media_count = self.media_processor.process_subreddit_posts(subreddit_name)

        # Mark as completed
        self.db.update_processing_state(
            subreddit_name,
            'completed',
            {
                'posts_count': posts_count,
                'comments_count': comments_count,
                'media_count': media_count
            }
        )

        logger.info("")
        logger.info(f"✓ r/{subreddit_name} COMPLETE:")
        logger.info(f"  - {posts_count:,} posts")
        logger.info(f"  - {comments_count:,} comments")
        logger.info(f"  - {media_count:,} media URLs")
        logger.info("")

        # Batch pause check
        await self.batch_pacer.check_and_pause()

        return True

    async def run_batch(self, limit: int = 50):
        """
        Process a batch of subreddits.

        Args:
            limit: Number of subreddits to process
        """
        logger.info("=" * 60)
        logger.info(f"Starting batch processing (limit: {limit})")
        logger.info("=" * 60)
        logger.info("")

        # Get subreddits to process
        subreddits = self.db.get_subreddits_for_processing(
            limit=limit,
            min_subscribers=self.config.min_subscribers
        )

        if not subreddits:
            logger.info("No subreddits to process")
            return

        logger.info(f"Found {len(subreddits)} subreddits to process")
        logger.info("")

        # Process each subreddit
        processed = 0
        failed = 0

        for i, sub in enumerate(subreddits, 1):
            try:
                logger.info(f"[{i}/{len(subreddits)}] Processing r/{sub['name']}")
                success = await self.process_subreddit(sub['name'])
                if success:
                    processed += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Error processing r/{sub['name']}: {e}", exc_info=True)
                failed += 1

        # Print summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("BATCH COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Processed: {processed} subreddits")
        logger.info(f"Failed: {failed} subreddits")
        logger.info("")

        # Stats
        stats = self.db.get_stats()
        logger.info("Database Stats:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value:,}")
        logger.info("")

        logger.info("Rate Limiter Stats:")
        rl_stats = self.rate_limiter.get_stats()
        for key, value in rl_stats.items():
            logger.info(f"  {key}: {value}")
        logger.info("")

        logger.info("Reddit API Stats:")
        api_stats = self.reddit.get_stats()
        for key, value in api_stats.items():
            logger.info(f"  {key}: {value}")

    async def add_subreddits_from_sqlite(self, sqlite_path: str, min_subscribers: int = 5000):
        """
        Import subreddits from existing subdir SQLite database.

        Args:
            sqlite_path: Path to subdir subreddit_scanner.db
            min_subscribers: Minimum subscribers threshold
        """
        import sqlite3

        logger.info(f"Importing subreddits from {sqlite_path}")

        conn = sqlite3.connect(sqlite_path)
        cursor = conn.cursor()

        # Query subreddits with min subscribers
        cursor.execute(
            """
            SELECT name, subscribers
            FROM subreddits
            WHERE status = 'active'
                AND subscribers >= ?
            ORDER BY subscribers DESC
            """,
            (min_subscribers,)
        )

        rows = cursor.fetchall()
        conn.close()

        logger.info(f"Found {len(rows)} subreddits with {min_subscribers}+ subscribers")

        # Add to PostgreSQL
        added = 0
        for name, subscribers in rows:
            # Assign priority based on subscriber count
            if subscribers >= 1_000_000:
                priority = 1  # High priority
            elif subscribers >= 100_000:
                priority = 2  # Normal
            else:
                priority = 3  # Low

            if self.db.add_subreddit(name, priority):
                added += 1

        logger.info(f"Added {added} new subreddits to queue")


async def main():
    """Main entry point"""
    # Load configuration
    try:
        config = ArchiverConfig.from_env()
        config.validate()
    except Exception as e:
        print(f"Configuration error: {e}")
        sys.exit(1)

    # Setup logging
    setup_logging(config.log_level)

    # Create scanner
    scanner = ArchiverScanner(config)

    try:
        # Initialize
        await scanner.initialize()

        # Run migrations
        migrations_dir = Path(__file__).parent.parent / 'migrations'
        schema_file = migrations_dir / '001_initial_schema.sql'

        if schema_file.exists():
            logger.info("Running database migrations")
            scanner.db.run_migration(str(schema_file))
            logger.info("✓ Migrations complete")
            logger.info("")

        # Import subreddits from subdir SQLite (if path provided)
        import os
        sqlite_path = os.getenv('SUBDIR_SQLITE_PATH')
        if sqlite_path and Path(sqlite_path).exists():
            await scanner.add_subreddits_from_sqlite(
                sqlite_path,
                min_subscribers=config.min_subscribers
            )
            logger.info("")

        # Get database stats
        stats = scanner.db.get_stats()
        logger.info("Initial Database Stats:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value:,}")
        logger.info("")

        # Run batch processing
        batch_size = int(os.getenv('BATCH_SIZE', '10'))
        await scanner.run_batch(limit=batch_size)

    except KeyboardInterrupt:
        logger.info("")
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await scanner.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
