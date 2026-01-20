import logging
import time
from typing import Dict, List, Any, Optional
from urllib.parse import urlparse, unquote

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

        # Log first few posts at INFO level to trace flow
        if post_id in ['1qedwmg', '1qef7ce', '1qefg3r']:  # First 3 posts from query
            logger.info(f"TRACE post {post_id}: is_video={post_data.get('is_video')}, is_gallery={post_data.get('is_gallery')}, url={post_data.get('url', 'NONE')[:50] if post_data.get('url') else 'NONE'}")

        # Early exclusion: external-preview.redd.it URLs are ephemeral thumbnails
        url = post_data.get('url', '')
        if 'external-preview.redd.it' in url.lower():
            logger.debug(f"Skipping external-preview URL for post {post_id}")
            return 0

        # Handle RedGifs URLs (store original, resolve later)
        if 'redgifs.com' in url.lower():
            media_urls.append({
                'post_id': post_id,
                'url': url,
                'media_type': 'video',
                'source': 'redgifs',
                'position': 0,
                'width': None,
                'height': None,
                'duration': None,
                'status': 'pending',
                'extracted_at': int(time.time())
            })
            if media_urls:
                self.db.add_media_urls(media_urls)
            return len(media_urls)

        # Handle Imgur .gifv (convert to .mp4)
        if 'imgur.com' in url.lower() and url.lower().endswith('.gifv'):
            url = url.replace('.gifv', '.mp4')
            media_urls.append({
                'post_id': post_id,
                'url': url,
                'media_type': 'video',
                'source': 'imgur',
                'position': 0,
                'width': None,
                'height': None,
                'duration': None,
                'status': 'pending',
                'extracted_at': int(time.time())
            })
            if media_urls:
                self.db.add_media_urls(media_urls)
            return len(media_urls)

        # Extract based on post type
        if post_data.get('is_video'):
            logger.info(f"TRACE {post_id}: Extracting video")
            media_urls.extend(self._extract_video_urls(post_id, post_data))
        elif post_data.get('is_gallery'):
            logger.info(f"TRACE {post_id}: Extracting gallery")
            media_urls.extend(self._extract_gallery_urls(post_id, post_data))
        elif self._is_image_url(post_data.get('url', '')):
            logger.info(f"TRACE {post_id}: Extracting image from {post_data.get('url', '')[:50]}")
            media_urls.extend(self._extract_image_url(post_id, post_data))
        else:
            logger.info(f"TRACE {post_id}: Extracting embedded (fallback)")
            # Check for embedded media
            media_urls.extend(self._extract_embedded_media(post_id, post_data))

        # Clean up URLs - unescape HTML entities and URL encoding
        for item in media_urls:
            if item.get('url'):
                item['url'] = unquote(item['url'].replace('&amp;', '&'))

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
                'width': None,
                'height': None,
                'duration': None,
                'status': 'pending',
                'extracted_at': int(time.time())
            })

        return urls

    def _extract_gallery_urls(self, post_id: str, post_data: Dict) -> List[Dict]:
        """Extract URLs from gallery posts with quality selection"""
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

            media_item = media_metadata[media_id]

            # Skip invalid items
            if media_item.get('status') != 'valid':
                continue

            # Get highest quality version - check 's' first, then 'p' array
            highest_quality = None
            if 's' in media_item:
                highest_quality = media_item['s']
            elif 'p' in media_item:
                # Sort by width (x) to get highest quality
                highest_quality = sorted(
                    media_item['p'],
                    key=lambda x: x.get('x', 0),
                    reverse=True
                )[0]

            if highest_quality:
                url = highest_quality.get('u')
                if url:
                    # Note: URL cleaning happens in process_post() after all extraction
                    urls.append({
                        'post_id': post_id,
                        'url': url,
                        'media_type': media_item.get('e', 'Image').lower(),
                        'source': 'reddit',
                        'position': position,
                        'width': highest_quality.get('x'),
                        'height': highest_quality.get('y'),
                        'duration': None,
                        'status': 'pending',
                        'extracted_at': int(time.time())
                    })

        return urls

    def _extract_image_url(self, post_id: str, post_data: Dict) -> List[Dict]:
        """Extract single image URL with special handling for i.redd.it and Imgur"""
        url = post_data.get('url', '')
        if not url or not self._is_image_url(url):
            return []

        # Prioritize i.redd.it URLs (Reddit's CDN - direct use)
        if 'i.redd.it' in url:
            # Note: URL cleaning happens in process_post()
            return [{
                'post_id': post_id,
                'url': url,
                'media_type': 'image',
                'source': 'reddit',
                'position': 0,
                'width': None,
                'height': None,
                'duration': None,
                'status': 'pending',
                'extracted_at': int(time.time())
            }]

        # Handle Imgur links without extensions (add .jpg)
        if 'imgur.com' in url.lower():
            if not any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.mp4', '.webm']):
                if '/a/' not in url and '/gallery/' not in url:
                    url = f"{url}.jpg"

        # Try to get high-res version from preview for other URLs
        preview = post_data.get('preview', {})
        if preview:
            images = preview.get('images', [])
            if images:
                source = images[0].get('source', {})
                preview_url = source.get('url')
                if preview_url:
                    # Note: URL cleaning happens in process_post()
                    url = preview_url

        return [{
            'post_id': post_id,
            'url': url,
            'media_type': 'image',
            'source': self._get_domain(url),
            'position': 0,
            'width': None,
            'height': None,
            'duration': None,
            'status': 'pending',
            'extracted_at': int(time.time())
        }]

    def _extract_embedded_media(self, post_id: str, post_data: Dict) -> List[Dict]:
        """Extract media from preview - only Reddit-hosted content"""
        urls = []

        # Check preview for images
        preview = post_data.get('preview', {})
        if preview:
            images = preview.get('images', [])
            for image in images:
                source = image.get('source', {})
                source_url = source.get('url', '')

                # Only use Reddit-hosted content, exclude ephemeral previews
                # Accept: i.redd.it, preview.redd.it
                # Reject: external-preview.redd.it (ephemeral thumbnails)
                if source_url and ('i.redd.it' in source_url or 'preview.redd.it' in source_url) and 'external-preview' not in source_url:
                    # Note: URL cleaning happens in process_post()
                    urls.append({
                        'post_id': post_id,
                        'url': source_url,
                        'media_type': 'image',
                        'source': 'reddit',
                        'position': 0,
                        'width': source.get('width'),
                        'height': source.get('height'),
                        'duration': None,
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

        logger.info(f"Processing {len(posts)} posts for media extraction")

        total_media = 0
        posts_with_media = 0
        for i, post in enumerate(posts, 1):
            # Post dict now contains both columns and merged metadata
            media_count = self.process_post(post['id'], post)
            if media_count > 0:
                posts_with_media += 1
                total_media += media_count

            # Mark as extracted
            self.db.update_post_media_extracted(post['id'])

            # Log progress every 100 posts
            if i % 100 == 0:
                logger.info(f"  Processed {i}/{len(posts)} posts, found {total_media} media URLs so far")

        logger.info(f"✓ r/{subreddit_name} - {total_media:,} media URLs from {posts_with_media}/{len(posts)} posts")

        return total_media
