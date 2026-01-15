"""
Database schema migrations for subreddit scanner.

Historical migration logic for upgrading from older schema versions.
"""

import logging
import sqlite3


def migrate_v1_to_v2(conn: sqlite3.Connection):
    """Migrate from schema v1 to v2: merge processing_state into subreddits, simplify thread_ids."""
    cursor = conn.cursor()
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

        conn.commit()
        logging.info("✓ Schema v1→v2 migration complete")

        # Compact database to reclaim space from dropped tables
        logging.info("Compacting database (VACUUM)...")
        cursor.execute("VACUUM")
        logging.info("✓ Database compacted")

    except Exception as e:
        conn.rollback()
        logging.error(f"Migration failed: {e}")
        raise


def migrate_v2_to_v3(conn: sqlite3.Connection):
    """Migrate from schema v2 to v3: focus on subreddit metadata, drop thread tracking."""
    cursor = conn.cursor()
    logging.info("Starting v2→v3 migration...")

    try:
        # 1. Create new subreddits table with v3 schema
        cursor.execute("""
            CREATE TABLE subreddits_v3 (
                name TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                public_description TEXT,
                subscribers INTEGER,
                active_users INTEGER,
                over_18 BOOLEAN,
                subreddit_type TEXT,
                created_utc INTEGER,
                category TEXT,
                tags TEXT,
                language TEXT DEFAULT 'en',
                status TEXT,
                last_updated INTEGER,
                error_message TEXT,
                metadata_collected BOOLEAN DEFAULT 0
            )
        """)

        # 2. Copy data from v2 to v3 (excluding threads_collected, retry_count, last_checked)
        cursor.execute("""
            INSERT INTO subreddits_v3 (
                name, title, description, public_description,
                subscribers, active_users, over_18, subreddit_type, created_utc,
                category, tags, language,
                status, last_updated, error_message, metadata_collected
            )
            SELECT
                name, title, description, public_description,
                subscribers, active_users, over_18, subreddit_type, created_utc,
                NULL as category,
                NULL as tags,
                'en' as language,
                status, last_updated, error_message, metadata_collected
            FROM subreddits
        """)

        # 3. Drop old tables and indexes
        cursor.execute("DROP TABLE IF EXISTS thread_ids")
        cursor.execute("DROP INDEX IF EXISTS idx_thread_ids_subreddit")
        cursor.execute("DROP INDEX IF EXISTS idx_subreddits_threads_collected")
        cursor.execute("DROP INDEX IF EXISTS idx_subreddits_retry_count")
        cursor.execute("DROP TABLE subreddits")

        # 4. Rename new table
        cursor.execute("ALTER TABLE subreddits_v3 RENAME TO subreddits")

        # 5. Create v3 indexes
        cursor.executescript("""
            CREATE INDEX idx_subreddits_status ON subreddits(status);
            CREATE INDEX idx_subreddits_metadata_collected ON subreddits(metadata_collected);
            CREATE INDEX idx_subreddits_subscribers ON subreddits(subscribers DESC);
            CREATE INDEX idx_subreddits_category ON subreddits(category);
            CREATE INDEX idx_subreddits_language ON subreddits(language);
            CREATE INDEX idx_subreddits_name_prefix ON subreddits(name COLLATE NOCASE);
        """)

        conn.commit()
        logging.info("✓ Schema v2→v3 migration complete")

        # Compact database to reclaim space
        logging.info("Compacting database (VACUUM)...")
        cursor.execute("VACUUM")
        logging.info("✓ Database compacted")

    except Exception as e:
        conn.rollback()
        logging.error(f"Migration failed: {e}")
        raise


def ensure_v4_columns(conn: sqlite3.Connection):
    """Ensure all v4 schema columns exist (add missing columns for existing v4 databases)."""
    cursor = conn.cursor()

    # List of columns to add if missing (column_name, column_type_and_default)
    new_columns = [
        ('icon_url', 'TEXT'),
        ('primary_color', 'TEXT'),
        ('advertiser_category', 'TEXT'),
        ('submission_type', 'TEXT'),
        ('allow_images', 'BOOLEAN DEFAULT 1'),
        ('allow_videos', 'BOOLEAN DEFAULT 1'),
        ('allow_galleries', 'BOOLEAN DEFAULT 0'),
        ('allow_videogifs', 'BOOLEAN DEFAULT 0'),
        ('allow_polls', 'BOOLEAN DEFAULT 0'),
        ('link_flair_enabled', 'BOOLEAN DEFAULT 0'),
        ('spoilers_enabled', 'BOOLEAN DEFAULT 0'),
        ('whitelist_status', 'INTEGER'),
        ('is_accessible', 'BOOLEAN DEFAULT 1'),
        ('retry_count', 'INTEGER DEFAULT 0'),
    ]

    # Get existing columns
    cursor.execute("PRAGMA table_info(subreddits)")
    existing_cols = {row[1] for row in cursor.fetchall()}

    # Add missing columns
    added = []
    for col_name, col_def in new_columns:
        if col_name not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE subreddits ADD COLUMN {col_name} {col_def}")
                added.append(col_name)
            except Exception as e:
                logging.warning(f"Could not add column {col_name}: {e}")

    if added:
        conn.commit()
        logging.info(f"Added new columns to v4 schema: {', '.join(added)}")
