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
        """Get posts that need media extraction - includes columns + metadata"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        id,
                        subreddit,
                        url,
                        is_video,
                        post_type,
                        metadata
                    FROM posts
                    WHERE subreddit = %s
                        AND media_extracted = FALSE
                    ORDER BY score DESC
                    """,
                    (subreddit,)
                )
                rows = cur.fetchall()

                # Merge metadata into main dict for processing
                result = []
                for row in rows:
                    post_dict = dict(row)
                    metadata = post_dict.pop('metadata', {}) or {}
                    # Merge metadata fields into post_dict
                    post_dict.update(metadata)
                    # Check if gallery based on post_type or gallery_data having actual content
                    post_dict['is_gallery'] = (post_dict.get('post_type') == 'gallery' or
                                               bool(post_dict.get('gallery_data')))
                    result.append(post_dict)

                return result

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

    # Two-tier processing operations

    def get_subreddits_for_posts(self, limit: int = 50, min_subscribers: int = 5000) -> List[Dict]:
        """Get subreddits that need posts processing (metadata + posts + media)"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM subreddits
                    WHERE posts_status = 'pending'
                        AND (subscribers IS NULL OR subscribers >= %s)
                        AND retry_count < 3
                    ORDER BY priority ASC, subscribers DESC NULLS LAST
                    LIMIT %s
                    """,
                    (min_subscribers, limit)
                )
                return [dict(row) for row in cur.fetchall()]

    def get_posts_for_comments_batch(self, limit: int = 5, spread_across_subs: bool = True) -> List[Dict]:
        """
        Get posts needing comments, optionally spread across multiple subreddits.
        Returns posts ordered by: comments_status='processing' first, then by score.
        """
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                if spread_across_subs:
                    # Get distinct subreddits first, then one high-scoring post from each
                    cur.execute(
                        """
                        WITH subs_needing_comments AS (
                            SELECT DISTINCT p.subreddit
                            FROM posts p
                            JOIN subreddits s ON p.subreddit = s.name
                            WHERE p.comment_fetch_status = 'pending'
                                AND s.posts_status = 'completed'
                            ORDER BY s.comments_status = 'processing' DESC,
                                     s.subscribers DESC NULLS LAST
                            LIMIT %s
                        ),
                        ranked_posts AS (
                            SELECT p.*,
                                   ROW_NUMBER() OVER (PARTITION BY p.subreddit ORDER BY p.score DESC) as rn
                            FROM posts p
                            WHERE p.subreddit IN (SELECT subreddit FROM subs_needing_comments)
                                AND p.comment_fetch_status = 'pending'
                        )
                        SELECT id, subreddit, title
                        FROM ranked_posts
                        WHERE rn = 1
                        ORDER BY subreddit
                        """,
                        (limit,)
                    )
                else:
                    # Just get top posts by score regardless of subreddit
                    cur.execute(
                        """
                        SELECT p.id, p.subreddit, p.title
                        FROM posts p
                        JOIN subreddits s ON p.subreddit = s.name
                        WHERE p.comment_fetch_status = 'pending'
                            AND s.posts_status = 'completed'
                        ORDER BY p.score DESC
                        LIMIT %s
                        """,
                        (limit,)
                    )
                return [dict(row) for row in cur.fetchall()]

    def mark_posts_complete(self, subreddit: str):
        """Mark posts processing (posts + media) as completed for subreddit"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                now = int(time.time())
                cur.execute(
                    """
                    UPDATE subreddits
                    SET posts_status = 'completed',
                        posts_completed_at = %s,
                        comments_status = CASE
                            WHEN archive_comments THEN 'pending'
                            ELSE 'skipped'
                        END,
                        posts_pending_comments = (
                            SELECT COUNT(*)
                            FROM posts
                            WHERE subreddit = %s AND comment_fetch_status = 'pending'
                        )
                    WHERE name = %s
                    """,
                    (now, subreddit, subreddit)
                )

    def mark_comments_complete(self, subreddit: str):
        """Mark comments processing as completed for subreddit"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE subreddits
                    SET comments_status = 'completed',
                        comments_completed_at = %s,
                        posts_pending_comments = 0
                    WHERE name = %s
                    """,
                    (int(time.time()), subreddit)
                )

    def update_processing_tier_status(self, subreddit: str, tier: str, status: str):
        """Update tier status (pending, processing, completed, error). Tier is 'posts' or 'comments'."""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                tier_col = f'{tier}_status'
                cur.execute(
                    f"""
                    UPDATE subreddits
                    SET {tier_col} = %s
                    WHERE name = %s
                    """,
                    (status, subreddit)
                )

    def update_posts_pending_comments(self, subreddit: str):
        """Recalculate and update posts_pending_comments count"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE subreddits
                    SET posts_pending_comments = (
                        SELECT COUNT(*)
                        FROM posts
                        WHERE subreddit = %s AND comment_fetch_status = 'pending'
                    )
                    WHERE name = %s
                    """,
                    (subreddit, subreddit)
                )

    # Scanner state operations

    def get_scanner_state(self) -> Dict:
        """Get global scanner state"""
        with self.get_connection() as conn:
            with conn.cursor(cursor_factory=extras.RealDictCursor) as cur:
                cur.execute("SELECT * FROM scanner_state WHERE id = 1")
                row = cur.fetchone()
                return dict(row) if row else {}

    def update_scanner_state(self, **kwargs):
        """Update scanner state fields"""
        if not kwargs:
            return

        set_clause = ', '.join(f"{k} = %s" for k in kwargs.keys())
        values = list(kwargs.values())

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE scanner_state
                    SET {set_clause}, updated_at = %s
                    WHERE id = 1
                    """,
                    values + [int(time.time())]
                )

    def update_processing_tier_activity(self, tier: str):
        """Record activity for a tier ('posts' or 'comments')"""
        field = f'last_{tier}_activity'
        self.update_scanner_state(**{field: int(time.time())})

    def increment_processing_tier_processed(self, tier: str, count: int = 1):
        """Increment processed count for tier ('posts' or 'comments')"""
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                field = f'{tier}_subs_processed' if tier == 'posts' else f'{tier}_posts_processed'
                cur.execute(
                    f"""
                    UPDATE scanner_state
                    SET {field} = {field} + %s,
                        updated_at = %s
                    WHERE id = 1
                    """,
                    (count, int(time.time()))
                )

    def check_pause(self) -> Optional[int]:
        """Check if scanner is paused, returns seconds remaining"""
        state = self.get_scanner_state()
        pause_until = state.get('pause_until')
        if not pause_until:
            return None

        now = int(time.time())
        if now < pause_until:
            return pause_until - now
        return None

    def set_pause(self, duration_seconds: int):
        """Pause scanner for specified duration"""
        pause_until = int(time.time()) + duration_seconds
        self.update_scanner_state(pause_until=pause_until)
        logger.info(f"Scanner paused for {duration_seconds}s")

    def clear_pause(self):
        """Clear pause"""
        self.update_scanner_state(pause_until=None)

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
