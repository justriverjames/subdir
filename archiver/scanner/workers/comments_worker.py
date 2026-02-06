import asyncio
import time
import logging

from global_rate_limiter import GlobalRateLimiter, TaskType

logger = logging.getLogger(__name__)


class CommentsWorker:
    """
    Comment backfill worker.
    Fetches comments for posts in batches, spread across subreddits.
    """

    def __init__(self, config, db, reddit, rate_limiter: GlobalRateLimiter,
                 anti_detection, comments_processor):
        self.config = config
        self.db = db
        self.reddit = reddit
        self.rate_limiter = rate_limiter
        self.anti_detection = anti_detection
        self.comments_processor = comments_processor
        self.running = False

        self.total_comments = 0
        self.batches_done = 0

    async def run(self):
        """Main loop — continuously process comment batches"""
        self.running = True
        self.rate_limiter.register_worker(TaskType.COMMENTS)

        logger.info("CommentsWorker started")

        try:
            while self.running:
                # Check pause
                pause_remaining = self.db.check_pause()
                if pause_remaining:
                    logger.info(f"[comments] Paused for {pause_remaining}s")
                    await asyncio.sleep(pause_remaining)
                    continue

                count = await self._process_batch()
                if count == 0:
                    logger.info("[comments] No more comments to fetch")
                    break

                self.total_comments += count
                self.batches_done += 1

                # Cooldown between batches
                logger.info(f"[comments] Cooldown {self.config.comments_cooldown:.0f}s")
                await asyncio.sleep(self.config.comments_cooldown)

            logger.info(
                f"[comments] Done: {self.total_comments:,} comments "
                f"in {self.batches_done} batches"
            )

        finally:
            self.running = False
            self.rate_limiter.unregister_worker(TaskType.COMMENTS)

    async def _process_batch(self) -> int:
        """Process one batch of comments spread across subreddits"""
        batch_size = self.config.comments_batch_size

        posts = self.db.get_posts_for_comments_batch(
            limit=batch_size, spread_across_subs=True
        )

        if not posts:
            return 0

        subs = set(p['subreddit'] for p in posts)
        logger.info(f"[comments] Batch: {len(posts)} posts across {len(subs)} subs")

        comments_fetched = 0

        for i, post in enumerate(posts, 1):
            if not self.running:
                break

            subreddit = post['subreddit']
            post_id = post['id']

            logger.info(f"[comments] [{i}/{len(posts)}] r/{subreddit}: {post['title'][:50]}")

            self.db.update_processing_tier_status(subreddit, 'comments', 'processing')
            self.reddit.set_task_type(TaskType.COMMENTS)

            try:
                count = await self.comments_processor.process_post(
                    subreddit, post_id, post['title']
                )
                comments_fetched += count

                # Mark post as fetched so it doesn't get re-queued
                self.db.update_post_comment_status(post_id, 'completed', count)
                self.db.update_posts_pending_comments(subreddit)

                # Check if subreddit's comments are all done
                remaining = self.db.get_posts_for_comments(subreddit, limit=1)
                if not remaining:
                    self.db.mark_comments_complete(subreddit)
                    logger.info(f"[comments] r/{subreddit} complete")

            except Exception as e:
                logger.error(f"[comments] Error on post {post_id}: {e}")

            if i < len(posts):
                await self.anti_detection.random_delay(2.0, 5.0)

        self.db.update_processing_tier_activity('comments')
        self.db.increment_processing_tier_processed('comments', len(posts))

        logger.info(f"[comments] Batch done: {comments_fetched:,} comments")
        return comments_fetched

    def stop(self):
        self.running = False
