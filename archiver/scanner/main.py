import asyncio
import logging
import sys
import random
import time
import argparse
import sqlite3
from pathlib import Path

from config import ArchiverConfig
from database import Database
from reddit_client import RedditAPIClient
from rate_limiter import ConservativeRateLimiter, AntiDetection
from processors.metadata import MetadataProcessor
from processors.posts import PostsProcessor
from processors.comments import CommentsProcessor


def setup_logging(level: str = 'INFO'):
    logging.basicConfig(
        level=getattr(logging, level),
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )


logger = logging.getLogger(__name__)


class TieredScanner:
    """
    Two-tier archiver scanner.
    Posts: Metadata + Posts + Media (fast, high priority)
    Comments: Comments (slow, background)
    """

    def __init__(self, config: ArchiverConfig):
        self.config = config
        self.db = None
        self.reddit = None
        self.rate_limiter = None
        self.anti_detection = None

        self.metadata_processor = None
        self.posts_processor = None
        self.comments_processor = None

        self.last_comments_run = 0.0

    async def initialize(self):
        logger.info("Initializing Two-Tier Reddit Archiver Scanner")
        logger.info("=" * 60)

        self.db = Database(self.config)
        self.db.connect()

        if not self.db.test_connection():
            raise Exception("Database connection failed")

        logger.info("✓ Database connected")

        self.rate_limiter = ConservativeRateLimiter(self.config)
        self.anti_detection = AntiDetection(self.config)

        self.reddit = RedditAPIClient(self.config, self.rate_limiter)
        await self.reddit.__aenter__()

        logger.info("✓ Reddit API authenticated")

        self.metadata_processor = MetadataProcessor(self.reddit, self.db)
        self.posts_processor = PostsProcessor(self.reddit, self.db, self.config)
        self.comments_processor = CommentsProcessor(self.reddit, self.db, self.config)

        logger.info(f"✓ Mode: {self.config.scanner_mode}")
        logger.info("✓ Ready")
        logger.info("")

    async def shutdown(self):
        logger.info("")
        logger.info("Shutting down")

        if self.reddit:
            await self.reddit.__aexit__(None, None, None)

        if self.db:
            self.db.close()

        stats = self.rate_limiter.get_stats()
        logger.info(f"Total requests: {stats['total_requests']}")
        logger.info(f"Total wait time: {stats['total_wait_time']:.1f}s")

        anti_stats = self.anti_detection.get_stats()
        logger.info(f"Breaks taken: {anti_stats['break_count']}")

        logger.info("✓ Done")

    async def process_posts(self, subreddit_name: str) -> bool:
        """
        Posts: Metadata → Posts + Media
        """
        logger.info("")
        logger.info("=" * 60)
        logger.info(f"[POSTS] r/{subreddit_name}")
        logger.info("=" * 60)

        self.db.update_processing_tier_status(subreddit_name, 'posts', 'processing')

        # Phase 1: Metadata
        logger.info(f"[1/2] Fetching metadata")
        self.db.update_processing_state(subreddit_name, 'metadata')

        success = await self.metadata_processor.process_subreddit(subreddit_name)
        if not success:
            logger.warning(f"Skipping r/{subreddit_name} - metadata fetch failed")
            self.db.update_processing_tier_status(subreddit_name, 'posts', 'error')
            return False

        # Phase 2: Posts + Media URLs
        logger.info(f"[2/2] Fetching posts and media URLs")
        self.db.update_processing_state(subreddit_name, 'posts')

        posts_count, media_count = await self.posts_processor.process_subreddit(subreddit_name)

        if posts_count == 0:
            logger.warning(f"No posts found for r/{subreddit_name}")

        # Mark posts complete
        self.db.mark_posts_complete(subreddit_name)
        self.db.update_processing_tier_activity('posts')
        self.db.increment_processing_tier_processed('posts')

        logger.info("")
        logger.info(f"✓ r/{subreddit_name} POSTS COMPLETE:")
        logger.info(f"  - {posts_count:,} posts")
        logger.info(f"  - {media_count:,} media URLs")
        logger.info("")

        return True

    async def process_comments_batch(self, batch_size: int = None) -> int:
        """
        Comments: Comments (batch processing)
        Fetches comments for a small batch of posts spread across multiple subreddits.
        """
        if batch_size is None:
            batch_size = self.config.comments_batch_size

        logger.info("")
        logger.info("=" * 60)
        logger.info(f"[COMMENTS] Processing comment batch (size: {batch_size})")
        logger.info("=" * 60)

        posts = self.db.get_posts_for_comments_batch(
            limit=batch_size,
            spread_across_subs=True
        )

        if not posts:
            logger.info("No posts needing comments")
            return 0

        logger.info(f"Found {len(posts)} posts needing comments across {len(set(p['subreddit'] for p in posts))} subreddits")

        comments_fetched = 0

        for i, post in enumerate(posts, 1):
            subreddit = post['subreddit']
            post_id = post['id']
            title = post['title']

            logger.info(f"[{i}/{len(posts)}] r/{subreddit}: {title[:50]}")

            # Mark subreddit as comments processing if not already
            self.db.update_processing_tier_status(subreddit, 'comments', 'processing')

            try:
                count = await self.comments_processor.process_post(subreddit, post_id, title)
                comments_fetched += count

                # Update posts_pending_comments for this subreddit
                self.db.update_posts_pending_comments(subreddit)

                # Check if subreddit comments is complete
                remaining = self.db.get_posts_for_comments(subreddit, limit=1)
                if not remaining:
                    self.db.mark_comments_complete(subreddit)
                    logger.info(f"✓ r/{subreddit} comments complete")

            except Exception as e:
                logger.error(f"Error fetching comments for {post_id}: {e}")

            # Longer delay between posts for comments (anti-detection)
            if i < len(posts):
                await self.anti_detection.random_delay(2.0, 5.0)

        self.db.update_processing_tier_activity('comments')
        self.db.increment_processing_tier_processed('comments', len(posts))
        self.last_comments_run = time.time()

        logger.info("")
        logger.info(f"✓ COMMENTS BATCH COMPLETE: {comments_fetched:,} comments fetched")
        logger.info("")

        return comments_fetched

    def should_run_comments(self) -> bool:
        """Check if it's time to run a comments batch"""
        if self.config.scanner_mode == 'threads':
            return False

        elapsed = time.time() - self.last_comments_run
        return elapsed >= self.config.comments_cooldown

    async def run_threads_only(self, limit: int = 50):
        """Run threads processing only (posts + media URLs, no comments)"""
        logger.info("Mode: Threads Only (Posts + Media URLs)")
        logger.info("")

        # Set all comments to deferred for threads-only mode
        self.db.set_all_comments_deferred()

        subreddits = self.db.get_subreddits_for_posts(
            limit=limit,
            min_subscribers=self.config.min_subscribers
        )

        if not subreddits:
            logger.info("No subreddits need posts processing")
            return

        # Apply anti-detection shuffling
        subreddits = self.anti_detection.shuffle_with_bias(subreddits, 'subscribers')

        logger.info(f"Found {len(subreddits)} subreddits for posts")
        logger.info("")

        processed = 0
        failed = 0

        for i, sub in enumerate(subreddits, 1):
            # Check for pause
            pause_remaining = self.db.check_pause()
            if pause_remaining:
                logger.info(f"Scanner paused for {pause_remaining}s")
                await asyncio.sleep(pause_remaining)

            try:
                logger.info(f"[{i}/{len(subreddits)}] r/{sub['name']}")
                success = await self.process_posts(sub['name'])
                if success:
                    processed += 1
                else:
                    failed += 1

                # Anti-detection break
                await self.anti_detection.maybe_take_break()

                # Pause between subreddits
                if i < len(subreddits):
                    pause = random.uniform(
                        self.config.subreddit_pause_min,
                        self.config.subreddit_pause_max
                    )
                    logger.info(f"Pausing {pause:.0f}s before next subreddit...")
                    await asyncio.sleep(pause)

            except Exception as e:
                logger.error(f"Error processing r/{sub['name']}: {e}", exc_info=True)
                failed += 1

        logger.info("")
        logger.info("=" * 60)
        logger.info("POSTS BATCH COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Processed: {processed}")
        logger.info(f"Failed: {failed}")
        logger.info("")

    async def run_comments_only(self):
        """Run comments processing only (comment backfill)"""
        logger.info("Mode: Comments Only (Comments)")
        logger.info("")

        while True:
            # Check for pause
            pause_remaining = self.db.check_pause()
            if pause_remaining:
                logger.info(f"Scanner paused for {pause_remaining}s")
                await asyncio.sleep(pause_remaining)

            # Process a batch
            count = await self.process_comments_batch()

            if count == 0:
                logger.info("No more comments to fetch")
                break

            # Cooldown before next batch
            logger.info(f"Cooldown for {self.config.comments_cooldown:.0f}s before next batch...")
            await asyncio.sleep(self.config.comments_cooldown)


    async def run(self, limit: int = 50):
        """Main entry point - dispatches based on mode"""
        mode = self.config.scanner_mode

        if mode == 'threads':
            await self.run_threads_only(limit)
        elif mode == 'comments':
            await self.run_comments_only()
        else:
            raise ValueError(f"Invalid scanner_mode: {mode}. Must be 'threads' or 'comments'")

        # Final stats
        stats = self.db.get_stats()
        logger.info("Database Stats:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value:,}")

    async def sync_from_scanner(self, sqlite_path: str, min_subscribers: int = 5000):
        """Import/update subreddits from scanner SQLite database"""
        logger.info("")
        logger.info("=" * 60)
        logger.info("SCANNER SQLITE SYNC")
        logger.info("=" * 60)
        logger.info(f"Scanner DB: {sqlite_path}")
        logger.info(f"Min subscribers: {min_subscribers:,}")
        logger.info("")

        if not Path(sqlite_path).exists():
            logger.error(f"Scanner database not found: {sqlite_path}")
            return

        conn = sqlite3.connect(sqlite_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT name, subscribers
            FROM subreddits
            WHERE is_accessible = 1
                AND status = 'active'
                AND subscribers >= ?
            ORDER BY subscribers DESC
            """,
            (min_subscribers,)
        )

        rows = cursor.fetchall()
        conn.close()

        logger.info(f"Found {len(rows):,} accessible subreddits with {min_subscribers}+ subscribers")
        logger.info("")

        added = 0
        updated = 0

        for name, subscribers in rows:
            # Calculate priority (1=highest, 5=lowest)
            if subscribers >= 1_000_000:
                priority = 1
            elif subscribers >= 500_000:
                priority = 2
            elif subscribers >= 100_000:
                priority = 3
            elif subscribers >= 10_000:
                priority = 4
            else:
                priority = 5

            was_new, was_updated = self.db.upsert_subreddit(name, priority, subscribers)

            if was_new:
                added += 1
            elif was_updated:
                updated += 1

            if (added + updated) % 100 == 0:
                logger.info(f"Progress: {added:,} added, {updated:,} updated")

        logger.info("")
        logger.info("=" * 60)
        logger.info("SYNC COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Added: {added:,} new subreddits")
        logger.info(f"Updated: {updated:,} existing subreddits")
        logger.info(f"Total synced: {added + updated:,}")
        logger.info("")


async def main():
    parser = argparse.ArgumentParser(description='Reddit Archiver Scanner')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Run command (main scanner)
    run_parser = subparsers.add_parser('run', help='Run the scanner')
    run_parser.add_argument('--limit', type=int, default=50, help='Batch size (default: 50)')
    run_parser.add_argument('--mode', choices=['threads', 'comments'], help='Override SCANNER_MODE')

    # Sync command (import from scanner SQLite)
    sync_parser = subparsers.add_parser('sync', help='Sync subreddits from scanner SQLite database')
    sync_parser.add_argument('--scanner-db', required=True, help='Path to scanner SQLite database')
    sync_parser.add_argument('--min-subscribers', type=int, default=5000, help='Min subscribers (default: 5000)')

    # Import CSV command
    import_parser = subparsers.add_parser('import-csv', help='Import subreddits from CSV')
    import_parser.add_argument('csv_file', help='Path to CSV file')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        config = ArchiverConfig.from_env()

        # Override mode if specified
        if hasattr(args, 'mode') and args.mode:
            config.scanner_mode = args.mode

        config.validate()
    except Exception as e:
        print(f"Config error: {e}")
        sys.exit(1)

    setup_logging(config.log_level)

    scanner = TieredScanner(config)

    try:
        await scanner.initialize()

        # Run migrations
        migrations_dir = Path(__file__).parent.parent / 'migrations'
        schema_file = migrations_dir / '001_initial_schema.sql'

        if schema_file.exists():
            logger.info("Running migrations")
            scanner.db.run_migration(str(schema_file))
            logger.info("✓ Migrations complete")
            logger.info("")

        # Execute command
        if args.command == 'sync':
            await scanner.sync_from_scanner(args.scanner_db, args.min_subscribers)

        elif args.command == 'import-csv':
            await import_csv_subreddits(scanner, args.csv_file)

        elif args.command == 'run':
            stats = scanner.db.get_stats()
            logger.info("Initial Stats:")
            for key, value in stats.items():
                logger.info(f"  {key}: {value:,}")
            logger.info("")

            await scanner.run(limit=args.limit)

    except KeyboardInterrupt:
        logger.info("")
        logger.info("Interrupted")
    except Exception as e:
        logger.error(f"Fatal: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await scanner.shutdown()


async def import_csv_subreddits(scanner: TieredScanner, csv_path: str):
    """Import subreddits from CSV file"""
    import csv

    logger.info("")
    logger.info("=" * 60)
    logger.info("IMPORT SUBREDDITS FROM CSV")
    logger.info("=" * 60)
    logger.info(f"CSV file: {csv_path}")
    logger.info("")

    if not Path(csv_path).exists():
        logger.error(f"CSV file not found: {csv_path}")
        return

    added = 0
    skipped = 0

    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)

        for row in reader:
            name = row['subreddit']
            priority = int(row['priority'])

            if scanner.db.add_subreddit(name, priority):
                added += 1
            else:
                skipped += 1

            if (added + skipped) % 50 == 0:
                logger.info(f"Progress: {added:,} added, {skipped:,} skipped")

    logger.info("")
    logger.info("=" * 60)
    logger.info("IMPORT COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Added: {added:,} new subreddits")
    logger.info(f"Skipped: {skipped:,} (already exist)")
    logger.info(f"Total: {added + skipped:,}")
    logger.info("")


if __name__ == '__main__':
    asyncio.run(main())
