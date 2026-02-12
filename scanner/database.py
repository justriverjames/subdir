"""
Database module for subreddit metadata and thread ID storage using SQLite.
"""

import sqlite3
import logging
import time
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from database_migrations import migrate_v1_to_v2, migrate_v2_to_v3, ensure_v4_columns


class Database:
    """SQLite database manager for subreddit scanning."""

    SCHEMA_VERSION = 4

    SCHEMA = """
    -- Subreddit metadata and discovery table
    CREATE TABLE IF NOT EXISTS subreddits (
        name TEXT PRIMARY KEY,
        -- Metadata from Reddit API
        title TEXT,
        description TEXT,  -- Short description (from public_description in API)
        subscribers INTEGER,
        active_users INTEGER,
        over_18 BOOLEAN,
        subreddit_type TEXT,  -- 'public', 'private', 'restricted', 'archived'
        created_utc INTEGER,
        -- Visual/branding fields (v4)
        icon_url TEXT,
        primary_color TEXT,
        -- Categorization helper fields (v4)
        advertiser_category TEXT,
        submission_type TEXT,
        allow_images BOOLEAN DEFAULT 1,
        allow_videos BOOLEAN DEFAULT 1,
        allow_galleries BOOLEAN DEFAULT 0,
        allow_videogifs BOOLEAN DEFAULT 0,
        allow_polls BOOLEAN DEFAULT 0,
        -- Community quality indicators
        link_flair_enabled BOOLEAN DEFAULT 0,
        spoilers_enabled BOOLEAN DEFAULT 0,
        whitelist_status INTEGER,
        -- Search and discovery fields
        category TEXT,
        tags TEXT,
        language TEXT DEFAULT 'en',
        -- Status and processing tracking
        status TEXT,  -- 'pending', 'active', 'private', 'banned', 'quarantined', 'deleted', 'error'
        is_accessible BOOLEAN DEFAULT 1,  -- 0 for banned/deleted/private/quarantined (quick filter)
        last_updated INTEGER,
        retry_count INTEGER DEFAULT 0,  -- Retry counter for 403/404 errors (--update mode only)
        error_message TEXT,
        metadata_collected BOOLEAN DEFAULT 0
    );

    -- Schema version tracking
    CREATE TABLE IF NOT EXISTS schema_version (
        version INTEGER PRIMARY KEY
    );

    -- Optimized indexes for search and filtering
    CREATE INDEX IF NOT EXISTS idx_subreddits_status ON subreddits(status);
    CREATE INDEX IF NOT EXISTS idx_subreddits_metadata_collected ON subreddits(metadata_collected);
    CREATE INDEX IF NOT EXISTS idx_subreddits_subscribers ON subreddits(subscribers DESC);
    CREATE INDEX IF NOT EXISTS idx_subreddits_category ON subreddits(category);
    CREATE INDEX IF NOT EXISTS idx_subreddits_language ON subreddits(language);
    CREATE INDEX IF NOT EXISTS idx_subreddits_name_prefix ON subreddits(name COLLATE NOCASE);
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
                migrate_v1_to_v2(self.conn)
                current_version = 2

            if current_version == 2:
                migrate_v2_to_v3(self.conn)
                current_version = 3

            if current_version == 3:
                # v3→v4: add new metadata columns (handled by ensure_v4_columns below)
                current_version = 4

            # Update version
            cursor.execute("UPDATE schema_version SET version = ?", (current_version,))
            self.conn.commit()
            logging.info(f"✓ Database migration complete: now at version {current_version}")
        elif current_version > self.SCHEMA_VERSION:
            raise ValueError(
                f"Database schema version {current_version} is newer than code version {self.SCHEMA_VERSION}. "
                f"Please update the scanner code."
            )

        # Ensure all columns exist (for v4 schema enhancements)
        ensure_v4_columns(self.conn)

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
                        name, status, metadata_collected
                    )
                    VALUES (?, 'pending', 0)
                """, (name.lower(),))

                return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Error adding subreddit {name}: {e}")
            return False

    def update_subreddit_metadata(self, name: str, metadata: Dict[str, Any]) -> bool:
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
                        name, status, metadata_collected
                    )
                    VALUES (?, 'pending', 0)
                """, (name.lower(),))

                if cursor.rowcount > 0:
                    added += 1

        logging.info(f"Added {added} new subreddits to database")
        return added

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
                        subscribers = ?,
                        active_users = ?,
                        over_18 = ?,
                        status = ?,
                        is_accessible = 1,
                        subreddit_type = ?,
                        created_utc = ?,
                        last_updated = ?,
                        icon_url = ?,
                        primary_color = ?,
                        advertiser_category = ?,
                        submission_type = ?,
                        allow_images = ?,
                        allow_videos = ?,
                        allow_galleries = ?,
                        allow_videogifs = ?,
                        allow_polls = ?,
                        link_flair_enabled = ?,
                        spoilers_enabled = ?,
                        whitelist_status = ?,
                        language = ?,
                        error_message = NULL
                    WHERE name = ?
                """, (
                    metadata.get('title'),
                    self._decode_html_entities(metadata.get('public_description')),  # Short description -> description
                    metadata.get('subscribers'),
                    metadata.get('active_user_count'),
                    metadata.get('over18', False),
                    'active',
                    metadata.get('subreddit_type'),
                    metadata.get('created_utc'),
                    now,
                    self._decode_html_entities(metadata.get('community_icon')),
                    metadata.get('primary_color'),
                    metadata.get('advertiser_category'),
                    metadata.get('submission_type'),
                    metadata.get('allow_images', True),
                    metadata.get('allow_videos', True),
                    metadata.get('allow_galleries', False),
                    metadata.get('allow_videogifs', False),
                    metadata.get('allow_polls', False),
                    metadata.get('link_flair_enabled', False),
                    metadata.get('spoilers_enabled', False),
                    metadata.get('wls'),
                    metadata.get('lang', 'en'),
                    name.lower()
                ))

            return True
        except Exception as e:
            logging.error(f"Error updating subreddit {name}: {e}")
            return False

    def update_subreddit_status(self, name: str, status: str, error_message: Optional[str] = None):
        """
        Update subreddit status and accessibility.

        Args:
            name: Subreddit name
            status: Status string
            error_message: Optional error message
        """
        # Determine if subreddit is accessible
        # Only 'active' and 'pending' are accessible
        is_accessible = 1 if status in ('active', 'pending') else 0

        with self.transaction() as cursor:
            cursor.execute("""
                UPDATE subreddits SET
                    status = ?,
                    is_accessible = ?,
                    error_message = ?
                WHERE name = ?
            """, (status, is_accessible, error_message, name.lower()))

    def update_subreddit(self, subreddit: str, status: str,
                        error_message: Optional[str] = None,
                        metadata_collected: Optional[bool] = None):
        """
        Update subreddit processing status and flags.

        Args:
            subreddit: Subreddit name
            status: Processing status
            error_message: Error message (optional)
            metadata_collected: Whether metadata has been collected (optional)
        """
        with self.transaction() as cursor:
            # Build UPDATE statement dynamically based on what needs updating
            updates = ["status = ?", "error_message = ?"]
            params = [status, error_message]

            if metadata_collected is not None:
                updates.append("metadata_collected = ?")
                params.append(metadata_collected)

            params.append(subreddit.lower())

            query = f"""
                UPDATE subreddits SET
                    {', '.join(updates)}
                WHERE name = ?
            """

            cursor.execute(query, params)

    def count_stale_subreddits(self, stale_days: int = 30) -> Dict[str, int]:
        """
        Count subreddits needing update (never updated or stale).

        Args:
            stale_days: Minimum days since last update (default 30)

        Returns:
            Dictionary with counts: never_updated, stale, total_needing_update
        """
        import time
        cursor = self.conn.cursor()

        stale_cutoff = int(time.time()) - (stale_days * 24 * 60 * 60)

        # Count never updated
        cursor.execute("""
            SELECT COUNT(*) FROM subreddits
            WHERE metadata_collected = 1 AND status = 'active'
              AND last_updated IS NULL
        """)
        never_updated = cursor.fetchone()[0]

        # Count stale (older than cutoff)
        cursor.execute("""
            SELECT COUNT(*) FROM subreddits
            WHERE metadata_collected = 1 AND status = 'active'
              AND last_updated IS NOT NULL
              AND last_updated < ?
        """, (stale_cutoff,))
        stale = cursor.fetchone()[0]

        return {
            'never_updated': never_updated,
            'stale': stale,
            'total_needing_update': never_updated + stale,
            'stale_days': stale_days
        }

    def get_subreddits_for_update(self, limit: Optional[int] = None, stale_days: int = 30, nsfw_only: bool = False) -> List[str]:
        """
        Get subreddits for metadata refresh/update.

        Only returns subreddits that need updating:
        - Never updated (last_updated IS NULL), OR
        - Last updated more than stale_days ago

        Priority order:
        Phase 1 (never updated): NULL last_updated, ordered by subscribers DESC
        Phase 2 (stale): Oldest last_updated first, then subscribers DESC

        Args:
            limit: Maximum number to return
            stale_days: Minimum days since last update (default 30)
            nsfw_only: Only return NSFW (over_18) subreddits

        Returns:
            List of subreddit names
        """
        import time
        cursor = self.conn.cursor()

        # Calculate cutoff timestamp (stale_days ago)
        stale_cutoff = int(time.time()) - (stale_days * 24 * 60 * 60)

        # Build WHERE clause
        where_clause = "metadata_collected = 1 AND status = 'active' AND (last_updated IS NULL OR last_updated < ?)"
        if nsfw_only:
            where_clause += " AND over_18 = 1"

        # Only get subreddits that are stale or never updated
        if limit:
            cursor.execute(f"""
                SELECT name FROM subreddits
                WHERE {where_clause}
                ORDER BY
                    CASE WHEN last_updated IS NULL THEN 0 ELSE 1 END ASC,
                    CASE WHEN last_updated IS NULL THEN -COALESCE(subscribers, 0) ELSE last_updated END ASC,
                    subscribers DESC NULLS LAST
                LIMIT ?
            """, (stale_cutoff, limit))
        else:
            cursor.execute(f"""
                SELECT name FROM subreddits
                WHERE {where_clause}
                ORDER BY
                    CASE WHEN last_updated IS NULL THEN 0 ELSE 1 END ASC,
                    CASE WHEN last_updated IS NULL THEN -COALESCE(subscribers, 0) ELSE last_updated END ASC,
                    subscribers DESC NULLS LAST
            """, (stale_cutoff,))

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

        # Total subreddits
        cursor.execute("SELECT COUNT(*) FROM subreddits")
        stats['total_subreddits'] = cursor.fetchone()[0]

        # Metadata collection stats
        cursor.execute("SELECT COUNT(*) FROM subreddits WHERE metadata_collected = 1")
        stats['metadata_collected'] = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM subreddits
            WHERE (metadata_collected = 0 OR status = 'error' OR status = 'pending')
        """)
        stats['metadata_pending'] = cursor.fetchone()[0]

        return stats

    def cleanup_user_profiles(self) -> int:
        """
        Remove user profiles from database - these aren't real subreddits.
        Detects user profiles by subreddit_type = 'user' or u_ prefix.

        Returns:
            Number of entries removed
        """
        with self.transaction() as cursor:
            # Count how many we'll remove (both by type and by prefix)
            cursor.execute(
                "SELECT COUNT(*) FROM subreddits "
                "WHERE subreddit_type = 'user' OR name LIKE 'u_%'"
            )
            count = cursor.fetchone()[0]

            if count > 0:
                # Remove user profiles
                cursor.execute(
                    "DELETE FROM subreddits "
                    "WHERE subreddit_type = 'user' OR name LIKE 'u_%'"
                )

                logging.info(f"Cleaned up {count} user profiles")

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
                SET metadata_collected = 0
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

    def _decode_html_entities(self, text: Optional[str]) -> Optional[str]:
        """
        Decode HTML entities in text (e.g., &amp; -> &).

        Args:
            text: Text that may contain HTML entities

        Returns:
            Decoded text or None if input is None
        """
        if not text:
            return text

        import html
        return html.unescape(text)

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

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logging.debug("Database connection closed")
