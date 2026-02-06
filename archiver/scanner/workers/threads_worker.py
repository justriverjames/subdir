import asyncio
import random
import logging

from global_rate_limiter import GlobalRateLimiter, TaskType

logger = logging.getLogger(__name__)


class ThreadsWorker:
    """
    Posts + media URL archiver.
    Fetches metadata, posts (top+hot), and extracts media URLs per subreddit.
    """

    def __init__(self, config, db, reddit, rate_limiter: GlobalRateLimiter,
                 anti_detection, metadata_processor, posts_processor):
        self.config = config
        self.db = db
        self.reddit = reddit
        self.rate_limiter = rate_limiter
        self.anti_detection = anti_detection
        self.metadata_processor = metadata_processor
        self.posts_processor = posts_processor
        self.running = False

        self.processed = 0
        self.failed = 0

    async def run(self, limit: int = 50):
        """Main loop — process subreddits for posts + media"""
        self.running = True
        self.rate_limiter.register_worker(TaskType.THREADS)
        self.reddit.set_task_type(TaskType.THREADS)

        logger.info("ThreadsWorker started")

        try:
            # Defer all comments for threads-only processing
            self.db.set_all_comments_deferred()

            subreddits = self.db.get_subreddits_for_posts(
                limit=limit,
                min_subscribers=self.config.min_subscribers
            )

            if not subreddits:
                logger.info("[threads] No subreddits need posts processing")
                return

            subreddits = self.anti_detection.shuffle_with_bias(subreddits, 'subscribers')
            logger.info(f"[threads] {len(subreddits)} subreddits queued")

            for i, sub in enumerate(subreddits, 1):
                if not self.running:
                    break

                # Check pause
                pause_remaining = self.db.check_pause()
                if pause_remaining:
                    logger.info(f"[threads] Paused for {pause_remaining}s")
                    await asyncio.sleep(pause_remaining)

                try:
                    logger.info(f"[threads] [{i}/{len(subreddits)}] r/{sub['name']}")
                    success = await self._process_subreddit(sub['name'])
                    if success:
                        self.processed += 1
                    else:
                        self.failed += 1

                    await self.anti_detection.maybe_take_break()

                    if i < len(subreddits):
                        pause = random.uniform(
                            self.config.subreddit_pause_min,
                            self.config.subreddit_pause_max
                        )
                        logger.info(f"[threads] Pausing {pause:.0f}s")
                        await asyncio.sleep(pause)

                except Exception as e:
                    logger.error(f"[threads] Error on r/{sub['name']}: {e}", exc_info=True)
                    self.failed += 1

            logger.info(f"[threads] Batch done: {self.processed} ok, {self.failed} failed")

        finally:
            self.running = False
            self.rate_limiter.unregister_worker(TaskType.THREADS)

    async def _process_subreddit(self, name: str) -> bool:
        """Metadata → Posts + Media for one subreddit"""
        self.db.update_processing_tier_status(name, 'posts', 'processing')

        # Phase 1: Metadata
        logger.info(f"[threads] r/{name} — fetching metadata")
        self.db.update_processing_state(name, 'metadata')

        success = await self.metadata_processor.process_subreddit(name)
        if not success:
            logger.warning(f"[threads] r/{name} — metadata failed, skipping")
            self.db.update_processing_tier_status(name, 'posts', 'error')
            return False

        # Phase 2: Posts + Media
        logger.info(f"[threads] r/{name} — fetching posts + media")
        self.db.update_processing_state(name, 'posts')

        posts_count, media_count = await self.posts_processor.process_subreddit(name)

        if posts_count == 0:
            logger.warning(f"[threads] r/{name} — no posts found")

        self.db.mark_posts_complete(name, set_comments_deferred=True)
        self.db.update_processing_tier_activity('posts')
        self.db.increment_processing_tier_processed('posts')

        logger.info(f"[threads] r/{name} done: {posts_count:,} posts, {media_count:,} media")
        return True

    def stop(self):
        self.running = False
