import logging
import time
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class MediaProcessor:
    """
    Extract media URLs from posts for future downloading.
    Does NOT download files, just stores URLs and metadata.
    """

    def __init__(self, database):
        self.db = database

    def process_post(self, post_id: str, post_data: Dict) -> int:
        """
        Extract media URLs from a post.

        Returns:
            Number of media URLs extracted
        """
        media_urls = []

        # Extract based on post type
        if post_data.get('is_video'):
            media_urls.extend(self._extract_video_urls(post_id, post_data))
        elif post_data.get('is_gallery'):
            media_urls.extend(self._extract_gallery_urls(post_id, post_data))
        elif self._is_image_url(post_data.get('url', '')):
            media_urls.extend(self._extract_image_url(post_id, post_data))
        else:
            # Check for embedded media
            media_urls.extend(self._extract_embedded_media(post_id, post_data))

        # Store in database
        if media_urls:
            self.db.add_media_urls(media_urls)
            logger.debug(f"Extracted {len(media_urls)} media URLs from post {post_id}")

        return len(media_urls)

    def _extract_video_urls(self, post_id: str, post_data: Dict) -> List[Dict]:
        """Extract video URLs from post"""
        urls = []

        # Reddit hosted video
        media = post_data.get('media', {})
        if media:
            reddit_video = media.get('reddit_video', {})
            if reddit_video:
                dash_url = reddit_video.get('dash_url')
                fallback_url = reddit_video.get('fallback_url')

                if fallback_url:
                    urls.append({
                        'post_id': post_id,
                        'url': fallback_url,
                        'media_type': 'video',
                        'source': 'reddit',
                        'position': 0,
                        'width': reddit_video.get('width'),
                        'height': reddit_video.get('height'),
                        'duration': reddit_video.get('duration'),
                        'status': 'pending',
                        'extracted_at': int(time.time())
                    })

        # External video (youtube, vimeo, etc.)
        url = post_data.get('url', '')
        if self._is_video_url(url):
            urls.append({
                'post_id': post_id,
                'url': url,
                'media_type': 'video',
                'source': self._get_domain(url),
                'position': 0,
                'status': 'pending',
                'extracted_at': int(time.time())
            })

        return urls

    def _extract_gallery_urls(self, post_id: str, post_data: Dict) -> List[Dict]:
        """Extract URLs from gallery posts"""
        urls = []

        gallery_data = post_data.get('gallery_data', {})
        media_metadata = post_data.get('media_metadata', {})

        if not gallery_data or not media_metadata:
            return urls

        items = gallery_data.get('items', [])

        for position, item in enumerate(items):
            media_id = item.get('media_id')
            if not media_id or media_id not in media_metadata:
                continue

            media_info = media_metadata[media_id]
            media_type = media_info.get('e')  # 'Image', 'AnimatedImage', etc.

            # Get highest quality image
            source = media_info.get('s', {})
            url = source.get('u') or source.get('gif') or source.get('mp4')

            if url:
                # Decode HTML entities
                url = url.replace('&amp;', '&')

                urls.append({
                    'post_id': post_id,
                    'url': url,
                    'media_type': 'gallery_item',
                    'source': 'reddit',
                    'position': position,
                    'width': source.get('x'),
                    'height': source.get('y'),
                    'status': 'pending',
                    'extracted_at': int(time.time())
                })

        return urls

    def _extract_image_url(self, post_id: str, post_data: Dict) -> List[Dict]:
        """Extract single image URL"""
        url = post_data.get('url', '')
        if not url or not self._is_image_url(url):
            return []

        # Try to get high-res version from preview
        preview = post_data.get('preview', {})
        if preview:
            images = preview.get('images', [])
            if images:
                source = images[0].get('source', {})
                preview_url = source.get('url')
                if preview_url:
                    url = preview_url.replace('&amp;', '&')

        return [{
            'post_id': post_id,
            'url': url,
            'media_type': 'image',
            'source': self._get_domain(url),
            'position': 0,
            'status': 'pending',
            'extracted_at': int(time.time())
        }]

    def _extract_embedded_media(self, post_id: str, post_data: Dict) -> List[Dict]:
        """Extract media from preview/thumbnail"""
        urls = []

        # Check preview for images
        preview = post_data.get('preview', {})
        if preview:
            images = preview.get('images', [])
            for image in images:
                source = image.get('source', {})
                url = source.get('url')
                if url:
                    url = url.replace('&amp;', '&')
                    urls.append({
                        'post_id': post_id,
                        'url': url,
                        'media_type': 'image',
                        'source': 'reddit',
                        'position': 0,
                        'width': source.get('width'),
                        'height': source.get('height'),
                        'status': 'pending',
                        'extracted_at': int(time.time())
                    })

        return urls

    def _is_image_url(self, url: str) -> bool:
        """Check if URL points to an image"""
        if not url:
            return False

        url_lower = url.lower()
        image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']

        # Check extension
        if any(url_lower.endswith(ext) for ext in image_extensions):
            return True

        # Check domain
        image_domains = ['i.redd.it', 'i.imgur.com', 'imgur.com']
        domain = self._get_domain(url)
        if any(img_domain in domain for img_domain in image_domains):
            return True

        return False

    def _is_video_url(self, url: str) -> bool:
        """Check if URL points to a video"""
        if not url:
            return False

        video_domains = [
            'youtube.com', 'youtu.be', 'vimeo.com',
            'twitch.tv', 'streamable.com',
            'redgifs.com', 'gfycat.com'
        ]

        domain = self._get_domain(url)
        return any(vid_domain in domain for vid_domain in video_domains)

    def _get_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            return parsed.netloc.lower()
        except:
            return ''

    def process_subreddit_posts(self, subreddit_name: str) -> int:
        """
        Extract media URLs from all posts in a subreddit.

        Returns:
            Total number of media URLs extracted
        """
        logger.info(f"Extracting media URLs for r/{subreddit_name}")

        # Get posts that need media extraction
        posts = self.db.get_posts_for_media_extraction(subreddit_name)

        if not posts:
            logger.info(f"No posts need media extraction for r/{subreddit_name}")
            return 0

        total_media = 0
        for post in posts:
            # Post metadata stored as JSONB
            media_count = self.process_post(post['id'], post['metadata'])
            total_media += media_count

            # Mark as extracted
            self.db.update_post_media_extracted(post['id'])

        logger.info(f"✓ r/{subreddit_name} - {total_media:,} media URLs from {len(posts)} posts")

        return total_media
