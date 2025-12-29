import asyncio
from config import Config
from reddit_client import RedditAPIClient
from rate_limiter import SlidingWindowRateLimiter

async def test():
    config = Config.from_env()
    limiter = SlidingWindowRateLimiter(85, 14, 2)
    client = RedditAPIClient(config, limiter)
    await client.initialize()

    # Test with known-active subreddit
    metadata, status = await client.get_subreddit_info('python')
    print(f'Status: {status}')
    if metadata:
        print(f'Title: {metadata.get("title")}')
        print(f'Subscribers: {metadata.get("subscribers")}')
    else:
        print('No metadata returned - likely auth issue or 403')

    await client.close()

asyncio.run(test())
