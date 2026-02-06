import asyncio
import csv
import random
import logging
import time
import tempfile
import shutil
from pathlib import Path
from typing import Optional

from global_rate_limiter import GlobalRateLimiter, TaskType

logger = logging.getLogger(__name__)


class MetadataWorker:
    """
    Subreddit discovery and metadata refresh worker.
    Two modes:
      1. CSV discovery — process rows from CSV, shrink as we go
      2. Stale refresh — re-check subs not updated in N days
    """

    def __init__(self, config, db, reddit, rate_limiter: GlobalRateLimiter,
                 metadata_processor, anti_detection):
        self.config = config
        self.db = db
        self.reddit = reddit
        self.rate_limiter = rate_limiter
        self.metadata_processor = metadata_processor
        self.anti_detection = anti_detection
        self.running = False

        self.discovered = 0
        self.refreshed = 0
        self.skipped = 0

    async def run(self):
        """Main loop — CSV first, then stale refresh"""
        self.running = True
        self.rate_limiter.register_worker(TaskType.METADATA)

        logger.info("MetadataWorker started")

        try:
            csv_path = self.config.csv_path
            if csv_path and Path(csv_path).exists():
                rows = self._count_csv_rows(csv_path)
                if rows > 0:
                    logger.info(f"[metadata] CSV discovery: {rows} rows remaining")
                    await self._process_csv(csv_path)

            # After CSV is done (or if no CSV), refresh stale subs
            if self.running:
                await self._refresh_stale()

            logger.info(
                f"[metadata] Done: {self.discovered} discovered, "
                f"{self.refreshed} refreshed, {self.skipped} skipped"
            )

        finally:
            self.running = False
            self.rate_limiter.unregister_worker(TaskType.METADATA)

    async def _process_csv(self, csv_path: str):
        """
        Process subreddits from CSV. Atomic per-row:
        check DB → fetch metadata → save to PG → remove from CSV.
        """
        logger.info(f"[metadata] Processing CSV: {csv_path}")

        while self.running:
            # Read remaining rows
            rows = self._read_csv(csv_path)
            if not rows:
                logger.info("[metadata] CSV fully processed")
                break

            # Sort by subscribers desc (bigger subs first)
            rows.sort(key=lambda r: int(r.get('subscribers', 0)), reverse=True)

            batch_processed = 0

            for row in rows:
                if not self.running:
                    break

                # Check pause
                pause_remaining = self.db.check_pause()
                if pause_remaining:
                    logger.info(f"[metadata] Paused for {pause_remaining}s")
                    await asyncio.sleep(pause_remaining)

                name = row.get('subreddit', '').strip().lower()
                if not name:
                    continue

                # Skip if already in DB
                existing = self._check_exists(name)
                if existing:
                    self.skipped += 1
                    batch_processed += 1
                    continue

                # Fetch metadata via Reddit API
                self.reddit.set_task_type(TaskType.METADATA)

                result = await self.reddit.get_subreddit_about(name)
                status = result['status']

                if status == 'active':
                    data = result['data']
                    subscribers = data.get('subscribers', 0)

                    # Skip small subs
                    if subscribers < self.config.min_subscribers:
                        self.skipped += 1
                        batch_processed += 1
                        continue

                    # Skip user profiles
                    sub_type = data.get('subreddit_type', '')
                    if sub_type == 'user' or name.startswith('u_'):
                        self.skipped += 1
                        batch_processed += 1
                        continue

                    # Add to PG
                    was_new = self.db.add_subreddit(name, priority=self._calc_priority(subscribers))
                    if was_new:
                        # Update metadata immediately
                        self.metadata_processor.db = self.db
                        self.db.update_subreddit_metadata(name, self.metadata_processor._parse_metadata(data))
                        self.discovered += 1
                        logger.info(f"[metadata] + r/{name} ({subscribers:,} subs)")

                elif status in ['notfound', 'deleted']:
                    logger.debug(f"[metadata] r/{name} — not found")

                elif status == 'private':
                    logger.debug(f"[metadata] r/{name} — private")

                else:
                    logger.debug(f"[metadata] r/{name} — {status}")

                batch_processed += 1

                # Remove processed row from CSV
                self._remove_from_csv(csv_path, name)

                # Delay between requests
                delay = random.uniform(1.0, 2.5)
                await asyncio.sleep(delay)

                if batch_processed % 50 == 0:
                    logger.info(
                        f"[metadata] CSV progress: {self.discovered} added, "
                        f"{self.skipped} skipped, {batch_processed} processed this batch"
                    )

            # If we processed the whole batch, CSV is done
            break

    async def _refresh_stale(self):
        """Re-check subreddits that haven't been updated in stale_threshold_days"""
        stale_days = self.config.stale_threshold_days
        logger.info(f"[metadata] Refreshing subs older than {stale_days} days")

        subs = self.db.get_subreddits_for_metadata_update(
            limit=200,
            stale_days=stale_days
        )

        if not subs:
            logger.info("[metadata] No stale subreddits to refresh")
            return

        logger.info(f"[metadata] {len(subs)} stale subs to refresh")

        for i, sub in enumerate(subs, 1):
            if not self.running:
                break

            pause_remaining = self.db.check_pause()
            if pause_remaining:
                await asyncio.sleep(pause_remaining)

            name = sub['name']
            self.reddit.set_task_type(TaskType.METADATA)

            success = await self.metadata_processor.process_subreddit(name)
            if success:
                self.refreshed += 1
            else:
                self.skipped += 1

            if i % 25 == 0:
                logger.info(f"[metadata] Refresh: {self.refreshed}/{i}")

            delay = random.uniform(1.5, 3.0)
            await asyncio.sleep(delay)

            await self.anti_detection.maybe_take_break()

    def _check_exists(self, name: str) -> bool:
        """Check if subreddit already exists in PG"""
        try:
            subs = self.db.get_subreddits_for_processing(limit=1, min_subscribers=0)
            # Quick existence check via direct query
            from psycopg2.extras import RealDictCursor
            with self.db.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1 FROM subreddits WHERE name = %s", (name,))
                    return cur.fetchone() is not None
        except Exception:
            return False

    def _calc_priority(self, subscribers: int) -> int:
        """Priority based on subscriber count"""
        if subscribers >= 1_000_000:
            return 1
        elif subscribers >= 500_000:
            return 2
        elif subscribers >= 100_000:
            return 3
        elif subscribers >= 10_000:
            return 4
        return 5

    def _count_csv_rows(self, path: str) -> int:
        try:
            with open(path, 'r') as f:
                reader = csv.DictReader(f)
                return sum(1 for _ in reader)
        except Exception:
            return 0

    def _read_csv(self, path: str) -> list:
        try:
            with open(path, 'r') as f:
                reader = csv.DictReader(f)
                return list(reader)
        except Exception:
            return []

    def _remove_from_csv(self, path: str, name: str):
        """Remove a processed row from CSV (atomic write via temp file)"""
        try:
            rows = []
            fieldnames = None

            with open(path, 'r') as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
                for row in reader:
                    if row.get('subreddit', '').strip().lower() != name:
                        rows.append(row)

            if fieldnames:
                tmp = path + '.tmp'
                with open(tmp, 'w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(rows)
                shutil.move(tmp, path)

        except Exception as e:
            logger.warning(f"[metadata] Failed to update CSV: {e}")

    def stop(self):
        self.running = False
