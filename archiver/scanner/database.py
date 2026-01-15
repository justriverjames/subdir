import psycopg2
from psycopg2 import pool, extras
from contextlib import contextmanager
import time
import logging
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


class Database:
    """PostgreSQL connection pool and query interface"""

    def __init__(self, config):
        self.config = config
        self.pool = None

    def connect(self):
        """Initialize connection pool"""
        try:
            self.pool = psycopg2.pool.ThreadedConnectionPool(
                minconn=2,
                maxconn=10,
                host=self.config.postgres_host,
                port=self.config.postgres_port,
                database=self.config.postgres_db,
                user=self.config.postgres_user,
                password=self.config.postgres_password
            )
            logger.info("PostgreSQL connection pool created")
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """Get connection from pool"""
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
            conn.commit()
        except Exception:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                self.pool.putconn(conn)

    def close(self):
        """Close all connections"""
        if self.pool:
            self.pool.closeall()
            logger.info("Connection pool closed")

    # Subreddit operations

    def add_subreddit(self, name: str, priority: int = 2) -> bool:
        """Add subreddit if not exists"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO subreddits (name, priority, status, first_seen_at)
                    VALUES (%s, %s, 'pending', %s)
                    ON CONFLICT (name) DO NOTHING
                    RETURNING name
                    """,
                    (name.lower(), priority, int(time.time()))
                )
                return cur.fetchone() is not None

    def update_subreddit_metadata(self, name: str, metadata: Dict[str, Any]):
        """Update subreddit metadata after fetch"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE subreddits
                    SET
                        display_name = %s,
                        title = %s,
                        public_description = %s,
                        description = %s,
                        subscribers = %s,
                        active_users = %s,
                        created_utc = %s,
                        icon_url = %s,
                        banner_url = %s,
                        primary_color = %s,
                        key_color = %s,
                        over_18 = %s,
                        subreddit_type = %s,
                        status = %s,
                        last_metadata_update = %s,
                        retry_count = 0,
                        error_message = NULL,
                        metadata = %s
                    WHERE name = %s
                    """,
                    (
                        metadata.get('display_name'),
                        metadata.get('title'),
                        metadata.get('public_description'),
                        metadata.get('description'),
                        metadata.get('subscribers', 0),
                        metadata.get('active_user_count', 0),
                        metadata.get('created_utc'),
                        metadata.get('icon_url'),
                        metadata.get('banner_img'),
                        metadata.get('primary_color'),
                        metadata.get('key_color'),
                        metadata.get('over18', False),
                        metadata.get('subreddit_type'),
                        'active',
                        int(time.time()),
                        extras.Json(metadata),
                        name.lower()
                    )
                )

    def update_subreddit_status(self, name: str, status: str, error_msg: Optional[str] = None):
        """Update subreddit status"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE subreddits
                    SET status = %s,
                        error_message = %s,
                        retry_count = retry_count + 1
                    WHERE name = %s
                    """,
                    (status, error_msg, name.lower())
                )

    def get_subreddits_for_processing(self, limit: int = 50, min_subscribers: int = 5000) -> List[Dict]:
        """Get subreddits ready for processing"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM subreddits
                    WHERE status IN ('pending', 'active')
                        AND (subscribers IS NULL OR subscribers >= %s)
                        AND (retry_count < 3)
                    ORDER BY priority ASC, subscribers DESC NULLS LAST
                    LIMIT %s
                    """,
                    (min_subscribers, limit)
                )
                return [dict(row) for row in cur.fetchall()]

    # Post operations

    def add_posts(self, posts: List[Dict[str, Any]]):
        """Bulk insert posts"""
        if not posts:
            return

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # Use execute_batch for efficiency
                extras.execute_batch(
                    cur,
                    """
                    INSERT INTO posts (
                        id, subreddit, author, title, selftext, url, domain,
                        post_type, is_self, is_video,
                        created_utc, edited_utc, archived_at,
                        score, upvote_ratio, num_comments, num_crossposts,
                        over_18, spoiler, stickied, locked, archived,
                        link_flair_text, link_flair_css_class, author_flair_text,
                        source_listing, metadata
                    )
                    VALUES (
                        %(id)s, %(subreddit)s, %(author)s, %(title)s, %(selftext)s,
                        %(url)s, %(domain)s, %(post_type)s, %(is_self)s, %(is_video)s,
                        %(created_utc)s, %(edited_utc)s, %(archived_at)s,
                        %(score)s, %(upvote_ratio)s, %(num_comments)s, %(num_crossposts)s,
                        %(over_18)s, %(spoiler)s, %(stickied)s, %(locked)s, %(archived)s,
                        %(link_flair_text)s, %(link_flair_css_class)s, %(author_flair_text)s,
                        %(source_listing)s, %(metadata)s
                    )
                    ON CONFLICT (id) DO NOTHING
                    """,
                    posts
                )

                # Update subreddit stats
                if posts:
                    subreddit = posts[0]['subreddit']
                    cur.execute(
                        """
                        UPDATE subreddits
                        SET total_posts = (SELECT COUNT(*) FROM posts WHERE subreddit = %s),
                            last_posts_fetch = %s
                        WHERE name = %s
                        """,
                        (subreddit, int(time.time()), subreddit)
                    )

    def get_posts_for_comments(self, subreddit: str, limit: int = 500) -> List[Dict]:
        """Get posts that need comments fetched"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, subreddit, title
                    FROM posts
                    WHERE subreddit = %s
                        AND comment_fetch_status = 'pending'
                    ORDER BY score DESC
                    LIMIT %s
                    """,
                    (subreddit, limit)
                )
                return [dict(row) for row in cur.fetchall()]

    def get_posts_for_media_extraction(self, subreddit: str) -> List[Dict]:
        """Get posts that need media extraction"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, subreddit, metadata
                    FROM posts
                    WHERE subreddit = %s
                        AND media_extracted = FALSE
                    ORDER BY score DESC
                    """,
                    (subreddit,)
                )
                return [dict(row) for row in cur.fetchall()]

    def update_post_comment_status(self, post_id: str, status: str, comment_count: int):
        """Update post comment fetch status"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE posts
                    SET comment_fetch_status = %s,
                        comment_count_archived = %s
                    WHERE id = %s
                    """,
                    (status, comment_count, post_id)
                )

    def update_post_media_extracted(self, post_id: str):
        """Mark post media as extracted"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE posts SET media_extracted = TRUE WHERE id = %s",
                    (post_id,)
                )

    # Comment operations

    def add_comments(self, comments: List[Dict[str, Any]]):
        """Bulk insert comments"""
        if not comments:
            return

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                extras.execute_batch(
                    cur,
                    """
                    INSERT INTO comments (
                        id, post_id, parent_id, author, body, body_html,
                        created_utc, edited_utc, archived_at,
                        score, controversiality, gilded,
                        depth, path,
                        stickied, is_submitter, score_hidden, distinguished,
                        is_bot
                    )
                    VALUES (
                        %(id)s, %(post_id)s, %(parent_id)s, %(author)s, %(body)s, %(body_html)s,
                        %(created_utc)s, %(edited_utc)s, %(archived_at)s,
                        %(score)s, %(controversiality)s, %(gilded)s,
                        %(depth)s, %(path)s,
                        %(stickied)s, %(is_submitter)s, %(score_hidden)s, %(distinguished)s,
                        %(is_bot)s
                    )
                    ON CONFLICT (id) DO NOTHING
                    """,
                    comments
                )

                # Update subreddit stats
                if comments:
                    post_id = comments[0]['post_id']
                    cur.execute(
                        """
                        UPDATE subreddits
                        SET total_comments = (
                            SELECT COUNT(*)
                            FROM comments c
                            JOIN posts p ON c.post_id = p.id
                            WHERE p.subreddit = subreddits.name
                        ),
                        last_comments_fetch = %s
                        WHERE name IN (
                            SELECT subreddit FROM posts WHERE id = %s
                        )
                        """,
                        (int(time.time()), post_id)
                    )

    # Media URL operations

    def add_media_urls(self, media_urls: List[Dict[str, Any]]):
        """Bulk insert media URLs"""
        if not media_urls:
            return

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                extras.execute_batch(
                    cur,
                    """
                    INSERT INTO media_urls (
                        post_id, url, media_type, source, position,
                        width, height, duration,
                        status, extracted_at
                    )
                    VALUES (
                        %(post_id)s, %(url)s, %(media_type)s, %(source)s, %(position)s,
                        %(width)s, %(height)s, %(duration)s,
                        %(status)s, %(extracted_at)s
                    )
                    ON CONFLICT DO NOTHING
                    """,
                    media_urls
                )

                # Update subreddit stats
                if media_urls:
                    post_id = media_urls[0]['post_id']
                    cur.execute(
                        """
                        UPDATE subreddits
                        SET total_media_urls = (
                            SELECT COUNT(*)
                            FROM media_urls m
                            JOIN posts p ON m.post_id = p.id
                            WHERE p.subreddit = subreddits.name
                        )
                        WHERE name IN (
                            SELECT subreddit FROM posts WHERE id = %s
                        )
                        """,
                        (post_id,)
                    )

    # Processing state operations

    def update_processing_state(self, subreddit: str, phase: str, progress: Optional[Dict] = None):
        """Update processing state"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO processing_state (subreddit, current_phase, phase_started_at, phase_progress, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (subreddit)
                    DO UPDATE SET
                        current_phase = EXCLUDED.current_phase,
                        phase_progress = EXCLUDED.phase_progress,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (subreddit, phase, int(time.time()), extras.Json(progress or {}), int(time.time()))
                )

    def get_processing_state(self, subreddit: str) -> Optional[Dict]:
        """Get processing state for subreddit"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(
                    "SELECT * FROM processing_state WHERE subreddit = %s",
                    (subreddit,)
                )
                row = cur.fetchone()
                return dict(row) if row else None

    # Statistics

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                stats = {}

                # Subreddit stats
                cur.execute("SELECT COUNT(*) FROM subreddits")
                stats['total_subreddits'] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM subreddits WHERE status = 'active'")
                stats['active_subreddits'] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(*) FROM subreddits WHERE status = 'pending'")
                stats['pending_subreddits'] = cur.fetchone()[0]

                # Post stats
                cur.execute("SELECT COUNT(*) FROM posts")
                stats['total_posts'] = cur.fetchone()[0]

                cur.execute("SELECT COUNT(DISTINCT subreddit) FROM posts")
                stats['subreddits_with_posts'] = cur.fetchone()[0]

                # Comment stats
                cur.execute("SELECT COUNT(*) FROM comments")
                stats['total_comments'] = cur.fetchone()[0]

                # Media stats
                cur.execute("SELECT COUNT(*) FROM media_urls")
                stats['total_media_urls'] = cur.fetchone()[0]

                # Processing stats
                cur.execute("SELECT COUNT(*) FROM processing_state")
                stats['subreddits_in_progress'] = cur.fetchone()[0]

                return stats

    # Migration operations

    def run_migration(self, sql_file: str):
        """Run SQL migration file"""
        with open(sql_file, 'r') as f:
            sql = f.read()

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        logger.info(f"Migration {sql_file} completed")

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return True
        except Exception as e:
            logger.error(f"Connection test failed: {e}")
            return False
