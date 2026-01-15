import aiohttp
import asyncio
import time
import logging
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


class RedditAPIClient:
    """
    Reddit API client with OAuth2 authentication.
    Handles token management, requests, and error handling.
    """

    def __init__(self, config, rate_limiter):
        self.config = config
        self.rate_limiter = rate_limiter

        self.access_token: Optional[str] = None
        self.token_expires_at: float = 0

        self.session: Optional[aiohttp.ClientSession] = None

        # Stats
        self.total_requests = 0
        self.failed_requests = 0
        self.rate_limit_hits = 0
        self.consecutive_403 = 0

    async def __aenter__(self):
        """Async context manager entry"""
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=5, force_close=False)
        self.session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        await self.authenticate()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.close()

    async def authenticate(self):
        """Authenticate with Reddit OAuth2 (password grant)"""
        logger.info("Authenticating with Reddit API")

        auth = aiohttp.BasicAuth(
            self.config.reddit_client_id,
            self.config.reddit_client_secret
        )

        data = {
            'grant_type': 'password',
            'username': self.config.reddit_username,
            'password': self.config.reddit_password
        }

        headers = {'User-Agent': self.config.user_agent}

        async with self.session.post(
            'https://www.reddit.com/api/v1/access_token',
            auth=auth,
            data=data,
            headers=headers
        ) as response:
            if response.status == 200:
                token_data = await response.json()
                self.access_token = token_data['access_token']
                expires_in = token_data['expires_in']
                self.token_expires_at = time.time() + expires_in - 60  # 60s buffer

                logger.info(f"Authentication successful, token expires in {expires_in}s")
            else:
                error = await response.text()
                raise Exception(f"Authentication failed: {response.status} - {error}")

    async def ensure_authenticated(self):
        """Check and refresh token if needed"""
        if time.time() >= self.token_expires_at:
            logger.info("Token expired, re-authenticating")
            await self.authenticate()

    async def request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        """
        Make authenticated request with rate limiting and retry logic.
        """
        await self.ensure_authenticated()
        await self.rate_limiter.wait_with_delay()

        headers = kwargs.pop('headers', {})
        headers['User-Agent'] = self.config.user_agent
        headers['Authorization'] = f'Bearer {self.access_token}'

        self.total_requests += 1

        try:
            response = await self.session.request(method, url, headers=headers, **kwargs)

            # Handle rate limiting
            if response.status == 429:
                self.rate_limit_hits += 1
                retry_after = int(response.headers.get('Retry-After', 60))
                logger.warning(f"Rate limit hit (429), waiting {retry_after}s")

                if self.rate_limit_hits >= self.config.max_total_429:
                    raise Exception(f"Too many rate limit hits ({self.rate_limit_hits}), stopping")

                await asyncio.sleep(retry_after)
                return await self.request(method, url, **kwargs)

            # Handle 403 (forbidden/deleted)
            if response.status == 403:
                self.consecutive_403 += 1
                if self.consecutive_403 >= self.config.max_consecutive_403:
                    raise Exception(f"Too many consecutive 403s ({self.consecutive_403}), stopping")

            # Reset 403 counter on success
            if response.status == 200:
                self.consecutive_403 = 0

            return response

        except Exception as e:
            self.failed_requests += 1
            logger.error(f"Request failed: {method} {url} - {e}")
            raise

    async def get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """GET request"""
        return await self.request('GET', url, **kwargs)

    async def post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """POST request"""
        return await self.request('POST', url, **kwargs)

    # High-level API methods

    async def get_subreddit_about(self, subreddit: str) -> Dict[str, Any]:
        """
        Fetch subreddit metadata.
        Returns dict with 'status' and 'data' keys.
        """
        url = f'https://oauth.reddit.com/r/{subreddit}/about'

        try:
            response = await self.get(url, params={'raw_json': 1})

            if response.status == 200:
                data = await response.json()
                return {
                    'status': 'active',
                    'data': data['data']
                }
            elif response.status == 404:
                return {
                    'status': 'notfound',
                    'data': None
                }
            elif response.status == 403:
                # Could be private, quarantined, or deleted
                text = await response.text()
                if 'private' in text.lower():
                    return {'status': 'private', 'data': None}
                elif 'quarantine' in text.lower():
                    return {'status': 'quarantined', 'data': None}
                else:
                    return {'status': 'deleted', 'data': None}
            else:
                logger.warning(f"Unexpected status {response.status} for r/{subreddit}")
                return {
                    'status': 'error',
                    'data': None
                }

        except Exception as e:
            logger.error(f"Error fetching r/{subreddit}: {e}")
            return {
                'status': 'error',
                'data': None
            }

    async def get_posts(
        self,
        subreddit: str,
        listing_type: str = 'hot',
        time_filter: Optional[str] = None,
        limit: int = 1000
    ) -> List[Dict]:
        """
        Fetch posts from a listing with pagination.

        Args:
            subreddit: Subreddit name
            listing_type: 'hot', 'top', 'new', 'rising'
            time_filter: For 'top': 'all', 'year', 'month', 'week', 'day'
            limit: Total posts to fetch

        Returns:
            List of post dicts
        """
        posts = []
        after = None
        per_page = 100

        pages_needed = (limit + per_page - 1) // per_page

        for page in range(pages_needed):
            url = f'https://oauth.reddit.com/r/{subreddit}/{listing_type}'
            params = {
                'limit': min(per_page, limit - len(posts)),
                'raw_json': 1
            }

            if time_filter:
                params['t'] = time_filter
            if after:
                params['after'] = after

            try:
                response = await self.get(url, params=params)

                if response.status != 200:
                    logger.warning(
                        f"Failed to fetch {listing_type} for r/{subreddit}: {response.status}"
                    )
                    break

                data = await response.json()
                children = data['data']['children']

                for child in children:
                    if child['kind'] == 't3':  # Post
                        posts.append(child['data'])

                after = data['data']['after']
                if not after:
                    break  # No more pages

                logger.debug(
                    f"r/{subreddit} {listing_type}: page {page + 1}/{pages_needed}, "
                    f"{len(posts)} posts"
                )

            except Exception as e:
                logger.error(f"Error fetching {listing_type} for r/{subreddit}: {e}")
                break

        return posts[:limit]

    def get_stats(self) -> Dict:
        """Get API client statistics"""
        return {
            'total_requests': self.total_requests,
            'failed_requests': self.failed_requests,
            'success_rate': (
                round((self.total_requests - self.failed_requests) / self.total_requests * 100, 1)
                if self.total_requests > 0 else 0
            ),
            'rate_limit_hits': self.rate_limit_hits,
            'consecutive_403': self.consecutive_403
        }
