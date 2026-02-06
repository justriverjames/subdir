import sqlite3
import time
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


async def sync_databases(pg_db, sqlite_path: str, min_subscribers: int = 5000,
                         direction: str = 'both'):
    """
    Bidirectional sync between archiver PostgreSQL and scanner SQLite.
    Per-subreddit, whichever DB has the newer timestamp wins.

    direction: 'both', 'sqlite-to-pg', 'pg-to-sqlite'
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("DATABASE SYNC")
    logger.info("=" * 60)
    logger.info(f"Scanner DB: {sqlite_path}")
    logger.info(f"Direction: {direction}")
    logger.info(f"Min subscribers: {min_subscribers:,}")
    logger.info("")

    if not Path(sqlite_path).exists():
        logger.error(f"Scanner database not found: {sqlite_path}")
        return

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row

    stats = {'sqlite_to_pg': 0, 'pg_to_sqlite': 0, 'skipped': 0}

    try:
        if direction in ('both', 'sqlite-to-pg'):
            _sync_sqlite_to_pg(sqlite_conn, pg_db, min_subscribers, stats)

        if direction in ('both', 'pg-to-sqlite'):
            _sync_pg_to_sqlite(sqlite_conn, pg_db, min_subscribers, stats)

    finally:
        sqlite_conn.close()

    logger.info("")
    logger.info("=" * 60)
    logger.info("SYNC COMPLETE")
    logger.info("=" * 60)
    logger.info(f"SQLite → PG: {stats['sqlite_to_pg']:,}")
    logger.info(f"PG → SQLite: {stats['pg_to_sqlite']:,}")
    logger.info(f"Skipped: {stats['skipped']:,}")


def _sync_sqlite_to_pg(sqlite_conn, pg_db, min_subscribers: int, stats: Dict):
    """Import/update subreddits from scanner SQLite into archiver PG"""
    logger.info("Phase 1: SQLite → PostgreSQL")

    cursor = sqlite_conn.cursor()
    cursor.execute(
        """
        SELECT name, subscribers, active_users, over_18, status,
               icon_url, primary_color, title, description, last_updated
        FROM subreddits
        WHERE is_accessible = 1
            AND status = 'active'
            AND subscribers >= ?
        ORDER BY subscribers DESC
        """,
        (min_subscribers,)
    )

    rows = cursor.fetchall()
    logger.info(f"  Found {len(rows):,} eligible subreddits in SQLite")

    for row in rows:
        name = row['name']
        sqlite_updated = row['last_updated'] or 0

        # Check PG state
        pg_sub = _get_pg_subreddit(pg_db, name)

        if pg_sub is None:
            # New to PG — insert
            priority = _calc_priority(row['subscribers'] or 0)
            pg_db.add_subreddit(name, priority)
            stats['sqlite_to_pg'] += 1

        elif (pg_sub.get('last_metadata_update') or 0) < sqlite_updated:
            # SQLite is newer — update PG metadata
            _update_pg_from_sqlite(pg_db, name, row)
            stats['sqlite_to_pg'] += 1

        else:
            stats['skipped'] += 1

        if (stats['sqlite_to_pg'] + stats['skipped']) % 500 == 0:
            logger.info(f"  Progress: {stats['sqlite_to_pg']:,} synced, {stats['skipped']:,} skipped")

    logger.info(f"  Done: {stats['sqlite_to_pg']:,} imported/updated")


def _sync_pg_to_sqlite(sqlite_conn, pg_db, min_subscribers: int, stats: Dict):
    """Update scanner SQLite with newer metadata from archiver PG"""
    logger.info("Phase 2: PostgreSQL → SQLite")

    # Get all active subs from PG
    from psycopg2.extras import RealDictCursor
    with pg_db.get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT name, subscribers, active_users, over_18, status,
                       icon_url, primary_color, title, public_description,
                       last_metadata_update
                FROM subreddits
                WHERE status = 'active'
                    AND subscribers >= %s
                    AND last_metadata_update IS NOT NULL
                ORDER BY subscribers DESC
                """,
                (min_subscribers,)
            )
            pg_rows = cur.fetchall()

    logger.info(f"  Found {len(pg_rows):,} active subreddits in PG")

    sqlite_cursor = sqlite_conn.cursor()
    updated = 0

    for pg_row in pg_rows:
        name = pg_row['name']
        pg_updated = pg_row['last_metadata_update'] or 0

        # Check SQLite state
        sqlite_cursor.execute(
            "SELECT name, last_updated FROM subreddits WHERE name = ?",
            (name,)
        )
        sqlite_row = sqlite_cursor.fetchone()

        if sqlite_row is None:
            # New to SQLite — insert
            sqlite_cursor.execute(
                """
                INSERT INTO subreddits (
                    name, title, description, subscribers, active_users,
                    over_18, icon_url, primary_color, status, is_accessible,
                    last_updated, metadata_collected
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', 1, ?, 1)
                """,
                (
                    name,
                    pg_row.get('title'),
                    pg_row.get('public_description'),
                    pg_row.get('subscribers'),
                    pg_row.get('active_users'),
                    pg_row.get('over_18', False),
                    pg_row.get('icon_url'),
                    pg_row.get('primary_color'),
                    pg_updated
                )
            )
            updated += 1

        elif (sqlite_row['last_updated'] or 0) < pg_updated:
            # PG is newer — update SQLite
            sqlite_cursor.execute(
                """
                UPDATE subreddits
                SET title = ?,
                    description = ?,
                    subscribers = ?,
                    active_users = ?,
                    over_18 = ?,
                    icon_url = ?,
                    primary_color = ?,
                    last_updated = ?,
                    metadata_collected = 1
                WHERE name = ?
                """,
                (
                    pg_row.get('title'),
                    pg_row.get('public_description'),
                    pg_row.get('subscribers'),
                    pg_row.get('active_users'),
                    pg_row.get('over_18', False),
                    pg_row.get('icon_url'),
                    pg_row.get('primary_color'),
                    pg_updated,
                    name
                )
            )
            updated += 1

    sqlite_conn.commit()
    stats['pg_to_sqlite'] = updated
    logger.info(f"  Done: {updated:,} updated in SQLite")


def _get_pg_subreddit(pg_db, name: str) -> dict:
    """Fetch a single subreddit from PG"""
    from psycopg2.extras import RealDictCursor
    with pg_db.get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                "SELECT name, last_metadata_update FROM subreddits WHERE name = %s",
                (name,)
            )
            row = cur.fetchone()
            return dict(row) if row else None


def _update_pg_from_sqlite(pg_db, name: str, sqlite_row):
    """Update PG subreddit metadata from SQLite row"""
    with pg_db.get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE subreddits
                SET subscribers = %s,
                    active_users = %s,
                    over_18 = %s,
                    icon_url = %s,
                    primary_color = %s,
                    title = %s,
                    public_description = %s,
                    last_metadata_update = %s
                WHERE name = %s
                """,
                (
                    sqlite_row['subscribers'],
                    sqlite_row['active_users'],
                    bool(sqlite_row['over_18']),
                    sqlite_row['icon_url'],
                    sqlite_row['primary_color'],
                    sqlite_row['title'],
                    sqlite_row['description'],
                    sqlite_row['last_updated'],
                    name
                )
            )


def _calc_priority(subscribers: int) -> int:
    if subscribers >= 1_000_000:
        return 1
    elif subscribers >= 500_000:
        return 2
    elif subscribers >= 100_000:
        return 3
    elif subscribers >= 10_000:
        return 4
    return 5
