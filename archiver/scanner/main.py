import asyncio
import logging
import logging.handlers
import os
import sys
import argparse
from pathlib import Path

from config import ArchiverConfig
from database import Database
from reddit_client import RedditAPIClient
from global_rate_limiter import GlobalRateLimiter, TaskType
from rate_limiter import AntiDetection
from processors.metadata import MetadataProcessor
from processors.posts import PostsProcessor
from processors.comments import CommentsProcessor
from workers.metadata_worker import MetadataWorker
from workers.threads_worker import ThreadsWorker
from workers.comments_worker import CommentsWorker


def setup_logging(level: str = 'INFO', log_dir: str = '/app/logs'):
    root = logging.getLogger()
    root.setLevel(getattr(logging, level))

    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    root.addHandler(console)

    # File (with rotation)
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path / 'archiver.log',
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)


logger = logging.getLogger(__name__)


class ArchiverOrchestrator:
    """
    Manages three independent workers sharing a global rate limit pool:
      - metadata: subreddit discovery (CSV) and stale refresh
      - threads: posts + media URL archival
      - comments: comment backfill
    Any combination can run simultaneously.
    """

    def __init__(self, config: ArchiverConfig):
        self.config = config
        self.db = None
        self.reddit = None
        self.rate_limiter = None
        self.anti_detection = None

        self.metadata_worker = None
        self.threads_worker = None
        self.comments_worker = None

        # Active asyncio tasks (for WebUI control)
        self._worker_tasks: dict[str, asyncio.Task] = {}

    async def initialize(self):
        logger.info("Initializing SubDir Archiver")
        logger.info("=" * 60)

        self.db = Database(self.config)
        self.db.connect()

        if not self.db.test_connection():
            raise Exception("Database connection failed")
        logger.info("Database connected")

        # Shared rate limiter
        self.rate_limiter = GlobalRateLimiter(self.config)
        self.anti_detection = AntiDetection(self.config)

        # Shared Reddit API client
        self.reddit = RedditAPIClient(self.config, self.rate_limiter)
        await self.reddit.__aenter__()
        logger.info("Reddit API authenticated")

        # Processors (shared by workers)
        metadata_proc = MetadataProcessor(self.reddit, self.db)
        posts_proc = PostsProcessor(self.reddit, self.db, self.config)
        comments_proc = CommentsProcessor(self.reddit, self.db, self.config)

        # Workers
        self.metadata_worker = MetadataWorker(
            self.config, self.db, self.reddit, self.rate_limiter,
            metadata_proc, self.anti_detection
        )
        self.threads_worker = ThreadsWorker(
            self.config, self.db, self.reddit, self.rate_limiter,
            self.anti_detection, metadata_proc, posts_proc
        )
        self.comments_worker = CommentsWorker(
            self.config, self.db, self.reddit, self.rate_limiter,
            self.anti_detection, comments_proc
        )

        # Log active workers
        active = []
        if self.config.metadata_enabled:
            active.append('metadata')
        if self.config.threads_enabled:
            active.append('threads')
        if self.config.comments_enabled:
            active.append('comments')
        logger.info(f"Workers: {', '.join(active) or 'none'}")
        logger.info("Ready")
        logger.info("")

    async def shutdown(self):
        logger.info("")
        logger.info("Shutting down")

        await self.stop_workers()

        if self.reddit:
            await self.reddit.__aexit__(None, None, None)
        if self.db:
            self.db.close()

        if self.rate_limiter:
            stats = self.rate_limiter.get_stats()
            logger.info(f"Total requests: {stats['total_requests']}")
            logger.info(f"Total wait time: {stats['total_wait_time']:.1f}s")

        if self.anti_detection:
            anti_stats = self.anti_detection.get_stats()
            logger.info(f"Breaks taken: {anti_stats['break_count']}")
        logger.info("Done")

    # --- WebUI-callable methods ---

    async def start_workers(self, metadata: bool = None, threads: bool = None,
                            comments: bool = None, limit: int = 50):
        """Spawn worker asyncio tasks. Returns immediately (non-blocking)."""
        if self.is_running:
            logger.warning("Workers already running")
            return

        # Read enabled flags from DB if not overridden
        if metadata is None or threads is None or comments is None:
            db_flags = self.db.get_worker_enabled_states()
            if metadata is None:
                metadata = db_flags['metadata']
            if threads is None:
                threads = db_flags['threads']
            if comments is None:
                comments = db_flags['comments']

        if metadata:
            self._worker_tasks['metadata'] = asyncio.create_task(
                self._run_worker(self.metadata_worker, 'metadata'),
                name='metadata'
            )
        if threads:
            self._worker_tasks['threads'] = asyncio.create_task(
                self._run_worker(self.threads_worker, 'threads', limit=limit),
                name='threads'
            )
        if comments:
            self._worker_tasks['comments'] = asyncio.create_task(
                self._run_worker(self.comments_worker, 'comments'),
                name='comments'
            )

        started = list(self._worker_tasks.keys())
        if started:
            logger.info(f"Started workers: {started}")
        else:
            logger.warning("No workers enabled")

    async def _run_worker(self, worker, name: str, **kwargs):
        """Wrapper that catches exceptions so one crash doesn't kill others."""
        try:
            await worker.run(**kwargs)
        except asyncio.CancelledError:
            logger.info(f"Worker {name} cancelled")
        except Exception as e:
            logger.error(f"Worker {name} crashed: {e}", exc_info=True)
        finally:
            self._worker_tasks.pop(name, None)

    async def stop_workers(self):
        """Stop all running workers gracefully."""
        if not self._worker_tasks:
            return

        # Signal workers to stop
        for name in list(self._worker_tasks.keys()):
            worker = self._get_worker(name)
            if worker:
                worker.stop()

        # Cancel tasks and wait
        for name, task in list(self._worker_tasks.items()):
            task.cancel()

        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks.values(), return_exceptions=True)
            self._worker_tasks.clear()

        logger.info("All workers stopped")

    async def start_single_worker(self, worker_type: str, limit: int = 50):
        """Start a single worker if not already running."""
        if worker_type in self._worker_tasks:
            return  # already running

        worker = self._get_worker(worker_type)
        if not worker:
            return

        kwargs = {'limit': limit} if worker_type == 'threads' else {}
        self._worker_tasks[worker_type] = asyncio.create_task(
            self._run_worker(worker, worker_type, **kwargs),
            name=worker_type
        )
        logger.info(f"Started worker: {worker_type}")

    async def stop_single_worker(self, worker_type: str):
        """Stop a single worker."""
        task = self._worker_tasks.get(worker_type)
        if not task:
            return

        worker = self._get_worker(worker_type)
        if worker:
            worker.stop()

        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
        self._worker_tasks.pop(worker_type, None)
        logger.info(f"Stopped worker: {worker_type}")

    def _get_worker(self, name: str):
        return {
            'metadata': self.metadata_worker,
            'threads': self.threads_worker,
            'comments': self.comments_worker,
        }.get(name)

    @property
    def is_running(self) -> bool:
        return any(not t.done() for t in self._worker_tasks.values())

    def get_worker_status(self) -> dict:
        status = {}
        for name in ('metadata', 'threads', 'comments'):
            task = self._worker_tasks.get(name)
            worker = self._get_worker(name)
            running = task is not None and not task.done()
            info = {'running': running}

            if worker and running:
                if name == 'metadata':
                    info['discovered'] = worker.discovered
                    info['refreshed'] = worker.refreshed
                    info['skipped'] = worker.skipped
                elif name == 'threads':
                    info['processed'] = worker.processed
                    info['failed'] = worker.failed
                elif name == 'comments':
                    info['total_comments'] = worker.total_comments
                    info['batches_done'] = worker.batches_done

            status[name] = info
        return status

    # --- CLI methods (unchanged) ---

    async def run(self, limit: int = 50,
                  metadata: bool = None, threads: bool = None, comments: bool = None):
        """Start enabled workers concurrently. Blocks until done. For CLI use."""
        run_metadata = metadata if metadata is not None else self.config.metadata_enabled
        run_threads = threads if threads is not None else self.config.threads_enabled
        run_comments = comments if comments is not None else self.config.comments_enabled

        tasks = []

        if run_metadata:
            tasks.append(asyncio.create_task(
                self.metadata_worker.run(), name='metadata'
            ))
        if run_threads:
            tasks.append(asyncio.create_task(
                self.threads_worker.run(limit=limit), name='threads'
            ))
        if run_comments:
            tasks.append(asyncio.create_task(
                self.comments_worker.run(), name='comments'
            ))

        if not tasks:
            logger.warning("No workers enabled. Use --metadata, --threads, or --comments")
            return

        logger.info(f"Starting {len(tasks)} worker(s): {[t.get_name() for t in tasks]}")

        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)

        for task in done:
            if task.exception():
                logger.error(f"Worker {task.get_name()} crashed: {task.exception()}")
                for p in pending:
                    p.cancel()

        if pending:
            await asyncio.wait(pending, timeout=10)

        stats = self.db.get_stats()
        logger.info("Database Stats:")
        for key, value in stats.items():
            logger.info(f"  {key}: {value:,}")

    async def sync_from_scanner(self, sqlite_path: str, min_subscribers: int = 5000,
                                direction: str = 'both'):
        from sync import sync_databases
        await sync_databases(self.db, sqlite_path, min_subscribers, direction)

    async def import_csv(self, csv_path: str):
        import csv as csv_mod

        logger.info("")
        logger.info("=" * 60)
        logger.info("IMPORT SUBREDDITS FROM CSV")
        logger.info("=" * 60)
        logger.info(f"CSV: {csv_path}")
        logger.info("")

        if not Path(csv_path).exists():
            logger.error(f"CSV not found: {csv_path}")
            return

        added = 0
        skipped = 0

        with open(csv_path, 'r') as f:
            reader = csv_mod.DictReader(f)
            for row in reader:
                name = row['subreddit']
                priority = int(row['priority'])

                if self.db.add_subreddit(name, priority):
                    added += 1
                else:
                    skipped += 1

                if (added + skipped) % 50 == 0:
                    logger.info(f"Progress: {added:,} added, {skipped:,} skipped")

        logger.info(f"Import done: {added:,} added, {skipped:,} skipped")


async def main():
    parser = argparse.ArgumentParser(description='SubDir Archiver')
    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Run command
    run_parser = subparsers.add_parser('run', help='Run archiver workers')
    run_parser.add_argument('--limit', type=int, default=50, help='Threads batch size')
    run_parser.add_argument('--metadata', action='store_true', help='Enable metadata worker')
    run_parser.add_argument('--threads', action='store_true', help='Enable threads worker')
    run_parser.add_argument('--comments', action='store_true', help='Enable comments worker')
    run_parser.add_argument('--no-metadata', action='store_true', help='Disable metadata worker')
    run_parser.add_argument('--no-threads', action='store_true', help='Disable threads worker')
    run_parser.add_argument('--no-comments', action='store_true', help='Disable comments worker')

    # Sync command
    sync_parser = subparsers.add_parser('sync', help='Sync with scanner SQLite database')
    sync_parser.add_argument('--scanner-db', required=True, help='Path to scanner SQLite database')
    sync_parser.add_argument('--min-subscribers', type=int, default=5000)
    sync_parser.add_argument('--direction', choices=['both', 'pg-to-sqlite', 'sqlite-to-pg'],
                             default='both')

    # Import CSV command
    import_parser = subparsers.add_parser('import-csv', help='Import from priority CSV')
    import_parser.add_argument('csv_file', help='Path to CSV file')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        config = ArchiverConfig.from_env()
        config.validate()
    except Exception as e:
        print(f"Config error: {e}")
        sys.exit(1)

    setup_logging(config.log_level)

    orchestrator = ArchiverOrchestrator(config)

    try:
        await orchestrator.initialize()

        # Run migrations
        migrations_dir = Path(__file__).parent.parent / 'migrations'
        for migration in sorted(migrations_dir.glob('*.sql')):
            logger.info(f"Running migration: {migration.name}")
            orchestrator.db.run_migration(str(migration))
        logger.info("Migrations complete")
        logger.info("")

        if args.command == 'run':
            has_explicit = args.metadata or args.threads or args.comments
            has_disable = args.no_metadata or args.no_threads or args.no_comments

            if has_explicit:
                meta = args.metadata
                thrd = args.threads
                cmnt = args.comments
            elif has_disable:
                meta = not args.no_metadata and config.metadata_enabled
                thrd = not args.no_threads and config.threads_enabled
                cmnt = not args.no_comments and config.comments_enabled
            else:
                meta = None
                thrd = None
                cmnt = None

            stats = orchestrator.db.get_stats()
            logger.info("Initial Stats:")
            for key, value in stats.items():
                logger.info(f"  {key}: {value:,}")
            logger.info("")

            await orchestrator.run(
                limit=args.limit,
                metadata=meta,
                threads=thrd,
                comments=cmnt
            )

        elif args.command == 'sync':
            await orchestrator.sync_from_scanner(
                args.scanner_db, args.min_subscribers, args.direction
            )

        elif args.command == 'import-csv':
            await orchestrator.import_csv(args.csv_file)

    except KeyboardInterrupt:
        logger.info("Interrupted")
    except Exception as e:
        logger.error(f"Fatal: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await orchestrator.shutdown()


if __name__ == '__main__':
    asyncio.run(main())
