import logging
import time
from typing import Dict, List, Any, Tuple
from urllib.parse import urlparse, unquote
from psycopg2 import extras as pg_extras

logger = logging.getLogger(__name__)


class PostsProcessor:
    """
    Fetch posts from Reddit and store in database.
    Extracts media URLs during post processing (not as separate phase).
    """

    def __init__(self, reddit_client, database, config):
        self.reddit = reddit_client
        self.db = database
        self.config = config

    async def process_subreddit(self, subreddit_name: str) -> Tuple[int, int]:
        """
        Fetch, store posts, and extract media URLs for a subreddit.

        Returns:
            Tuple of (unique posts count, media URLs count)
        """
        logger.info(f"Fetching posts for r/{subreddit_name}")

        all_posts = {}
        all_media_urls = []

        # Fetch top 1000 all-time
        self.db.update_processing_state(
            subreddit_name,
            'posts',
            {'step': 'top_all', 'current': 0, 'total': 2000}
        )

        top_all = await self.reddit.get_posts(
            subreddit_name,
            listing_type='top',
            time_filter='all',
            limit=1000
        )

        for post in top_all:
            post_id = post['id']
            parsed, media_urls = self._parse_post_with_media(post, subreddit_name)
            parsed['source_listing'] = 'top_all'
            all_posts[post_id] = parsed
            all_media_urls.extend(media_urls)

        # Fetch hot 1000
        self.db.update_processing_state(
            subreddit_name,
            'posts',
            {'step': 'hot', 'current': len(top_all), 'total': 2000}
        )

        hot_posts = await self.reddit.get_posts(
            subreddit_name,
            listing_type='hot',
            limit=1000
        )

        for post in hot_posts:
            post_id = post['id']
            if post_id in all_posts:
                all_posts[post_id]['source_listing'] = 'both'
            else:
                parsed, media_urls = self._parse_post_with_media(post, subreddit_name)
                parsed['source_listing'] = 'hot'
                all_posts[post_id] = parsed
                all_media_urls.extend(media_urls)

        # Store posts and media URLs
        posts_list = list(all_posts.values())
        if posts_list:
            self.db.add_posts(posts_list)

        if all_media_urls:
            self.db.add_media_urls(all_media_urls)

        logger.info(
            f"✓ r/{subreddit_name} - {len(all_posts):,} posts, "
            f"{len(all_media_urls):,} media URLs "
            f"(top: {len(top_all)}, hot: {len(hot_posts)})"
        )

        return len(all_posts), len(all_media_urls)

    def _parse_post_with_media(self, post: Dict, subreddit_name: str) -> Tuple[Dict[str, Any], List[Dict]]:
        """
        Parse Reddit post and extract media URLs from raw API data.
        Returns (parsed_post, media_urls_list)
        """
        post_id = post['id']
        post_type = self._determine_post_type(post)

        # Extract media URLs from raw API data
        media_urls = self._extract_media_urls(post_id, post)

        edited_utc = None
        if post.get('edited') and isinstance(post['edited'], (int, float)):
            edited_utc = int(post['edited'])

        parsed = {
            'id': post_id,
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
            'media_extracted': True,  # Already extracted!

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

        return parsed, media_urls

    def _extract_media_urls(self, post_id: str, post: Dict) -> List[Dict]:
        """
        Extract media URLs from raw Reddit API post data.
        Based on Redditarr's working implementation.
        """
        media_urls = []
        url = post.get('url', '')

        # Skip external-preview URLs (ephemeral thumbnails)
        if 'external-preview.redd.it' in url.lower():
            return media_urls

        # RedGifs
        if 'redgifs.com' in url.lower():
            media_urls.append(self._make_media_dict(post_id, url, 'video', 'redgifs', 0))
            return media_urls

        # Imgur .gifv → .mp4
        if 'imgur.com' in url.lower() and url.lower().endswith('.gifv'):
            media_urls.append(self._make_media_dict(post_id, url.replace('.gifv', '.mp4'), 'video', 'imgur', 0))
            return media_urls

        # Gfycat
        if 'gfycat.com' in url.lower():
            media_urls.append(self._make_media_dict(post_id, url, 'video', 'gfycat', 0))
            return media_urls

        # Gallery posts
        if post.get('is_gallery'):
            gallery_data = post.get('gallery_data', {})
            media_metadata = post.get('media_metadata', {})

            if gallery_data and media_metadata:
                for position, item in enumerate(gallery_data.get('items', [])):
                    media_id = item.get('media_id')
                    if media_id and media_id in media_metadata:
                        media_item = media_metadata[media_id]
                        if media_item.get('status') == 'valid':
                            # Get highest quality: 's' key or largest from 'p' array
                            hq = media_item.get('s')
                            if not hq and media_item.get('p'):
                                hq = sorted(media_item['p'], key=lambda x: x.get('x', 0), reverse=True)[0]
                            if hq and hq.get('u'):
                                media_urls.append(self._make_media_dict(
                                    post_id,
                                    unquote(hq['u'].replace('&amp;', '&')),
                                    media_item.get('e', 'image').lower(),
                                    'reddit',
                                    position,
                                    hq.get('x'),
                                    hq.get('y')
                                ))
            return media_urls

        # Video posts
        if post.get('is_video'):
            media = post.get('media', {})
            if media:
                reddit_video = media.get('reddit_video', {})
                if reddit_video and reddit_video.get('fallback_url'):
                    media_urls.append(self._make_media_dict(
                        post_id,
                        reddit_video['fallback_url'],
                        'video',
                        'reddit',
                        0,
                        reddit_video.get('width'),
                        reddit_video.get('height'),
                        reddit_video.get('duration')
                    ))
            return media_urls

        # Direct image links with extension
        if any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.webm']):
            media_type = 'video' if url.lower().endswith(('.mp4', '.webm')) else 'image'
            media_urls.append(self._make_media_dict(post_id, url, media_type, self._get_domain(url), 0))
            return media_urls

        # i.redd.it URLs
        if 'i.redd.it' in url:
            media_urls.append(self._make_media_dict(post_id, url, 'image', 'reddit', 0))
            return media_urls

        # Imgur without extension
        if 'imgur.com' in url.lower():
            if '/a/' not in url and '/gallery/' not in url:
                url = f"{url}.jpg"
            media_urls.append(self._make_media_dict(post_id, url, 'image', 'imgur', 0))
            return media_urls

        # Fallback: Reddit-hosted preview images
        preview = post.get('preview', {})
        if preview and preview.get('images'):
            source = preview['images'][0].get('source', {})
            source_url = source.get('url', '')
            if source_url and ('i.redd.it' in source_url or 'preview.redd.it' in source_url) and 'external-preview' not in source_url:
                media_urls.append(self._make_media_dict(
                    post_id,
                    unquote(source_url.replace('&amp;', '&')),
                    'image',
                    'reddit',
                    0,
                    source.get('width'),
                    source.get('height')
                ))

        return media_urls

    def _make_media_dict(self, post_id: str, url: str, media_type: str, source: str,
                         position: int, width: int = None, height: int = None,
                         duration: int = None) -> Dict:
        return {
            'post_id': post_id,
            'url': url,
            'media_type': media_type,
            'source': source,
            'position': position,
            'width': width,
            'height': height,
            'duration': duration,
            'status': 'pending',
            'extracted_at': int(time.time())
        }

    def _get_domain(self, url: str) -> str:
        try:
            return urlparse(url).netloc.lower()
        except:
            return ''

    def _determine_post_type(self, post: Dict) -> str:
        if post.get('is_self'):
            return 'self'
        if post.get('is_video'):
            return 'video'
        if post.get('is_gallery'):
            return 'gallery'
        if post.get('crosspost_parent_list'):
            return 'crosspost'

        url = post.get('url', '')
        if any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp']):
            return 'image'
        if any(d in url for d in ['i.redd.it', 'imgur.com', 'i.imgur.com']):
            return 'image'
        if any(d in url for d in ['v.redd.it', 'youtube.com', 'youtu.be', 'vimeo.com']):
            return 'video'

        return 'link'
