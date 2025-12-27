"""
Main subreddit scanner orchestrator.

Coordinates database, Reddit API client, and rate limiting to process subreddits.
"""

import asyncio
import logging
import signal
import time
from pathlib import Path
from typing import Optional, List

# Local imports (works when run directly)
from config import Config
from database import Database
from rate_limiter import SlidingWindowRateLimiter
from reddit_client import RedditAPIClient


class SubredditScanner:
    """
    Main orchestrator for subreddit scanning.

    Handles:
    - Loading subreddit lists
    - Processing subreddits (metadata only)
    - Progress tracking and reporting
    - Graceful shutdown
    """

    def __init__(self, config: Config):
        """
        Initialize scanner.

        Args:
            config: Configuration object
        """
        self.config = config
        self.running = False
        self.shutdown_requested = False

        # Initialize components
        self.db = Database(config.db_path)
        self.rate_limiter = SlidingWindowRateLimiter(
            requests_per_minute=config.rate_limit_per_minute,
            requests_per_10s=config.rate_limit_per_10s,
            requests_per_1s=config.rate_limit_per_1s
        )
        self.reddit_client = RedditAPIClient(config, self.rate_limiter)

        # Statistics
        self.start_time: Optional[float] = None
        self.subreddits_processed = 0
        self.subreddits_failed = 0

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        signal_name = 'SIGINT' if signum == signal.SIGINT else 'SIGTERM'
        logging.info(f"\n{signal_name} received, shutting down gracefully...")
        self.shutdown_requested = True

    async def initialize(self):
        """Initialize scanner components."""
        await self.reddit_client.initialize()
        logging.debug("Scanner initialized")

    async def load_subreddit_list(self, file_path: str) -> int:
        """
        Load subreddit list from file and add to database.

        Args:
            file_path: Path to file containing subreddit names (one per line)

        Returns:
            Number of subreddits added
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Subreddit list file not found: {file_path}")

        logging.info(f"Loading subreddit list from {file_path}...")

        subreddits = []
        with open(path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    # Remove r/ prefix if present
                    if line.startswith('r/'):
                        line = line[2:]
                    subreddits.append(line.lower())

        if not subreddits:
            raise ValueError(f"No subreddits found in {file_path}")

        logging.info(f"Found {len(subreddits)} subreddits in file")
        logging.info("Adding subreddits to database...")

        added = self.db.add_subreddits_bulk(subreddits)

        # Get current database stats after import
        stats = self.db.get_processing_stats()

        logging.info(
            f"\n{'='*60}\n"
            f"Subreddit List Import Complete:\n"
            f"  From file: {len(subreddits)} subreddits\n"
            f"  New additions: {added}\n"
            f"  Already existed: {len(subreddits) - added}\n"
            f"  Total in database: {stats.get('total_subreddits', 0)}\n"
            f"  Pending processing: {stats.get('pending', 0)}\n"
            f"  Previously completed: {stats.get('completed', 0)}\n"
            f"{'='*60}"
        )

        # Rename imported file to prevent re-import
        import datetime
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = path.parent / f"{path.stem}.imported_{timestamp}{path.suffix}"

        try:
            path.rename(backup_path)
            logging.info(f"\n✓ Input file renamed to: {backup_path.name}")
            logging.info("  (This prevents accidental re-import)")
        except Exception as e:
            logging.warning(f"Could not rename input file: {e}")
            logging.warning("  You may want to manually rename/delete it to avoid re-import")

        return added

    async def process_subreddit(self, subreddit: str) -> bool:
        """
        Process a single subreddit: fetch metadata only.

        Args:
            subreddit: Subreddit name

        Returns:
            True if successful, False otherwise
        """
        # Update state to processing
        self.db.update_subreddit(subreddit, 'processing')

        try:
            # Fetch subreddit metadata
            metadata, status = await self.reddit_client.get_subreddit_info(subreddit)

            if status == 'active' and metadata:
                # Update database with metadata
                self.db.update_subreddit_metadata(subreddit, metadata)

                # Store metadata for output
                subscribers = metadata.get('subscribers', 0) or 0  # Handle None
                nsfw = metadata.get('over18', False)

                # Mark metadata as collected
                self.db.update_subreddit(
                    subreddit, 'active', None,
                    metadata_collected=True
                )

                # Update statistics
                self.subreddits_processed += 1

                # Clean single-line output
                nsfw_flag = '🔞' if nsfw else '  '
                logging.info(
                    f"✓ r/{subreddit:<25} {nsfw_flag} {subscribers:>12,} subs"
                )

                return True

            else:
                # Update status for non-active subreddits
                self.db.update_subreddit_status(subreddit, status)

                # Log non-active status and return
                logging.warning(f"⚠️  r/{subreddit} - {status}")

                # Mark as completed with metadata collected
                self.db.update_subreddit(
                    subreddit, 'completed', f"Status: {status}",
                    metadata_collected=True
                )
                return True

        except Exception as e:
            logging.error(f"❌ r/{subreddit} - Error: {e}")
            logging.debug(f"Error processing r/{subreddit}: {e}", exc_info=True)
            self.db.update_subreddit(
                subreddit,
                'error',
                error_message=str(e)
            )
            self.subreddits_failed += 1
            return False

    async def run(self):
        """Run the scanner main loop."""
        self.running = True
        self.start_time = time.time()

        # Fix any inconsistent states before processing
        fixed = self.db.fix_inconsistent_states()
        if sum(fixed.values()) > 0:
            logging.info(f"Fixed {sum(fixed.values())} inconsistent database states")

        # Get initial counts
        stats = self.db.get_processing_stats()
        pending = len(self.db.get_pending_subreddits())

        print("=" * 80)
        print(f"🚀 Starting Scanner - Subreddit Metadata Collection")
        print(f"   {pending:,} subreddits need metadata")
        print("=" * 80)
        print()

        try:
            while not self.shutdown_requested:
                # Get pending subreddits
                pending = self.db.get_pending_subreddits(limit=1)

                if not pending:
                    print()
                    logging.info("✅ All subreddit metadata collected!")
                    break

                subreddit = pending[0]

                # Process subreddit
                await self.process_subreddit(subreddit)

                # Show live progress after each subreddit
                self._show_progress()

                # Progress report every 10 subreddits
                if self.subreddits_processed % 10 == 0:
                    self._report_progress()

                # Cooldown between subreddits
                if not self.shutdown_requested and self.config.subreddit_cooldown > 0:
                    await asyncio.sleep(self.config.subreddit_cooldown)

            # Final report
            print()
            self._report_final()

        except Exception as e:
            logging.error(f"Scanner error: {e}", exc_info=True)
        finally:
            self.running = False

    def _show_progress(self):
        """Show live progress line after each subreddit."""
        stats = self.db.get_processing_stats()
        elapsed = time.time() - self.start_time
        total = stats.get('total_subreddits', 0)

        completed = stats.get('metadata_collected', 0)
        pending = stats.get('metadata_pending', 0)

        # Calculate rate and ETA
        if elapsed > 0:
            subs_per_hour = (self.subreddits_processed / elapsed) * 3600
            if subs_per_hour > 0:
                hours_remaining = pending / subs_per_hour
                eta_hours = int(hours_remaining)
                eta_minutes = int((hours_remaining - eta_hours) * 60)
                eta_str = f"{eta_hours}h {eta_minutes}m"
            else:
                eta_str = "calculating..."
        else:
            subs_per_hour = 0
            eta_str = "calculating..."

        # Progress percentage
        progress_pct = (completed / total * 100) if total > 0 else 0

        # Clean progress line
        print(
            f"   Progress: {completed:>5}/{total} ({progress_pct:>5.1f}%)  |  "
            f"{subs_per_hour:>5.1f} subs/hr  |  "
            f"ETA: {eta_str:<10}"
        )

    def _report_progress(self):
        """Report current progress."""
        stats = self.db.get_processing_stats()
        elapsed = time.time() - self.start_time

        completed = stats.get('metadata_collected', 0)
        pending = stats.get('metadata_pending', 0)

        # Calculate rates
        subs_per_hour = (self.subreddits_processed / elapsed * 3600) if elapsed > 0 else 0
        hours_remaining = (pending / subs_per_hour) if subs_per_hour > 0 else 0

        # Format elapsed time
        hours = int(elapsed / 3600)
        minutes = int((elapsed % 3600) / 60)
        elapsed_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

        # Format ETA
        eta_hours = int(hours_remaining)
        eta_minutes = int((hours_remaining - eta_hours) * 60)
        eta_str = f"{eta_hours}h {eta_minutes}m"

        print()
        print("=" * 80)
        print(f"📊 Progress Report (every 10 subreddits)")
        print("-" * 80)
        print(f"   Completed: {completed:>6,} / {stats.get('total_subreddits', 0):,} total")
        print(f"   Pending:   {pending:>6,}")
        print(f"   Failed:    {self.subreddits_failed:>6}")
        print("-" * 80)
        print(f"   Rate:      {subs_per_hour:>6.1f} subreddits/hour")
        print(f"   Elapsed:   {elapsed_str:>6}")
        print(f"   ETA:       {eta_str:>6} remaining")
        print("=" * 80)
        print()

    def _report_final(self):
        """Report final statistics."""
        stats = self.db.get_processing_stats()
        elapsed = time.time() - self.start_time

        completed = stats.get('metadata_collected', 0)
        pending = stats.get('metadata_pending', 0)

        # Calculate rates
        subs_per_hour = (self.subreddits_processed / elapsed * 3600) if elapsed > 0 else 0

        # Format elapsed time
        hours = int(elapsed / 3600)
        minutes = int((elapsed % 3600) / 60)
        elapsed_str = f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"

        reddit_stats = self.reddit_client.get_stats()

        print("=" * 80)
        print("🏁 Final Report")
        print("=" * 80)
        print()
        print("Processing:")
        print(f"  Total subreddits:    {stats.get('total_subreddits', 0):>8,}")
        print(f"  Completed:           {completed:>8,}")
        print(f"  Pending:             {pending:>8,}")
        print(f"  Errors:              {stats.get('error', 0):>8}")
        print()
        print("Performance:")
        print(f"  Processing rate:     {subs_per_hour:>8.1f} subs/hour")
        print(f"  Total time:          {elapsed_str:>8}")
        print()
        print("API Statistics:")
        print(f"  Total requests:      {reddit_stats['total_requests']:>8,}")
        print(f"  Failed requests:     {reddit_stats['failed_requests']:>8,}")
        print(f"  Success rate:        {reddit_stats['success_rate']*100:>7.1f}%")
        print(f"  Rate limit hits:     {reddit_stats['rate_limit_hits']:>8}")
        print("=" * 80)

    async def shutdown(self):
        """Shutdown scanner and cleanup resources."""
        logging.debug("Shutting down scanner...")

        await self.reddit_client.close()
        self.db.close()

        logging.debug("Scanner shutdown complete")
