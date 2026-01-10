"""
Main subreddit scanner orchestrator.

Coordinates database, Reddit API client, and rate limiting to process subreddits.
"""

import asyncio
import logging
import signal
import time
import random
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

        # Processing mode and limits
        self.mode: Optional[str] = None  # 'metadata', 'update', or 'threads'
        self.limit: Optional[int] = None  # Batch limit
        self.csv_path: Optional[str] = None  # CSV file for scan-csv mode
        self.nsfw_only: bool = False  # Filter for NSFW subreddits only

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

        # Error tracking for auto-termination
        self.consecutive_403s = 0
        self.total_429s = 0

        # Track recent successes to distinguish real 403s from throttling
        self.recent_successes = []  # Last N successful requests
        self.recent_success_window = 10  # Track last 10 requests

        # Setup signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        signal_name = 'SIGINT' if signum == signal.SIGINT else 'SIGTERM'
        logging.info(f"\n{signal_name} received, shutting down gracefully...")
        self.shutdown_requested = True

    def _track_success(self):
        """Track a successful request to help distinguish real 403s from throttling."""
        self.recent_successes.append(True)
        if len(self.recent_successes) > self.recent_success_window:
            self.recent_successes.pop(0)

    def _should_trust_403(self) -> bool:
        """
        Determine if a 403 is likely a real delete/ban vs. throttling.

        If we've had 5+ successes in the last 10 requests, we're not being throttled,
        so 403s are likely real bans/deletes.
        """
        return len(self.recent_successes) >= 5

    def _check_error_thresholds(self) -> bool:
        """Check if error thresholds exceeded. Returns True if should terminate."""
        max_403 = getattr(self.config, 'max_consecutive_403', 10)
        max_429 = getattr(self.config, 'max_total_429', 3)

        # Check 429s from reddit client
        self.total_429s = self.reddit_client.rate_limit_hits

        if self.consecutive_403s >= max_403:
            logging.error(f"🛑 {self.consecutive_403s} consecutive 403s - likely blocked. Terminating.")
            return True

        if self.total_429s >= max_429:
            logging.error(f"🛑 {self.total_429s} rate limit hits (429s) - backing off. Terminating.")
            return True

        return False

    def _interleave_with_random(self, ordered_list: List[str]) -> List[str]:
        """
        Interleave ordered list with random picks for organic access pattern.

        Pattern: popular, random, popular, random...
        This makes update scans look less like systematic scraping.
        """
        if len(ordered_list) <= 2:
            return ordered_list

        result = []
        remaining = set(ordered_list)
        ordered_idx = 0

        while remaining:
            # Pick next from ordered list (popular first)
            if ordered_idx < len(ordered_list) and ordered_list[ordered_idx] in remaining:
                sub = ordered_list[ordered_idx]
                result.append(sub)
                remaining.discard(sub)
                ordered_idx += 1
            else:
                # Skip already-used items in ordered list
                while ordered_idx < len(ordered_list) and ordered_list[ordered_idx] not in remaining:
                    ordered_idx += 1
                if ordered_idx < len(ordered_list):
                    sub = ordered_list[ordered_idx]
                    result.append(sub)
                    remaining.discard(sub)
                    ordered_idx += 1

            if not remaining:
                break

            # Pick random from remaining
            random_pick = random.choice(list(remaining))
            result.append(random_pick)
            remaining.discard(random_pick)

        return result

    async def initialize(self):
        """Initialize scanner components."""
        await self.reddit_client.initialize()
        logging.debug("Scanner initialized")

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

            # Skip if it's a user profile (and remove from DB)
            if metadata and metadata.get('subreddit_type') == 'user':
                self.db.conn.execute("DELETE FROM subreddits WHERE name = ?", (subreddit,))
                self.db.conn.commit()
                logging.info(f"⏭️  r/{subreddit:<25} (user profile, removed)")
                return True

            if status == 'active' and metadata:
                # Success - reset consecutive 403 counter and retry count
                self.consecutive_403s = 0

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

                # Reset retry count on success
                self.db.conn.execute(
                    "UPDATE subreddits SET retry_count = 0 WHERE name = ?",
                    (subreddit,)
                )
                self.db.conn.commit()

                # Update statistics
                self.subreddits_processed += 1

                # Clean single-line output
                nsfw_flag = '🔞' if nsfw else '  '
                logging.info(
                    f"✓ r/{subreddit:<25} {nsfw_flag} {subscribers:>12,} subs"
                )

                return True

            else:
                # Handle non-active statuses

                # Get current retry count
                cursor = self.db.conn.execute(
                    "SELECT retry_count FROM subreddits WHERE name = ?",
                    (subreddit,)
                )
                row = cursor.fetchone()
                retry_count = row[0] if row and row[0] is not None else 0

                # Handle 404 - subreddit doesn't exist, remove immediately
                if status == 'notfound':
                    self.db.conn.execute("DELETE FROM subreddits WHERE name = ?", (subreddit,))
                    self.db.conn.commit()
                    logging.warning(f"⚠️  r/{subreddit:<25} - 404 not found (removed from DB)")
                    self.consecutive_403s = 0
                    return True

                # Handle 403/deleted - potential ban/delete, use retry logic
                elif status == 'deleted':
                    self.consecutive_403s += 1
                    retry_count += 1

                    if retry_count >= 3:
                        # Failed 3 times, remove from DB
                        self.db.conn.execute("DELETE FROM subreddits WHERE name = ?", (subreddit,))
                        self.db.conn.commit()
                        logging.warning(f"⚠️  r/{subreddit:<25} - 403 forbidden (3 retries, removed from DB)")
                        self.consecutive_403s = 0
                        return True
                    else:
                        # Increment retry count, keep in DB
                        self.db.conn.execute(
                            "UPDATE subreddits SET retry_count = ? WHERE name = ?",
                            (retry_count, subreddit)
                        )
                        self.db.conn.commit()
                        logging.warning(f"⚠️  r/{subreddit:<25} - 403 forbidden (retry {retry_count}/3)")
                        return True

                # Handle other non-active statuses (private, quarantined, etc)
                else:
                    self.consecutive_403s = 0

                    # Update status but keep in DB
                    self.db.update_subreddit_status(subreddit, status)
                    self.db.update_subreddit(
                        subreddit, status, f"Status: {status}",
                        metadata_collected=True
                    )

                    # Reset retry count on successful response
                    self.db.conn.execute(
                        "UPDATE subreddits SET retry_count = 0 WHERE name = ?",
                        (subreddit,)
                    )
                    self.db.conn.commit()

                    logging.warning(f"⚠️  r/{subreddit:<25} - {status}")
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

        # Get subreddits that need updating (stale or never updated)
        subreddits_to_process = self.db.get_subreddits_for_update(
            limit=self.limit,
            nsfw_only=self.nsfw_only
        )
        mode_desc = "subreddits to UPDATE" + (" (NSFW only)" if self.nsfw_only else "")

        # Interleaved order: alternate popular + random for organic pattern
        subreddits_to_process = self._interleave_with_random(subreddits_to_process)
        logging.debug("Interleaved update order: alternating popular + random")

        total_to_process = len(subreddits_to_process)

        print("=" * 80)
        print(f"🔄 Starting Scanner - Metadata UPDATE (Refresh)")
        print(f"   {total_to_process:,} {mode_desc}")
        if self.limit:
            print(f"   Limited to: {self.limit:,} subreddits")
        print("=" * 80)
        print()

        try:
            if total_to_process == 0:
                print()
                logging.info("✅ No subreddits to process!")
            else:
                for idx, subreddit in enumerate(subreddits_to_process):
                    if self.shutdown_requested:
                        break

                    # Check error thresholds before processing
                    if self._check_error_thresholds():
                        self.shutdown_requested = True
                        break

                    # Process subreddit
                    await self.process_subreddit(subreddit)

                    # Check error thresholds after processing
                    if self._check_error_thresholds():
                        self.shutdown_requested = True
                        break

                    # Show live progress after each subreddit
                    self._show_progress(idx + 1, total_to_process)

                    # Progress report every 10 subreddits
                    if self.subreddits_processed % 10 == 0:
                        self._report_progress()

                    # Cooldown between subreddits
                    if not self.shutdown_requested and self.config.subreddit_cooldown > 0:
                        await asyncio.sleep(self.config.subreddit_cooldown)

                    # Batch pause every N subreddits (human-like break)
                    interval = getattr(self.config, 'batch_pause_interval', 75)
                    if not self.shutdown_requested and (idx + 1) % interval == 0:
                        pause_min = getattr(self.config, 'batch_pause_min', 30.0)
                        pause_max = getattr(self.config, 'batch_pause_max', 60.0)
                        pause = random.uniform(pause_min, pause_max)
                        logging.info(f"☕ Batch pause ({idx + 1} processed): {pause:.0f}s...")
                        await asyncio.sleep(pause)

                # Final report
                print()
                if idx + 1 >= total_to_process and not self.shutdown_requested:
                    logging.info("✅ All subreddit metadata updated!")

            self._report_final()

        except Exception as e:
            logging.error(f"Scanner error: {e}", exc_info=True)
        finally:
            self.running = False

    def _show_progress(self, current: int, total: int):
        """Show live progress line after each subreddit."""
        elapsed = time.time() - self.start_time

        # Calculate rate and ETA
        if elapsed > 0:
            subs_per_hour = (self.subreddits_processed / elapsed) * 3600
            remaining = total - current
            if subs_per_hour > 0:
                hours_remaining = remaining / subs_per_hour
                eta_hours = int(hours_remaining)
                eta_minutes = int((hours_remaining - eta_hours) * 60)
                eta_str = f"{eta_hours}h {eta_minutes}m"
            else:
                eta_str = "calculating..."
        else:
            subs_per_hour = 0
            eta_str = "calculating..."

        # Progress percentage
        progress_pct = (current / total * 100) if total > 0 else 0

        # Clean progress line
        print(
            f"   Progress: {current:>5}/{total} ({progress_pct:>5.1f}%)  |  "
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

    async def run_csv_scan(self):
        """
        SCAN-CSV mode: Atomic processing from CSV file.

        For each subreddit in CSV:
        1. Check if already in DB (duplicate) → remove from CSV
        2. If not in DB → fetch from Reddit API, save to DB, remove from CSV
        3. Write CSV back to disk after each batch

        CSV shrinks as we process. Safe and resumable.
        """
        import csv
        from pathlib import Path

        self.running = True
        self.start_time = time.time()

        csv_path = Path(self.csv_path)
        if not csv_path.exists():
            logging.error(f"CSV file not found: {self.csv_path}")
            return

        print("=" * 80)
        print(f"📄 Loading CSV: {csv_path}")
        print("=" * 80)

        # Load entire CSV into memory
        csv_rows = []
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('subreddit'):
                    csv_rows.append(row)

        # Sort by subscribers descending (highest first)
        csv_rows.sort(key=lambda x: int(x.get('subscribers', 0) or 0), reverse=True)
        logging.debug("Sorted CSV by subscribers (highest first)")

        initial_count = len(csv_rows)
        limit = self.limit if self.limit else len(csv_rows)

        print(f"CSV contains: {initial_count:,} subreddits")
        print(f"Will process: {min(limit, initial_count):,} subreddits")
        print("=" * 80)
        print()

        processed = 0
        duplicates_removed = 0
        scanned_and_saved = 0
        errors = 0

        try:
            rows_to_keep = []

            for idx, row in enumerate(csv_rows):
                if self.shutdown_requested:
                    logging.info("Shutdown requested, saving progress...")
                    rows_to_keep.extend(csv_rows[idx:])  # Keep unprocessed rows
                    break

                # Check error thresholds
                if self._check_error_thresholds():
                    logging.info("Error threshold exceeded, saving progress...")
                    self.shutdown_requested = True
                    rows_to_keep.extend(csv_rows[idx:])  # Keep unprocessed rows
                    break

                if processed >= limit:
                    # Reached limit, keep remaining rows
                    rows_to_keep.extend(csv_rows[idx:])
                    break

                subreddit = row['subreddit'].strip().lower()

                # Check if already in database
                existing = self.db.conn.execute(
                    "SELECT name FROM subreddits WHERE name = ?",
                    (subreddit,)
                ).fetchone()

                if existing:
                    # Duplicate - remove from CSV (don't keep this row)
                    duplicates_removed += 1
                    logging.info(f"⏭️  r/{subreddit:<25} (duplicate, removed from CSV)")
                else:
                    # Not in DB - fetch from Reddit API
                    try:
                        # Add to DB as pending first
                        self.db.add_subreddit(subreddit)

                        # Fetch metadata
                        metadata, status = await self.reddit_client.get_subreddit_info(subreddit)

                        # Skip if it's a user profile (and remove from DB)
                        if metadata and metadata.get('subreddit_type') == 'user':
                            self.db.conn.execute("DELETE FROM subreddits WHERE name = ?", (subreddit,))
                            self.db.conn.commit()
                            logging.info(f"⏭️  r/{subreddit:<25} (user profile, skipped)")
                            continue

                        if status == 'active' and metadata:
                            # Success - reset consecutive 403 counter and track success
                            self.consecutive_403s = 0
                            self._track_success()

                            subscribers = metadata.get('subscribers', 0) or 0

                            # Filter out tiny subreddits (< 100 subscribers) from current API data
                            if subscribers < 100:
                                logging.info(f"⏭️  r/{subreddit:<25} (< 100 subs, skipped)")
                                # Remove from DB (was added as pending)
                                self.db.conn.execute("DELETE FROM subreddits WHERE name = ?", (subreddit,))
                                self.db.conn.commit()
                                # Don't keep this row - filtered out
                                continue

                            # Save metadata
                            self.db.update_subreddit_metadata(subreddit, metadata)
                            self.db.update_subreddit(
                                subreddit, 'active', None,
                                metadata_collected=True
                            )

                            nsfw_flag = '🔞' if metadata.get('over18', False) else '  '
                            logging.info(
                                f"✓ r/{subreddit:<25} {nsfw_flag} {subscribers:>12,} subs (scanned & saved)"
                            )
                            scanned_and_saved += 1
                        elif status == 'notfound':
                            # 404 - subreddit doesn't exist, don't add to DB
                            self.consecutive_403s = 0
                            self._track_success()

                            # Remove from DB (was added as pending)
                            self.db.conn.execute("DELETE FROM subreddits WHERE name = ?", (subreddit,))
                            self.db.conn.commit()
                            logging.warning(f"⚠️  r/{subreddit:<25} - 404 not found (not added to DB, removed from CSV)")
                            # Don't increment scanned_and_saved - we didn't save it

                        elif status == 'deleted':
                            # 403 - likely deleted/banned, don't add to DB
                            self.consecutive_403s = 0
                            self._track_success()

                            # Remove from DB (was added as pending)
                            self.db.conn.execute("DELETE FROM subreddits WHERE name = ?", (subreddit,))
                            self.db.conn.commit()
                            logging.warning(f"⚠️  r/{subreddit:<25} - 403 forbidden (not added to DB, removed from CSV)")
                            # Don't increment scanned_and_saved - we didn't save it

                        else:
                            # Other non-active states (private, quarantined) - keep in DB
                            self.consecutive_403s = 0
                            self._track_success()

                            self.db.update_subreddit_status(subreddit, status)
                            self.db.update_subreddit(
                                subreddit, status, f"Status: {status}",
                                metadata_collected=True
                            )
                            logging.warning(f"⚠️  r/{subreddit:<25} - {status} (saved status)")
                            scanned_and_saved += 1

                        # Successfully processed - DON'T keep this row (unless it was a 403 retry)

                    except Exception as e:
                        logging.error(f"❌ r/{subreddit} - Error: {e}")
                        errors += 1
                        # Keep row on error so we can retry later
                        rows_to_keep.append(row)

                processed += 1

                # Show progress every 10 subreddits
                if processed % 10 == 0:
                    print()
                    print(f"   Progress: {processed}/{min(limit, initial_count)} | "
                          f"Scanned: {scanned_and_saved} | "
                          f"Duplicates removed: {duplicates_removed} | "
                          f"Errors: {errors}")
                    print()

                # Cooldown
                if not self.shutdown_requested and self.config.subreddit_cooldown > 0:
                    await asyncio.sleep(self.config.subreddit_cooldown)

                # Batch pause every N subreddits (human-like break)
                interval = getattr(self.config, 'batch_pause_interval', 75)
                if not self.shutdown_requested and processed % interval == 0:
                    pause_min = getattr(self.config, 'batch_pause_min', 30.0)
                    pause_max = getattr(self.config, 'batch_pause_max', 60.0)
                    pause = random.uniform(pause_min, pause_max)
                    logging.info(f"☕ Batch pause ({processed} processed): {pause:.0f}s...")
                    await asyncio.sleep(pause)

            # Write updated CSV (only rows we're keeping)
            print()
            print("=" * 80)
            print("💾 Updating CSV file...")

            with open(csv_path, 'w', newline='') as f:
                if rows_to_keep:
                    writer = csv.DictWriter(f, fieldnames=['subreddit', 'subscribers', 'retry_count'], extrasaction='ignore')
                    writer.writeheader()
                    for row in rows_to_keep:
                        # Ensure retry_count exists
                        if 'retry_count' not in row:
                            row['retry_count'] = 0
                        writer.writerow(row)
                else:
                    # Empty CSV - write just header
                    writer = csv.DictWriter(f, fieldnames=['subreddit', 'subscribers', 'retry_count'])
                    writer.writeheader()

            final_count = len(rows_to_keep)
            removed_total = initial_count - final_count

            print(f"✓ CSV updated:")
            print(f"  Started with:        {initial_count:,} subreddits")
            print(f"  Removed from CSV:    {removed_total:,} (scanned + duplicates)")
            print(f"  Remaining in CSV:    {final_count:,}")
            print("=" * 80)
            print()

            # Final report
            print("=" * 80)
            print("📊 CSV Scan Complete")
            print("=" * 80)
            print(f"  Processed:           {processed:,}")
            print(f"  Scanned & saved:     {scanned_and_saved:,}")
            print(f"  Duplicates removed:  {duplicates_removed:,}")
            print(f"  Errors:              {errors:,}")
            print(f"  Remaining in CSV:    {final_count:,}")
            print("=" * 80)

        except Exception as e:
            logging.error(f"CSV scan error: {e}", exc_info=True)
        finally:
            self.running = False

    def dedupe_csv(self):
        """
        Fast CSV deduplication: Remove internal duplicates AND subreddits already in DB.

        No API calls, no rate limiting - just pure DB lookups.
        Perfect for pre-cleaning CSV files before scanning.
        """
        import csv
        from pathlib import Path

        csv_path = Path(self.csv_path)
        if not csv_path.exists():
            logging.error(f"CSV file not found: {self.csv_path}")
            return

        print("=" * 80)
        print(f"📄 Loading CSV: {csv_path}")
        print("=" * 80)

        # Load entire CSV into memory
        csv_rows = []
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('subreddit'):
                    csv_rows.append(row)

        initial_count = len(csv_rows)
        print(f"CSV contains: {initial_count:,} subreddits")
        print("=" * 80)
        print()

        # Step 1: Remove internal duplicates from CSV
        logging.info("🔍 Step 1: Removing internal CSV duplicates...")
        seen_subreddits = set()
        unique_rows = []
        internal_dupes = 0

        for row in csv_rows:
            subreddit = row['subreddit'].strip().lower()
            if subreddit not in seen_subreddits:
                seen_subreddits.add(subreddit)
                unique_rows.append(row)
            else:
                internal_dupes += 1

        print(f"   Internal duplicates found: {internal_dupes:,}")
        print(f"   Unique subreddits in CSV:  {len(unique_rows):,}")
        print()

        # Step 2: Check against database
        logging.info("🔍 Step 2: Checking database for duplicates...")
        print()

        db_duplicates = 0
        rows_to_keep = []

        for idx, row in enumerate(unique_rows):
            subreddit = row['subreddit'].strip().lower()

            # Quick DB lookup - no API call
            existing = self.db.conn.execute(
                "SELECT name FROM subreddits WHERE name = ?",
                (subreddit,)
            ).fetchone()

            if existing:
                db_duplicates += 1
                if db_duplicates % 100 == 0:
                    print(f"   Progress: {idx + 1:,}/{len(unique_rows):,} checked | DB duplicates: {db_duplicates:,}")
            else:
                # Not in DB - keep this row
                rows_to_keep.append(row)

        # Write cleaned CSV
        print()
        print("=" * 80)
        print("💾 Writing cleaned CSV...")

        with open(csv_path, 'w', newline='') as f:
            if rows_to_keep:
                writer = csv.DictWriter(f, fieldnames=['subreddit', 'subscribers', 'retry_count'], extrasaction='ignore')
                writer.writeheader()
                for row in rows_to_keep:
                    # Ensure retry_count exists
                    if 'retry_count' not in row:
                        row['retry_count'] = 0
                    writer.writerow(row)
            else:
                # Empty CSV - write just header
                writer = csv.DictWriter(f, fieldnames=['subreddit', 'subscribers', 'retry_count'])
                writer.writeheader()

        final_count = len(rows_to_keep)
        total_removed = initial_count - final_count

        print(f"✓ CSV cleaned:")
        print(f"  Started with:           {initial_count:,} subreddits")
        print(f"  Internal duplicates:    {internal_dupes:,} (removed)")
        print(f"  Already in DB:          {db_duplicates:,} (removed)")
        print(f"  Total removed:          {total_removed:,}")
        print(f"  Remaining in CSV:       {final_count:,}")
        print("=" * 80)
        print()

        if final_count == 0:
            logging.info("✅ All subreddits already in database!")
        else:
            logging.info(f"✅ {final_count:,} new subreddits ready to scan")

    async def shutdown(self):
        """Shutdown scanner and cleanup resources."""
        logging.debug("Shutting down scanner...")

        await self.reddit_client.close()
        self.db.close()

        logging.debug("Scanner shutdown complete")
