"""
Database module for subreddit metadata and thread ID storage using SQLite.
"""

import sqlite3
import logging
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


class Database:
    """SQLite database manager for subreddit scanning."""

    SCHEMA_VERSION = 2

    SCHEMA = """
    -- Unified subreddit metadata and processing state table
    CREATE TABLE IF NOT EXISTS subreddits (
        name TEXT PRIMARY KEY,
        -- Metadata from Reddit API
        title TEXT,
        description TEXT,
        public_description TEXT,
        subscribers INTEGER,
        active_users INTEGER,
        over_18 BOOLEAN,
        subreddit_type TEXT,  -- 'public', 'private', 'restricted', 'archived'
        created_utc INTEGER,
        -- Status and processing tracking
        status TEXT,  -- 'pending', 'active', 'private', 'banned', 'quarantined', 'deleted', 'error'
        last_updated INTEGER,
        last_checked INTEGER,
        retry_count INTEGER DEFAULT 0,
        error_message TEXT,
        metadata_collected BOOLEAN DEFAULT 0,
        threads_collected BOOLEAN DEFAULT 0
    );

    -- Simplified thread IDs table (no source or timestamp bloat)
    CREATE TABLE IF NOT EXISTS thread_ids (
        thread_id TEXT PRIMARY KEY,
        subreddit TEXT NOT NULL,
        FOREIGN KEY(subreddit) REFERENCES subreddits(name)
    );

    -- Schema version tracking
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY
    );

    -- Optimized indexes
    CREATE INDEX IF NOT EXISTS idx_thread_ids_subreddit ON thread_ids(subreddit);
    CREATE INDEX IF NOT EXISTS idx_subreddits_status ON subreddits(status);
    CREATE INDEX IF NOT EXISTS idx_subreddits_metadata_collected ON subreddits(metadata_collected);
    CREATE INDEX IF NOT EXISTS idx_subreddits_threads_collected ON subreddits(threads_collected);
    CREATE INDEX IF NOT EXISTS idx_subreddits_retry_count ON subreddits(retry_count);
    CREATE INDEX IF NOT EXISTS idx_subreddits_subscribers ON subreddits(subscribers DESC);
    """

    def __init__(self, db_path: str):
        """
        Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._initialize_schema()

    def _connect(self):
        """Establish database connection with optimizations."""
        self.conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            isolation_level=None  # Autocommit mode
        )
        self.conn.row_factory = sqlite3.Row  # Enable column access by name

        # Enable WAL mode for better concurrency
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-64000")  # 64MB cache

        logging.debug(f"Database connected: {self.db_path}")

    def _initialize_schema(self):
        """Create database schema if it doesn't exist."""
        cursor = self.conn.cursor()

        # Check if schema_version table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
        if not cursor.fetchone():
            # Fresh database - create schema
            cursor.executescript(self.SCHEMA)
            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,))
            self.conn.commit()
            logging.info(f"Initialized fresh database with schema version {self.SCHEMA_VERSION}")
            return

        # Check schema version
        cursor.execute("SELECT version FROM schema_version LIMIT 1")
        result = cursor.fetchone()

        if not result:
            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (self.SCHEMA_VERSION,))
            current_version = self.SCHEMA_VERSION
        else:
            current_version = result[0]

        # Handle migrations
        if current_version < self.SCHEMA_VERSION:
            logging.info(f"Migrating database from version {current_version} to {self.SCHEMA_VERSION}...")

            if current_version == 1:
                self._migrate_v1_to_v2()
                current_version = 2

            # Update version
            cursor.execute("UPDATE schema_version SET version = ?", (current_version,))
            self.conn.commit()
            logging.info(f"✓ Database migration complete: now at version {current_version}")
        elif current_version > self.SCHEMA_VERSION:
            raise ValueError(
                f"Database schema version {current_version} is newer than code version {self.SCHEMA_VERSION}. "
                f"Please update the scanner code."
            )

    def _migrate_v1_to_v2(self):
        """Migrate from schema v1 to v2: merge processing_state into subreddits, simplify thread_ids."""
        cursor = self.conn.cursor()
        logging.info("Starting v1→v2 migration...")

        try:
            # 1. Create new tables with temporary names
            cursor.executescript("""
                CREATE TABLE subreddits_v2 (
                    name TEXT PRIMARY KEY,
                    title TEXT,
                    description TEXT,
                    public_description TEXT,
                    subscribers INTEGER,
                    active_users INTEGER,
                    over_18 BOOLEAN,
                    subreddit_type TEXT,
                    created_utc INTEGER,
                    status TEXT,
                    last_updated INTEGER,
                    last_checked INTEGER,
                    retry_count INTEGER DEFAULT 0,
                    error_message TEXT,
                    metadata_collected BOOLEAN DEFAULT 0,
                    threads_collected BOOLEAN DEFAULT 0
                );

                CREATE TABLE thread_ids_v2 (
                    thread_id TEXT PRIMARY KEY,
                    subreddit TEXT NOT NULL,
                    FOREIGN KEY(subreddit) REFERENCES subreddits_v2(name)
                );
            """)

            # 2. Check if processing_state table exists (might not if this is a fresh v1 install)
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='processing_state'")
            has_processing_state = cursor.fetchone() is not None

            # 3. Migrate data (merge processing_state into subreddits if it exists)
            if has_processing_state:
                # Check if metadata_collected and threads_collected columns exist in processing_state
                cursor.execute("PRAGMA table_info(processing_state)")
                ps_columns = [row[1] for row in cursor.fetchall()]
                has_metadata_col = 'metadata_collected' in ps_columns
                has_threads_col = 'threads_collected' in ps_columns

                if has_metadata_col and has_threads_col:
                    cursor.execute("""
                        INSERT INTO subreddits_v2
                        SELECT
                            s.name,
                            s.title,
                            s.description,
                            s.public_description,
                            s.subscribers,
                            s.active_users,
                            s.over_18,
                            s.subreddit_type,
                            s.created_utc,
                            COALESCE(p.status, s.status, 'pending') as status,
                            s.last_updated,
                            s.last_checked,
                            COALESCE(p.retry_count, 0) as retry_count,
                            COALESCE(p.error_message, s.error_message) as error_message,
                            COALESCE(p.metadata_collected, 0) as metadata_collected,
                            COALESCE(p.threads_collected, 0) as threads_collected
                        FROM subreddits s
                        LEFT JOIN processing_state p ON s.name = p.subreddit
                    """)
                else:
                    # Old v1 without metadata_collected columns
                    cursor.execute("""
                        INSERT INTO subreddits_v2
                        SELECT
                            s.name,
                            s.title,
                            s.description,
                            s.public_description,
                            s.subscribers,
                            s.active_users,
                            s.over_18,
                            s.subreddit_type,
                            s.created_utc,
                            COALESCE(p.status, s.status, 'pending') as status,
                            s.last_updated,
                            s.last_checked,
                            COALESCE(p.retry_count, 0) as retry_count,
                            COALESCE(p.error_message, s.error_message) as error_message,
                            CASE WHEN p.status = 'completed' THEN 1 ELSE 0 END as metadata_collected,
                            CASE WHEN p.status = 'completed' THEN 1 ELSE 0 END as threads_collected
                        FROM subreddits s
                        LEFT JOIN processing_state p ON s.name = p.subreddit
                    """)
            else:
                # No processing_state table - just copy subreddits
                cursor.execute("""
                    INSERT INTO subreddits_v2
                    SELECT
                        name,
                        title,
                        description,
                        public_description,
                        subscribers,
                        active_users,
                        over_18,
                        subreddit_type,
                        created_utc,
                        COALESCE(status, 'pending') as status,
                        last_updated,
                        last_checked,
                        0 as retry_count,
                        error_message,
                        0 as metadata_collected,
                        0 as threads_collected
                    FROM subreddits
                """)

            # 4. Migrate thread_ids (drop source and discovered_at columns)
            cursor.execute("""
                INSERT INTO thread_ids_v2 (thread_id, subreddit)
                SELECT DISTINCT thread_id, subreddit
                FROM thread_ids
            """)

            # 5. Drop old tables
            cursor.execute("DROP TABLE IF EXISTS processing_state")
            cursor.execute("DROP INDEX IF EXISTS idx_processing_state_status")
            cursor.execute("DROP INDEX IF EXISTS idx_thread_ids_source")
            cursor.execute("DROP INDEX IF EXISTS idx_subreddits_last_checked")
            cursor.execute("DROP TABLE thread_ids")
            cursor.execute("DROP TABLE subreddits")

            # 6. Rename new tables
            cursor.execute("ALTER TABLE subreddits_v2 RENAME TO subreddits")
            cursor.execute("ALTER TABLE thread_ids_v2 RENAME TO thread_ids")

            # 7. Create indexes
            cursor.executescript("""
                CREATE INDEX idx_thread_ids_subreddit ON thread_ids(subreddit);
                CREATE INDEX idx_subreddits_status ON subreddits(status);
                CREATE INDEX idx_subreddits_metadata_collected ON subreddits(metadata_collected);
                CREATE INDEX idx_subreddits_threads_collected ON subreddits(threads_collected);
                CREATE INDEX idx_subreddits_retry_count ON subreddits(retry_count);
                CREATE INDEX idx_subreddits_subscribers ON subreddits(subscribers DESC);
            """)

            self.conn.commit()
            logging.info("✓ Schema v1→v2 migration complete")

            # Compact database to reclaim space from dropped tables
            logging.info("Compacting database (VACUUM)...")
            cursor.execute("VACUUM")
            logging.info("✓ Database compacted")

        except Exception as e:
            self.conn.rollback()
            logging.error(f"Migration failed: {e}")
            raise

    @contextmanager
    def transaction(self):
        """Context manager for transactions."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("BEGIN")
            yield cursor
            cursor.execute("COMMIT")
        except Exception as e:
            cursor.execute("ROLLBACK")
            raise e

    def add_subreddit(self, name: str) -> bool:
        """
        Add a subreddit to the database.

        Args:
            name: Subreddit name

        Returns:
            True if added, False if already exists
        """
        try:
            with self.transaction() as cursor:
                cursor.execute("""
                    INSERT OR IGNORE INTO subreddits (
                        name, status, last_checked, retry_count,
                        metadata_collected, threads_collected
                    )
                    VALUES (?, 'pending', 0, 0, 0, 0)
                """, (name.lower(),))

                return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Error adding subreddit {name}: {e}")
            return False

    def add_subreddits_bulk(self, names: List[str]) -> int:
        """
        Add multiple subreddits in bulk.

        Args:
            names: List of subreddit names

        Returns:
            Number of subreddits added
        """
        added = 0
        with self.transaction() as cursor:
            for name in names:
                cursor.execute("""
                    INSERT OR IGNORE INTO subreddits (
                        name, status, last_checked, retry_count,
                        metadata_collected, threads_collected
                    )
                    VALUES (?, 'pending', 0, 0, 0, 0)
                """, (name.lower(),))

                if cursor.rowcount > 0:
                    added += 1

        logging.info(f"Added {added} new subreddits to database")
        return added

    def ingest_from_csv(self, csv_path: str) -> Dict[str, int]:
        """
        Ingest NEW subreddits from CSV file (skips existing subreddits).

        CSV format: subreddit,subscribers (with header line)

        Only adds subreddits that DON'T exist in the database.
        Sets initial subscriber count and marks for processing.

        Args:
            csv_path: Path to CSV file

        Returns:
            Dictionary with counts: {added, skipped, total}
        """
        import csv
        from pathlib import Path

        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        added = 0
        skipped = 0
        total = 0

        logging.info(f"Ingesting NEW subreddits from {csv_path}...")

        with open(path, 'r') as f:
            reader = csv.reader(f)

            # Skip header
            next(reader, None)

            with self.transaction() as cursor:
                for row in reader:
                    if len(row) < 2:
                        continue

                    subreddit = row[0].strip().lower()

                    # Skip user profiles (u_something) - these aren't real subreddits
                    if subreddit.startswith('u_'):
                        skipped += 1
                        continue

                    try:
                        subscribers = int(row[1].strip())
                    except ValueError:
                        logging.warning(f"Invalid subscriber count for {subreddit}: {row[1]}")
                        continue

                    total += 1

                    # Check if subreddit exists
                    cursor.execute("SELECT name FROM subreddits WHERE name = ?", (subreddit,))
                    result = cursor.fetchone()

                    if not result:
                        # New subreddit - add with subscriber count
                        cursor.execute("""
                            INSERT INTO subreddits (
                                name, status, subscribers, last_checked, retry_count,
                                metadata_collected, threads_collected
                            )
                            VALUES (?, 'pending', ?, 0, 0, 0, 0)
                        """, (subreddit, subscribers))

                        added += 1
                    else:
                        # Already exists - skip
                        skipped += 1

        logging.info(
            f"CSV ingest complete: {total} total, {added} added, {skipped} skipped (already in DB)"
        )

        return {
            'total': total,
            'added': added,
            'skipped': skipped
        }

    def import_subreddits_from_csv(self, csv_path: str) -> Dict[str, int]:
        """
        Import subreddits from CSV file with subscriber counts.

        CSV format: subreddit,subscribers (no header)

        For each subreddit:
        - If not in DB: Add with CSV subscriber count
        - If in DB and not processed: Update subscriber count
        - If already processed: Skip (preserve existing data)

        Args:
            csv_path: Path to CSV file

        Returns:
            Dictionary with counts: {added, updated, skipped, total}
        """
        import csv
        from pathlib import Path

        path = Path(csv_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {csv_path}")

        added = 0
        updated = 0
        skipped = 0
        total = 0

        logging.info(f"Importing subreddits from {csv_path}...")

        with open(path, 'r') as f:
            reader = csv.reader(f)

            with self.transaction() as cursor:
                for row in reader:
                    if len(row) < 2:
                        continue

                    subreddit = row[0].strip().lower()

                    # Skip user profiles (u_something) - these aren't real subreddits
                    if subreddit.startswith('u_'):
                        skipped += 1
                        continue

                    try:
                        subscribers = int(row[1].strip())
                    except ValueError:
                        logging.warning(f"Invalid subscriber count for {subreddit}: {row[1]}")
                        continue

                    total += 1

                    # Check if subreddit exists and its processing state
                    cursor.execute("""
                        SELECT name, status, metadata_collected
                        FROM subreddits
                        WHERE name = ?
                    """, (subreddit,))

                    result = cursor.fetchone()

                    if not result:
                        # New subreddit - add with subscriber count
                        cursor.execute("""
                            INSERT INTO subreddits (
                                name, status, subscribers, last_checked, retry_count,
                                metadata_collected, threads_collected
                            )
                            VALUES (?, 'pending', ?, 0, 0, 0, 0)
                        """, (subreddit, subscribers))

                        added += 1

                    elif result[1] in ('pending', 'error') or result[2] == 0:
                        # Exists but not processed - update subscriber count
                        cursor.execute("""
                            UPDATE subreddits
                            SET subscribers = ?
                            WHERE name = ?
                        """, (subscribers, subreddit))

                        updated += 1

                    else:
                        # Already processed - skip
                        skipped += 1

        logging.info(
            f"CSV import complete: {total} total, {added} added, "
            f"{updated} updated, {skipped} skipped"
        )

        return {
            'total': total,
            'added': added,
            'updated': updated,
            'skipped': skipped
        }

    def update_subreddit_metadata(self, name: str, metadata: Dict[str, Any]) -> bool:
        """
        Update subreddit metadata.

        Args:
            name: Subreddit name
            metadata: Dictionary containing subreddit metadata

        Returns:
            True if successful
        """
        try:
            now = int(time.time())
            with self.transaction() as cursor:
                cursor.execute("""
                    UPDATE subreddits SET
                        title = ?,
                        description = ?,
                        public_description = ?,
                        subscribers = ?,
                        active_users = ?,
                        over_18 = ?,
                        status = ?,
                        subreddit_type = ?,
                        created_utc = ?,
                        last_updated = ?,
                        last_checked = ?,
                        error_message = NULL
                    WHERE name = ?
                """, (
                    metadata.get('title'),
                    metadata.get('description'),
                    metadata.get('public_description'),
                    metadata.get('subscribers'),
                    metadata.get('active_user_count'),
                    metadata.get('over18', False),
                    'active',
                    metadata.get('subreddit_type'),
                    metadata.get('created_utc'),
                    now,
                    now,
                    name.lower()
                ))

            return True
        except Exception as e:
            logging.error(f"Error updating subreddit {name}: {e}")
            return False

    def update_subreddit_status(self, name: str, status: str, error_message: Optional[str] = None):
        """
        Update subreddit status.

        Args:
            name: Subreddit name
            status: Status string
            error_message: Optional error message
        """
        now = int(time.time())
        with self.transaction() as cursor:
            cursor.execute("""
                UPDATE subreddits SET
                    status = ?,
                    last_checked = ?,
                    error_message = ?
                WHERE name = ?
            """, (status, now, error_message, name.lower()))

    def add_thread_ids(self, subreddit: str, thread_ids: List[str]) -> int:
        """
        Add thread IDs to the database with deduplication.

        Args:
            subreddit: Subreddit name
            thread_ids: List of thread IDs

        Returns:
            Number of new thread IDs added
        """
        added = 0

        with self.transaction() as cursor:
            for thread_id in thread_ids:
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO thread_ids (thread_id, subreddit)
                        VALUES (?, ?)
                    """, (thread_id, subreddit.lower()))

                    if cursor.rowcount > 0:
                        added += 1
                except Exception as e:
                    logging.error(f"Error adding thread ID {thread_id}: {e}")

        return added

    def update_subreddit(self, subreddit: str, status: str,
                        error_message: Optional[str] = None,
                        increment_retry: bool = False,
                        metadata_collected: Optional[bool] = None,
                        threads_collected: Optional[bool] = None):
        """
        Update subreddit processing status and flags.

        Args:
            subreddit: Subreddit name
            status: Processing status
            error_message: Error message (optional)
            increment_retry: Whether to increment retry counter
            metadata_collected: Whether metadata has been collected (optional)
            threads_collected: Whether thread IDs have been collected (optional)
        """
        now = int(time.time())

        with self.transaction() as cursor:
            if increment_retry:
                cursor.execute("""
                    UPDATE subreddits SET
                        status = ?,
                        last_checked = ?,
                        error_message = ?,
                        retry_count = retry_count + 1
                    WHERE name = ?
                """, (status, now, error_message, subreddit.lower()))
            else:
                # Build UPDATE statement dynamically based on what needs updating
                updates = ["status = ?", "last_checked = ?", "error_message = ?"]
                params = [status, now, error_message]

                if metadata_collected is not None:
                    updates.append("metadata_collected = ?")
                    params.append(metadata_collected)

                if threads_collected is not None:
                    updates.append("threads_collected = ?")
                    params.append(threads_collected)

                params.append(subreddit.lower())

                query = f"""
                    UPDATE subreddits SET
                        {', '.join(updates)}
                    WHERE name = ?
                """

                cursor.execute(query, params)

    def get_pending_subreddits(self, limit: Optional[int] = None, mode: str = 'metadata') -> List[str]:
        """
        Get subreddits pending processing based on mode.

        Priority order:
        1. Subreddits without subscriber counts (NULL subscribers) - process FIRST
        2. Never processed subreddits (pending/error with retry < 3) - by subscriber count DESC

        Mode 'metadata':
        - Returns subreddits where metadata_collected = 0 OR status = 'error'
        - Includes pending and error states

        Mode 'threads':
        - Returns subreddits where metadata_collected = 1 AND no threads in thread_ids table
        - Only active subreddits

        Args:
            limit: Maximum number to return
            mode: Processing mode ('metadata' or 'threads')

        Returns:
            List of subreddit names
        """
        cursor = self.conn.cursor()

        if mode == 'metadata':
            # Metadata mode: Get subreddits that need metadata collection or failed
            # Priority: NULL subscribers first, then by subscriber count DESC
            if limit:
                cursor.execute("""
                    SELECT name FROM subreddits
                    WHERE (metadata_collected = 0 OR status = 'error' OR status = 'pending')
                    AND retry_count < 3
                    ORDER BY
                        CASE WHEN subscribers IS NULL THEN 0 ELSE 1 END,
                        subscribers DESC NULLS LAST,
                        retry_count ASC
                    LIMIT ?
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT name FROM subreddits
                    WHERE (metadata_collected = 0 OR status = 'error' OR status = 'pending')
                    AND retry_count < 3
                    ORDER BY
                        CASE WHEN subscribers IS NULL THEN 0 ELSE 1 END,
                        subscribers DESC NULLS LAST,
                        retry_count ASC
                """)
        elif mode == 'threads':
            # Threads mode: Get subreddits that need thread ID collection
            # Must have metadata collected and threads not yet collected
            if limit:
                cursor.execute("""
                    SELECT name FROM subreddits
                    WHERE metadata_collected = 1
                    AND threads_collected = 0
                    AND retry_count < 3
                    AND status IN ('active', 'completed')
                    ORDER BY subscribers DESC NULLS LAST, retry_count ASC
                    LIMIT ?
                """, (limit,))
            else:
                cursor.execute("""
                    SELECT name FROM subreddits
                    WHERE metadata_collected = 1
                    AND threads_collected = 0
                    AND retry_count < 3
                    AND status IN ('active', 'completed')
                    ORDER BY subscribers DESC NULLS LAST, retry_count ASC
                """)
        else:
            raise ValueError(f"Invalid mode: {mode}. Must be 'metadata' or 'threads'")

        return [row[0] for row in cursor.fetchall()]

    def get_processing_stats(self) -> Dict[str, int]:
        """
        Get processing statistics.

        Returns:
            Dictionary with statistics
        """
        cursor = self.conn.cursor()

        # Count by status
        cursor.execute("""
            SELECT status, COUNT(*) FROM subreddits
            GROUP BY status
        """)
        stats = dict(cursor.fetchall())

        # Total thread IDs
        cursor.execute("SELECT COUNT(*) FROM thread_ids")
        stats['total_threads'] = cursor.fetchone()[0]

        # Total subreddits
        cursor.execute("SELECT COUNT(*) FROM subreddits")
        stats['total_subreddits'] = cursor.fetchone()[0]

        # Metadata collection stats
        cursor.execute("SELECT COUNT(*) FROM subreddits WHERE metadata_collected = 1")
        stats['metadata_collected'] = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM subreddits
            WHERE (metadata_collected = 0 OR status = 'error' OR status = 'pending')
            AND retry_count < 3
        """)
        stats['metadata_pending'] = cursor.fetchone()[0]

        # Thread collection stats
        cursor.execute("SELECT COUNT(*) FROM subreddits WHERE threads_collected = 1")
        stats['threads_collected'] = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM subreddits WHERE threads_collected = 0")
        stats['threads_pending'] = cursor.fetchone()[0]

        return stats

    def cleanup_user_profiles(self) -> int:
        """
        Remove user profiles (u_*) from database - these aren't real subreddits.

        Returns:
            Number of entries removed
        """
        with self.transaction() as cursor:
            # Count how many we'll remove
            cursor.execute("SELECT COUNT(*) FROM subreddits WHERE name LIKE 'u_%'")
            count = cursor.fetchone()[0]

            if count > 0:
                # Remove thread_ids first (foreign key)
                cursor.execute("DELETE FROM thread_ids WHERE subreddit LIKE 'u_%'")
                threads_removed = cursor.rowcount

                # Remove subreddits
                cursor.execute("DELETE FROM subreddits WHERE name LIKE 'u_%'")

                logging.info(f"Cleaned up {count} user profiles (u_*) and {threads_removed} associated threads")

            return count

    def fix_inconsistent_states(self) -> Dict[str, int]:
        """
        Fix inconsistent processing states in the database.

        Fixes:
        - Subreddits with status='pending' but metadata_collected=1
        - Subreddits with status='completed' but metadata_collected=0

        Returns:
            Dictionary with counts of fixed records
        """
        fixed = {'pending_with_metadata': 0, 'completed_without_metadata': 0}

        with self.transaction() as cursor:
            # Fix: status='pending' but metadata_collected=1 -> set metadata_collected=0
            cursor.execute("""
                UPDATE subreddits
                SET metadata_collected = 0, threads_collected = 0
                WHERE status = 'pending' AND metadata_collected = 1
            """)
            fixed['pending_with_metadata'] = cursor.rowcount

            # Fix: status='completed' but metadata_collected=0 -> set status='pending'
            cursor.execute("""
                UPDATE subreddits
                SET status = 'pending'
                WHERE status = 'completed' AND metadata_collected = 0
            """)
            fixed['completed_without_metadata'] = cursor.rowcount

        total_fixed = sum(fixed.values())
        if total_fixed > 0:
            logging.info(f"Fixed {total_fixed} inconsistent states in database")

        return fixed

    def vacuum(self) -> Dict[str, float]:
        """
        Compact database and reclaim space from deleted rows.

        VACUUM rebuilds the database file, repacking it into a minimal amount of disk space.
        This is useful after deleting data or dropping tables.

        Returns:
            Dictionary with size before and after in MB
        """
        import os

        # Get size before
        size_before = os.path.getsize(self.db_path)

        logging.info("Compacting database (VACUUM)...")
        cursor = self.conn.cursor()
        cursor.execute("VACUUM")
        self.conn.commit()

        # Get size after
        size_after = os.path.getsize(self.db_path)

        size_before_mb = size_before / (1024 * 1024)
        size_after_mb = size_after / (1024 * 1024)
        saved_mb = size_before_mb - size_after_mb

        logging.info(f"✓ Database compacted: {size_before_mb:.1f}MB → {size_after_mb:.1f}MB (saved {saved_mb:.1f}MB)")

        return {
            'size_before_mb': size_before_mb,
            'size_after_mb': size_after_mb,
            'saved_mb': saved_mb
        }

    def get_subreddit_info(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get subreddit information.

        Args:
            name: Subreddit name

        Returns:
            Dictionary with subreddit info or None
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM subreddits WHERE name = ?", (name.lower(),))

        row = cursor.fetchone()
        if row:
            return dict(row)
        return None

    def get_thread_count(self, subreddit: Optional[str] = None) -> int:
        """
        Get count of thread IDs.

        Args:
            subreddit: Optional subreddit filter

        Returns:
            Count of thread IDs
        """
        cursor = self.conn.cursor()

        if subreddit:
            cursor.execute("SELECT COUNT(*) FROM thread_ids WHERE subreddit = ?", (subreddit.lower(),))
        else:
            cursor.execute("SELECT COUNT(*) FROM thread_ids")

        return cursor.fetchone()[0]

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logging.debug("Database connection closed")
