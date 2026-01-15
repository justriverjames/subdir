import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class MetadataProcessor:
    """Fetch and store subreddit metadata"""

    def __init__(self, reddit_client, database):
        self.reddit = reddit_client
        self.db = database

    async def process_subreddit(self, subreddit_name: str) -> bool:
        """
        Fetch metadata for a subreddit and store in database.

        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Fetching metadata for r/{subreddit_name}")

        result = await self.reddit.get_subreddit_about(subreddit_name)
        status = result['status']
        data = result['data']

        if status == 'active':
            # Parse metadata
            metadata = self._parse_metadata(data)

            # Store in database
            self.db.update_subreddit_metadata(subreddit_name, metadata)

            logger.info(
                f"✓ r/{subreddit_name} - {metadata.get('subscribers', 0):,} subscribers"
            )
            return True

        elif status in ['notfound', 'deleted']:
            # Remove from database
            self.db.update_subreddit_status(subreddit_name, 'deleted', 'Subreddit not found or deleted')
            logger.warning(f"✗ r/{subreddit_name} - not found (404)")
            return False

        elif status == 'private':
            self.db.update_subreddit_status(subreddit_name, 'private', 'Private subreddit')
            logger.warning(f"✗ r/{subreddit_name} - private")
            return False

        elif status == 'quarantined':
            self.db.update_subreddit_status(subreddit_name, 'quarantined', 'Quarantined subreddit')
            logger.warning(f"✗ r/{subreddit_name} - quarantined")
            return False

        else:
            self.db.update_subreddit_status(subreddit_name, 'error', f'Unknown status: {status}')
            logger.error(f"✗ r/{subreddit_name} - error ({status})")
            return False

    def _parse_metadata(self, data: Dict) -> Dict[str, Any]:
        """
        Parse Reddit API response into metadata dict.
        Extracts key fields for database storage.
        """
        # Extract icon URL
        icon_url = None
        if data.get('community_icon'):
            # Decode HTML entities
            icon_url = data['community_icon'].replace('&amp;', '&')
        elif data.get('icon_img'):
            icon_url = data['icon_img']

        # Extract banner URL
        banner_url = data.get('banner_background_image') or data.get('banner_img')
        if banner_url:
            banner_url = banner_url.replace('&amp;', '&').split('?')[0]  # Remove query params

        metadata = {
            'display_name': data.get('display_name'),
            'title': data.get('title'),
            'public_description': data.get('public_description'),
            'description': data.get('description'),

            'subscribers': data.get('subscribers', 0),
            'active_user_count': data.get('active_user_count', 0),
            'created_utc': int(data.get('created_utc', 0)),

            'icon_url': icon_url,
            'banner_img': banner_url,
            'primary_color': data.get('primary_color'),
            'key_color': data.get('key_color'),

            'over18': data.get('over18', False),
            'subreddit_type': data.get('subreddit_type'),

            # Additional fields for future use
            'allow_images': data.get('allow_images'),
            'allow_videos': data.get('allow_videos'),
            'allow_videogifs': data.get('allow_videogifs'),
            'allow_galleries': data.get('allow_galleries'),
            'spoilers_enabled': data.get('spoilers_enabled'),
            'content_category': data.get('advertiser_category'),
        }

        return metadata
