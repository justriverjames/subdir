import logging
import re
import time
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class CommentsProcessor:
    """
    Fetch comments with materialized paths and bot filtering.
    Based on redditarr's approach.
    """

    # Bot username patterns
    BOT_PATTERNS = [
        r'.*bot$',
        r'^auto.*',
        r'^bot.*',
        r'.*_bot$',
        r'^moderator$',
        r'.*helper$',
        r'sneakpeekbot',
        r'remindmebot',
        r'converter.*bot',
        r'.*scraper.*',
    ]

    def __init__(self, reddit_client, database, config):
        self.reddit = reddit_client
        self.db = database
        self.config = config
        self.progress_update_interval = 10  # Update progress every N posts

    async def process_post(self, subreddit_name: str, post_id: str, post_title: str) -> int:
        """
        Fetch and store comments for a single post.

        Returns:
            Number of comments stored
        """
        logger.debug(f"Fetching comments for post {post_id} in r/{subreddit_name}")

        url = f'https://oauth.reddit.com/r/{subreddit_name}/comments/{post_id}'
        params = {
            'limit': self.config.max_comments_per_post,
            'depth': self.config.max_comment_depth,
            'raw_json': 1,
            'sort': 'top'  # Get highest quality comments first
        }

        try:
            response = await self.reddit.get(url, params=params)

            if response.status != 200:
                logger.warning(f"Failed to fetch comments for {post_id}: {response.status}")
                return 0

            data = await response.json()

            # data[0] is post listing, data[1] is comment listing
            if len(data) < 2:
                logger.warning(f"Unexpected response format for {post_id}")
                return 0

            comment_listing = data[1]['data']['children']

            # Parse comment tree
            comments = []
            for comment_data in comment_listing:
                if comment_data['kind'] == 't1':  # Comment (not 'more' object)
                    parsed = self._parse_comment_tree(
                        comment_data['data'],
                        parent_path='root',
                        current_depth=0
                    )
                    comments.extend(parsed)

            # Filter bots
            if self.config.filter_bots:
                before = len(comments)
                comments = [c for c in comments if not self._is_bot(c['author'])]
                filtered = before - len(comments)
                if filtered > 0:
                    logger.debug(f"Filtered {filtered} bot comments from {post_id}")

            # Store in database
            if comments:
                self.db.add_comments(comments)

            logger.debug(f"Stored {len(comments)} comments for {post_id}")
            return len(comments)

        except Exception as e:
            logger.error(f"Error fetching comments for {post_id}: {e}")
            return 0

    def _parse_comment_tree(self, comment: Dict, parent_path: str, current_depth: int) -> List[Dict]:
        """
        Recursively parse comment tree and build materialized paths.
        Returns flat list of comments with path info.
        """
        comments = []

        # Stop if max depth reached
        if current_depth >= self.config.max_comment_depth:
            return comments

        comment_id = comment.get('id')
        if not comment_id:
            return comments

        path = f"{parent_path}.{comment_id}"

        # Parse edited timestamp
        edited_utc = None
        if comment.get('edited') and isinstance(comment['edited'], (int, float)):
            edited_utc = int(comment['edited'])

        # Add this comment
        comments.append({
            'id': comment_id,
            'post_id': comment.get('link_id', '').replace('t3_', ''),
            'parent_id': comment.get('parent_id', '').replace('t1_', '').replace('t3_', ''),
            'author': comment.get('author', '[deleted]'),
            'body': comment.get('body', ''),
            'body_html': comment.get('body_html', ''),
            'created_utc': int(comment.get('created_utc', 0)),
            'edited_utc': edited_utc,
            'archived_at': int(time.time()),
            'score': comment.get('score', 0),
            'controversiality': comment.get('controversiality', 0),
            'gilded': comment.get('gilded', 0),
            'depth': current_depth,
            'path': path,
            'stickied': comment.get('stickied', False),
            'is_submitter': comment.get('is_submitter', False),
            'score_hidden': comment.get('score_hidden', False),
            'distinguished': comment.get('distinguished'),
            'is_bot': False  # Will be set by filter
        })

        # Parse replies
        replies = comment.get('replies', {})
        if isinstance(replies, dict) and 'data' in replies:
            children = replies['data'].get('children', [])
            for child in children:
                if child['kind'] == 't1':  # Comment (not 'more' object)
                    child_comments = self._parse_comment_tree(
                        child['data'],
                        parent_path=path,
                        current_depth=current_depth + 1
                    )
                    comments.extend(child_comments)

        return comments

    def _is_bot(self, username: str) -> bool:
        """Check if username matches bot patterns"""
        if not username or username == '[deleted]':
            return False

        username_lower = username.lower()
        for pattern in self.BOT_PATTERNS:
            if re.match(pattern, username_lower):
                return True

        return False

    async def process_subreddit_posts(self, subreddit_name: str) -> int:
        """
        Fetch comments for all posts in a subreddit that need comments.

        Returns:
            Total number of comments stored
        """
        logger.info(f"Fetching comments for r/{subreddit_name} posts")

        # Get posts that need comments
        posts = self.db.get_posts_for_comments(
            subreddit_name,
            limit=self.config.max_posts_per_subreddit
        )

        if not posts:
            logger.info(f"No posts need comments for r/{subreddit_name}")
            return 0

        logger.info(f"Fetching comments for {len(posts)} posts in r/{subreddit_name}")

        total_comments = 0
        for i, post in enumerate(posts, 1):
            comment_count = await self.process_post(
                subreddit_name,
                post['id'],
                post['title']
            )

            total_comments += comment_count

            # Update post comment status
            self.db.update_post_comment_status(
                post['id'],
                'completed',
                comment_count
            )

            # Update progress in database every N posts
            if i % self.progress_update_interval == 0 or i == len(posts):
                self.db.update_processing_state(
                    subreddit_name,
                    'comments',
                    {
                        'current': i,
                        'total': len(posts),
                        'percent': round((i / len(posts)) * 100, 1),
                        'comments_fetched': total_comments
                    }
                )

            # Progress log every 50 posts
            if i % 50 == 0:
                logger.info(
                    f"r/{subreddit_name}: {i}/{len(posts)} posts processed, "
                    f"{total_comments} comments stored"
                )

        logger.info(
            f"✓ r/{subreddit_name} - {total_comments:,} comments from {len(posts)} posts"
        )

        return total_comments
