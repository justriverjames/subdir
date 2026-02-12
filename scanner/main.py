"""
Main entry point for subreddit scanner CLI.
"""

import asyncio
import logging
import sys
from pathlib import Path
from datetime import datetime
from argparse import ArgumentParser, RawDescriptionHelpFormatter

# Local imports (works when run directly as python main.py)
from config import Config
from scanner import SubredditScanner


def setup_logging(log_dir: str, log_level: str):
    """
    Setup logging configuration.

    Args:
        log_dir: Directory for log files
        log_level: Logging level
    """
    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Create log filename with timestamp
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    log_file = log_path / f"scanner_{timestamp}.log"

    # Configure logging
    file_format = '[%(asctime)s] [%(levelname)s] %(message)s'
    console_format = '%(message)s'  # Cleaner console output
    date_format = '%Y-%m-%d %H:%M:%S'

    # File handler - detailed logging for debugging
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(logging.Formatter(file_format, date_format))
    file_handler.setLevel(logging.DEBUG)

    # Console handler - clean output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter(console_format))
    console_handler.setLevel(getattr(logging, log_level.upper()))

    # Root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Capture everything
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Suppress verbose third-party library logs in console
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)

    print(f"📁 Logging to: {log_file}")
    print()


def create_parser() -> ArgumentParser:
    """
    Create argument parser.

    Returns:
        ArgumentParser instance
    """
    parser = ArgumentParser(
        description='Subreddit Scanner - Metadata and Thread ID Collection Tool',
        formatter_class=RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # DEDUPE CSV: Remove subreddits already in DB (fast, no API calls)
  python main.py --dedupe-csv --csv ../data/all_subreddits_2025.csv

  # SCAN subreddits from CSV (atomic: fetch + save + remove from CSV)
  python main.py --scan-csv --csv ../data/subreddits_to_scan.csv --limit 100

  # UPDATE metadata for existing subreddits (refresh data)
  python main.py --update --limit 100

  # RECOMMENDED WORKFLOW:
  # 1. Fast dedupe CSV first (removes existing subs from CSV instantly)
  python main.py --dedupe-csv --csv ../data/all_subreddits_2025.csv

  # 2. Scan remaining new subreddits (processes & removes from CSV as you go)
  python main.py --scan-csv --csv ../data/all_subreddits_2025.csv --limit 1000

  # 3. Update existing subreddits periodically (keeps data fresh)
  python main.py --update --limit 1000

  # Maintenance: Compact database and reclaim space
  python main.py --vacuum

  # Show database statistics
  python main.py --stats

Alternative (from parent directory):
  python -m subreddit_scanner --ingest
  python -m subreddit_scanner --metadata
  python -m subreddit_scanner --threads
  python -m subreddit_scanner --vacuum

Environment variables:
  REDDIT_CLIENT_ID       - Reddit API client ID (required)
  REDDIT_CLIENT_SECRET   - Reddit API client secret (required)
  REDDIT_USERNAME        - Reddit username (required)
  REDDIT_PASSWORD        - Reddit password (required)
  SCANNER_DB_PATH        - Database path (default: subreddit_scanner.db)
  SCANNER_LOG_DIR        - Log directory (default: logs)
  LOG_LEVEL              - Logging level (default: INFO)
        """
    )

    # Mode selection (mutually exclusive)
    mode_group = parser.add_mutually_exclusive_group(required=True)

    mode_group.add_argument(
        '--scan-csv',
        action='store_true',
        help='SCAN subreddits from CSV (atomic: fetch + save + remove from CSV)'
    )

    mode_group.add_argument(
        '--update',
        action='store_true',
        help='UPDATE metadata for existing subreddits (refresh stale data)'
    )

    mode_group.add_argument(
        '--vacuum',
        action='store_true',
        help='Compact database and reclaim space (run after cleanup or migration)'
    )
    mode_group.add_argument(
        '--stats',
        action='store_true',
        help='Show database statistics and subreddits needing update'
    )

    mode_group.add_argument(
        '--dedupe-csv',
        action='store_true',
        help='Remove subreddits already in database from CSV (no API calls, fast)'
    )

    parser.add_argument(
        '--db',
        type=str,
        help='Database file path (default: subreddit_scanner.db)'
    )

    parser.add_argument(
        '--log-dir',
        type=str,
        help='Log directory (default: logs)'
    )

    parser.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        help='Logging level (default: INFO)'
    )

    # CSV file path
    parser.add_argument(
        '--csv',
        type=str,
        default='../data/subreddits_to_scan.csv',
        help='Path to CSV file (default: ../data/subreddits_to_scan.csv)'
    )

    # Batch limiting
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of subreddits to process (for testing or batching)'
    )

    # Filtering options
    parser.add_argument(
        '--nsfw-only',
        action='store_true',
        help='Only process NSFW (18+) subreddits'
    )

    # Rate limiting options
    parser.add_argument(
        '--rate-limit',
        type=int,
        help='Requests per minute (default: 60)'
    )

    parser.add_argument(
        '--cooldown',
        type=int,
        help='Cooldown between subreddits in seconds (default: 30)'
    )

    # Fetch options
    parser.add_argument(
        '--no-hot',
        action='store_true',
        help='Skip fetching hot posts'
    )

    parser.add_argument(
        '--no-top-all',
        action='store_true',
        help='Skip fetching top all-time posts'
    )

    parser.add_argument(
        '--no-top-year',
        action='store_true',
        help='Skip fetching top year posts'
    )

    # Environment file
    parser.add_argument(
        '--env-file',
        type=str,
        help='Path to .env file (default: auto-detect)'
    )

    return parser


async def main():
    """Main entry point."""
    parser = create_parser()
    args = parser.parse_args()

    try:
        # Load configuration
        config = Config.from_env(args.env_file)

        # Determine mode
        if args.scan_csv:
            mode = 'scan_csv'
        elif args.update:
            mode = 'update'
        elif args.vacuum:
            mode = 'vacuum'
        elif args.stats:
            mode = 'stats'
        elif args.dedupe_csv:
            mode = 'dedupe_csv'
        else:
            mode = None

        # Update from command line arguments
        config.update_from_args(
            db_path=args.db,
            log_dir=args.log_dir,
            log_level=args.log_level,
            mode=mode,
            rate_limit_per_minute=args.rate_limit,
            subreddit_cooldown=args.cooldown,
            fetch_hot=not args.no_hot,
            fetch_top_all=not args.no_top_all,
            fetch_top_year=not args.no_top_year,
        )

        # Validate configuration
        config.validate()

        # Setup logging
        setup_logging(config.log_dir, config.log_level)

        print("=" * 80)
        print("Subreddit Scanner v1.0.0")
        print("=" * 80)
        print()

        # Create scanner
        scanner = SubredditScanner(config)

        # Handle different modes
        if args.stats:
            # Stats mode: Show database statistics
            logging.info("="*60)
            logging.info("DATABASE STATISTICS")
            logging.info("="*60)

            # Get general stats
            stats = scanner.db.get_processing_stats()

            # Get update status
            update_stats = scanner.db.count_stale_subreddits(stale_days=30)

            logging.info("")
            logging.info("General:")
            logging.info(f"  Total subreddits:     {stats.get('total_subreddits', 0):>10,}")
            logging.info(f"  Active:               {stats.get('active', 0):>10,}")
            logging.info(f"  Private:              {stats.get('private', 0):>10,}")
            logging.info(f"  Banned/Deleted:       {stats.get('deleted', 0):>10,}")
            logging.info(f"  With metadata:        {stats.get('metadata_collected', 0):>10,}")
            logging.info("")
            logging.info("Update Status (30-day threshold):")
            logging.info(f"  Never updated:        {update_stats['never_updated']:>10,}")
            logging.info(f"  Stale (>30 days):     {update_stats['stale']:>10,}")
            logging.info(f"  Total needing update: {update_stats['total_needing_update']:>10,}")
            logging.info("="*60)

            # Exit after stats
            await scanner.shutdown()
            return 0

        elif args.vacuum:
            # Vacuum mode: Compact database
            logging.info("="*60)
            logging.info("VACUUM MODE: Compacting Database")
            logging.info("="*60)

            result = scanner.db.vacuum()

            logging.info("")
            logging.info("="*60)
            logging.info(f"Vacuum Results:")
            logging.info(f"  Size before: {result['size_before_mb']:.1f} MB")
            logging.info(f"  Size after:  {result['size_after_mb']:.1f} MB")
            logging.info(f"  Space saved: {result['saved_mb']:.1f} MB")
            logging.info("="*60)

            # Exit after vacuum
            await scanner.shutdown()
            return 0

        elif args.dedupe_csv:
            # Dedupe mode: Remove duplicates from CSV (no API calls)
            logging.info("="*60)
            logging.info("DEDUPE-CSV MODE: Remove duplicates from CSV")
            logging.info(f"CSV: {args.csv}")
            logging.info("="*60)

            # Pass CSV path to scanner
            scanner.csv_path = args.csv

            # Run dedupe (no initialization needed - just DB queries)
            scanner.dedupe_csv()

            # Exit after dedupe
            await scanner.shutdown()
            return 0

        elif args.scan_csv:
            # SCAN-CSV mode: Atomic processing (fetch + save + remove from CSV)
            logging.info("="*60)
            logging.info("SCAN-CSV MODE: Atomic Processing")
            if args.limit:
                logging.info(f"LIMIT: {args.limit} subreddits")
            logging.info(f"CSV: {args.csv}")
            logging.info("="*60)

            await scanner.initialize()

            # Pass limit and CSV path to scanner
            scanner.limit = args.limit
            scanner.csv_path = args.csv

            # Run CSV scanner
            await scanner.run_csv_scan()

            # Shutdown
            await scanner.shutdown()

            logging.info("CSV scanning complete")
            return 0

        elif args.update:
            # Update mode: Refresh existing subreddits
            await scanner.initialize()

            # Pass limit, mode, and filters to scanner
            scanner.limit = args.limit
            scanner.mode = mode
            scanner.nsfw_only = args.nsfw_only

            logging.info("="*60)
            logging.info(f"UPDATE MODE: Refresh existing subreddit metadata")
            if args.limit:
                logging.info(f"LIMIT: {args.limit} subreddits")
            if args.nsfw_only:
                logging.info(f"FILTER: NSFW subreddits only")
            logging.info("="*60)

            # Check if we have subreddits to process
            stats = scanner.db.get_processing_stats()
            if stats.get('total_subreddits', 0) == 0:
                logging.error("No subreddits in database!")
                logging.error("First scan subreddits with: python main.py --scan-csv --csv <file>")
                return 1

            # Run scanner
            await scanner.run()

            # Shutdown
            await scanner.shutdown()

            logging.info("Scanner finished successfully")
            return 0
        else:
            # This shouldn't happen due to mutually_exclusive_group(required=True)
            logging.error("No mode specified!")
            return 1

    except KeyboardInterrupt:
        logging.info("Interrupted by user")
        return 130

    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        return 1


def cli():
    """CLI entry point."""
    sys.exit(asyncio.run(main()))


if __name__ == '__main__':
    cli()
