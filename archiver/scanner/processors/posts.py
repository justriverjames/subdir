import logging
import time
from typing import Dict, List, Any
from psycopg2 import extras as pg_extras

logger = logging.getLogger(__name__)


class PostsProcessor:
    """
    Fetch posts from Reddit and store in database.
    Implements: top 1000 all-time + hot 1000, merge and deduplicate.
    """

    def __init__(self, reddit_client, database, config):
        self.reddit = reddit_client
        self.db = database
        self.config = config

    async def process_subreddit(self, subreddit_name: str) -> int:
        """
        Fetch and store posts for a subreddit.

        Returns top 1000 all-time + hot 1000, merged and deduplicated.

        Returns:
            Number of unique posts stored
        """
        logger.info(f"Fetching posts for r/{subreddit_name}")

        all_posts = {}

        # Fetch top 1000 all-time
        logger.debug(f"r/{subreddit_name}: fetching top 1000 all-time")
        top_all = await self.reddit.get_posts(
            subreddit_name,
            listing_type='top',
            time_filter='all',
            limit=1000
        )

        for post in top_all:
            post_id = post['id']
            all_posts[post_id] = {
                **self._parse_post(post, subreddit_name),
                'source_listing': 'top_all'
            }

        logger.debug(f"r/{subreddit_name}: fetched {len(top_all)} from top/all")

        # Fetch hot 1000
        logger.debug(f"r/{subreddit_name}: fetching hot 1000")
        hot_posts = await self.reddit.get_posts(
            subreddit_name,
            listing_type='hot',
            limit=1000
        )

        # Merge with deduplication
        for post in hot_posts:
            post_id = post['id']
            if post_id in all_posts:
                # Found in both listings
                all_posts[post_id]['source_listing'] = 'both'
            else:
                all_posts[post_id] = {
                    **self._parse_post(post, subreddit_name),
                    'source_listing': 'hot'
                }

        logger.debug(f"r/{subreddit_name}: fetched {len(hot_posts)} from hot")

        # Store in database
        posts_list = list(all_posts.values())
        if posts_list:
            self.db.add_posts(posts_list)

        logger.info(
            f"✓ r/{subreddit_name} - {len(all_posts):,} unique posts "
            f"(top: {len(top_all)}, hot: {len(hot_posts)})"
        )

        return len(all_posts)

    def _parse_post(self, post: Dict, subreddit_name: str) -> Dict[str, Any]:
        """
        Parse Reddit post data into database format.
        """
        # Determine post type
        post_type = self._determine_post_type(post)

        # Parse edited timestamp
        edited_utc = None
        if post.get('edited') and isinstance(post['edited'], (int, float)):
            edited_utc = int(post['edited'])

        parsed = {
            'id': post['id'],
            'subreddit': subreddit_name.lower(),
            'author': post.get('author', '[deleted]'),
            'title': post.get('title', ''),
            'selftext': post.get('selftext', ''),
            'url': post.get('url'),
            'domain': post.get('domain'),

            'post_type': post_type,
            'is_self': post.get('is_self', False),
            'is_video': post.get('is_video', False),

            'created_utc': int(post.get('created_utc', 0)),
            'edited_utc': edited_utc,
            'archived_at': int(time.time()),

            'score': post.get('score', 0),
            'upvote_ratio': post.get('upvote_ratio'),
            'num_comments': post.get('num_comments', 0),
            'num_crossposts': post.get('num_crossposts', 0),

            'over_18': post.get('over_18', False),
            'spoiler': post.get('spoiler', False),
            'stickied': post.get('stickied', False),
            'locked': post.get('locked', False),
            'archived': post.get('archived', False),

            'link_flair_text': post.get('link_flair_text'),
            'link_flair_css_class': post.get('link_flair_css_class'),
            'author_flair_text': post.get('author_flair_text'),

            'comment_fetch_status': 'pending',
            'comment_count_archived': 0,
            'media_extracted': False,

            'metadata': pg_extras.Json({
                'permalink': post.get('permalink'),
                'thumbnail': post.get('thumbnail'),
                'preview': post.get('preview', {}),
                'media': post.get('media'),
                'media_metadata': post.get('media_metadata'),
                'gallery_data': post.get('gallery_data'),
                'crosspost_parent_list': post.get('crosspost_parent_list'),
            })
        }

        return parsed

    def _determine_post_type(self, post: Dict) -> str:
        """
        Determine post type from post data.
        Returns: 'link', 'self', 'image', 'video', 'gallery', 'crosspost'
        """
        if post.get('is_self'):
            return 'self'

        if post.get('is_video'):
            return 'video'

        if post.get('is_gallery'):
            return 'gallery'

        if post.get('crosspost_parent_list'):
            return 'crosspost'

        # Check URL for media types
        url = post.get('url', '')
        domain = post.get('domain', '')

        if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            return 'image'

        if any(domain in url for domain in ['i.redd.it', 'imgur.com', 'i.imgur.com']):
            return 'image'

        if any(domain in url for domain in ['v.redd.it', 'youtube.com', 'youtu.be', 'vimeo.com']):
            return 'video'

        return 'link'
