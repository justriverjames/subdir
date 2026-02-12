"""
Reddit API client for subreddit scanning.

Simplified Reddit client focused on subreddit metadata and thread ID collection.
"""

import httpx
import logging
import asyncio
import random
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple

# Local imports (works when run directly)
from config import Config
from rate_limiter import SlidingWindowRateLimiter, ExponentialBackoff


class RedditAPIClient:
    """
    Simplified Reddit API client for subreddit scanning.

    Handles authentication, rate limiting, and basic API operations.
    """

    def __init__(self, config: Config, rate_limiter: SlidingWindowRateLimiter):
        """
        Initialize Reddit API client.

        Args:
            config: Configuration object
            rate_limiter: Rate limiter instance
        """
        self.config = config
        self.rate_limiter = rate_limiter

        # Authentication
        self.client_id = config.reddit_client_id
        self.client_secret = config.reddit_client_secret
        self.username = config.reddit_username
        self.password = config.reddit_password
        self.user_agent = config.user_agent

        # Token management
        self.token: Optional[str] = None
        self.token_expires: Optional[datetime] = None

        # HTTP client
        self.client: Optional[httpx.AsyncClient] = None

        # Statistics
        self.total_requests = 0
        self.failed_requests = 0
        self.rate_limit_hits = 0
        self.diversity_requests = 0  # Count of non-metadata requests

        # Anti-detection settings
        self.min_delay = getattr(config, 'min_request_delay', 2.0)
        self.max_delay = getattr(config, 'max_request_delay', 8.0)
        self.request_diversity = getattr(config, 'request_diversity', True)

    async def initialize(self):
        """Initialize the client and authenticate."""
        self.client = httpx.AsyncClient(
            timeout=30.0,
            headers={"User-Agent": self.user_agent}
        )
        await self._authenticate()
        logging.debug("Reddit API client initialized")

    async def _authenticate(self):
        """Authenticate with Reddit and get access token."""
        try:
            auth = httpx.BasicAuth(self.client_id, self.client_secret)
            data = {
                'grant_type': 'password',
                'username': self.username,
                'password': self.password,
            }

            response = await self.client.post(
                'https://www.reddit.com/api/v1/access_token',
                auth=auth,
                data=data,
                headers={"User-Agent": self.user_agent}
            )
            response.raise_for_status()

            token_data = response.json()
            self.token = token_data['access_token']
            expires_in = token_data.get('expires_in', 3600)
            self.token_expires = datetime.now() + timedelta(seconds=expires_in - 60)

            logging.debug(f"Reddit authentication successful, token expires in {expires_in}s")

        except Exception as e:
            logging.error(f"Reddit authentication failed: {e}")
            raise

    async def _ensure_token_valid(self):
        """Ensure access token is valid, refresh if needed."""
        if not self.token or not self.token_expires:
            await self._authenticate()
            return

        if datetime.now() >= self.token_expires:
            logging.info("Access token expired, refreshing...")
            await self._authenticate()

    async def _random_delay(self):
        """Add random human-like delay between requests."""
        delay = random.uniform(self.min_delay, self.max_delay)
        logging.debug(f"Adding human-like delay: {delay:.2f}s")
        await asyncio.sleep(delay)

    async def _make_diversity_request(self):
        """Make a random non-metadata request to appear more human-like."""
        if not self.request_diversity:
            return

        # 20% chance to make a diversity request
        if random.random() > 0.2:
            return

        diversity_endpoints = [
            'https://oauth.reddit.com/hot',
            'https://oauth.reddit.com/new',
            'https://oauth.reddit.com/r/all/hot?limit=5',
            'https://oauth.reddit.com/r/popular/hot?limit=5',
        ]

        endpoint = random.choice(diversity_endpoints)
        try:
            await self._make_request('GET', endpoint, max_retries=1)
            self.diversity_requests += 1
            logging.debug(f"Made diversity request to {endpoint}")
        except Exception:
            pass  # Ignore failures for diversity requests

    async def _make_request(
        self,
        method: str,
        url: str,
        max_retries: int = 3,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Make an API request with rate limiting and error handling.

        Args:
            method: HTTP method
            url: Request URL
            max_retries: Maximum number of retries
            **kwargs: Additional request arguments

        Returns:
            Response JSON or None on failure
        """
        await self._ensure_token_valid()

        backoff = ExponentialBackoff()

        for attempt in range(max_retries):
            try:
                # Wait for rate limiter
                await self.rate_limiter.acquire()

                # Add random human-like delay
                await self._random_delay()

                # Make request
                headers = {
                    'Authorization': f'Bearer {self.token}',
                    **kwargs.get('headers', {})
                }
                kwargs['headers'] = headers

                response = await self.client.request(method, url, **kwargs)
                self.total_requests += 1

                # Handle rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logging.warning(f"Rate limit hit (429), waiting {retry_after}s")
                    self.rate_limit_hits += 1
                    await asyncio.sleep(retry_after)
                    continue

                # Handle token expiration
                if response.status_code == 401:
                    logging.info("Token expired (401), re-authenticating...")
                    self.token = None
                    await self._authenticate()
                    continue

                # Handle redirects (subreddit doesn't exist)
                if response.status_code == 302:
                    logging.debug(f"Redirect (302) for {url} - likely doesn't exist")
                    return None

                # Raise for other HTTP errors
                response.raise_for_status()

                return response.json()

            except httpx.HTTPStatusError as e:
                self.failed_requests += 1
                status = e.response.status_code

                if status == 404:
                    logging.debug(f"Not found (404): {url}")
                    return {'_http_status': 404}  # Return status code for differentiation
                elif status == 403:
                    logging.debug(f"Forbidden (403): {url} - likely private/quarantined")
                    return {'_http_status': 403}  # Return status code for differentiation
                elif status >= 500:
                    # Server error, retry with backoff
                    logging.warning(f"Server error ({status}) for {url}, retrying...")
                    await backoff.wait()
                    continue
                else:
                    logging.error(f"HTTP error ({status}) for {url}: {e}")
                    return None

            except Exception as e:
                self.failed_requests += 1
                logging.error(f"Request failed for {url}: {e}")

                if attempt < max_retries - 1:
                    await backoff.wait()
                    continue
                else:
                    return None

        logging.error(f"Max retries exceeded for {url}")
        return None

    async def get_subreddit_info(self, subreddit: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """
        Get subreddit information.

        Args:
            subreddit: Subreddit name

        Returns:
            Tuple of (metadata dict, status string)
            Status can be: 'active', 'private', 'banned', 'quarantined', 'deleted', 'error'
        """
        # Occasionally make diversity requests to look more organic
        await self._make_diversity_request()

        url = f'https://oauth.reddit.com/r/{subreddit}/about'

        try:
            data = await self._make_request('GET', url)

            if data is None:
                # General error
                return None, 'error'

            # Check for HTTP status markers
            if isinstance(data, dict) and '_http_status' in data:
                if data['_http_status'] == 404:
                    return None, 'notfound'
                elif data['_http_status'] == 403:
                    return None, 'deleted'

            if data and 'data' in data:
                subreddit_data = data['data']

                # Check if quarantined
                if subreddit_data.get('quarantine', False):
                    return subreddit_data, 'quarantined'

                # Check subreddit type
                sub_type = subreddit_data.get('subreddit_type', 'public')
                if sub_type == 'private':
                    return subreddit_data, 'private'

                return subreddit_data, 'active'

            return None, 'error'

        except Exception as e:
            logging.error(f"Error fetching subreddit info for r/{subreddit}: {e}")
            return None, 'error'

    async def get_thread_ids(
        self,
        subreddit: str,
        sort: str = 'hot',
        time_filter: str = 'all',
        limit: int = 1000
    ) -> List[str]:
        """
        Get thread IDs from a subreddit.

        Args:
            subreddit: Subreddit name
            sort: Sort type ('hot', 'top', 'new', 'rising')
            time_filter: Time filter for 'top' sort
            limit: Maximum number of thread IDs to fetch

        Returns:
            List of thread IDs
        """
        thread_ids = []
        after = None

        while len(thread_ids) < limit:
            params = {
                'limit': min(100, limit - len(thread_ids)),
                'after': after
            }

            if sort == 'top':
                params['t'] = time_filter

            url = f'https://oauth.reddit.com/r/{subreddit}/{sort}'

            data = await self._make_request('GET', url, params=params)

            if not data or 'data' not in data:
                break

            children = data['data'].get('children', [])
            if not children:
                break

            for post in children:
                if post.get('kind') == 't3':  # Post type
                    post_id = post['data'].get('id')
                    if post_id:
                        thread_ids.append(post_id)

            after = data['data'].get('after')
            if not after:
                break

            # Minimal delay between pagination (rate limiter handles pacing)
            await asyncio.sleep(0.2)

        logging.debug(f"Fetched {len(thread_ids)} thread IDs from r/{subreddit} ({sort})")
        return thread_ids

    def get_stats(self) -> Dict[str, Any]:
        """
        Get client statistics.

        Returns:
            Dictionary with statistics
        """
        return {
            'total_requests': self.total_requests,
            'failed_requests': self.failed_requests,
            'rate_limit_hits': self.rate_limit_hits,
            'diversity_requests': self.diversity_requests,
            'success_rate': (
                (self.total_requests - self.failed_requests) / self.total_requests
                if self.total_requests > 0 else 0
            )
        }

    async def close(self):
        """Close the HTTP client."""
        if self.client:
            await self.client.aclose()
            logging.debug("Reddit API client closed")
