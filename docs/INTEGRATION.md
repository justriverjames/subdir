# SubDir Integration Guide

How to integrate SubDir with other applications (primarily Redditarr).

---

## For Redditarr Users

SubDir provides instant subreddit discovery and pre-populated thread IDs for faster archiving.

### Benefits

**Without SubDir:**
- Search "python" → Query Reddit API (rate-limited, slow)
- Paginate through 1500+ posts (2-3 minutes)
- Manual subreddit discovery

**With SubDir:**
- Search "python" → Instant results from local cache
- Get 1523 thread IDs instantly → Skip pagination entirely
- Browse 29k+ subreddits offline

### Integration Options

#### Option 1: Manual Usage (Current)

1. **Browse SubDir Web UI:**
   - Visit https://subdir.hammond.im
   - Search for subreddits
   - Copy subreddit names to Redditarr

2. **Use API for Thread IDs (Advanced):**
   ```bash
   # Get thread IDs for a subreddit
   curl https://subdir.hammond.im/api/subreddits/python/threads
   ```

#### Option 2: Built-in Integration (Redditarr v1.1+)

Coming in Redditarr v1.1:

1. **Enhanced Subreddit Search:**
   - Redditarr downloads SubDir metadata (~5MB, weekly refresh)
   - Search instantly across 29k+ subreddits
   - No Reddit API calls needed

2. **Thread ID Pre-population:**
   - When adding subreddit, fetch thread IDs from SubDir
   - Pre-populate database with thread IDs
   - Skip slow Reddit pagination (saves 2-3 minutes per subreddit)

3. **Settings UI:**
   - Enable/disable SubDir integration
   - Manual cache refresh
   - Link to SubDir web UI

---

## API Endpoints

### Search Subreddits

```http
GET https://subdir.hammond.im/api/search?q=python&limit=50
```

**Response:**
```json
{
  "subreddits": [
    {
      "name": "python",
      "title": "Python",
      "description": "News about the dynamic programming language...",
      "subscribers": 1234567,
      "over_18": false,
      "status": "active",
      "thread_count": 1523
    }
  ],
  "total": 1,
  "limit": 50
}
```

### Get Subreddit Metadata

```http
GET https://subdir.hammond.im/api/subreddits/python
```

**Response:**
```json
{
  "name": "python",
  "title": "Python",
  "description": "News about the dynamic programming language Python",
  "subscribers": 1234567,
  "active_users": 5432,
  "over_18": false,
  "subreddit_type": "public",
  "created_utc": 1201233135,
  "status": "active",
  "thread_count": 1523
}
```

### Get Thread IDs

```http
GET https://subdir.hammond.im/api/subreddits/python/threads
```

**Response:**
```json
{
  "subreddit": "python",
  "threads": ["abc123", "def456", "ghi789", ...],
  "count": 1523
}
```

### Bulk Export (Recommended for Integration)

```http
GET https://subdir.hammond.im/api/export/metadata.json.gz
```

**Response:** Gzipped JSON (~5MB) with all 29k+ subreddits.

**Structure:**
```json
{
  "version": "1.0.0",
  "total_subreddits": 29404,
  "subreddits": [
    {
      "name": "python",
      "title": "Python",
      "description": "...",
      "subscribers": 1234567,
      "over_18": false,
      "thread_count": 1523
    },
    ...
  ]
}
```

---

## Integration Example (Python)

### Basic Search

```python
import httpx

async def search_subreddits(query: str, limit: int = 50):
    """Search SubDir for subreddits"""
    url = f"https://subdir.hammond.im/api/search?q={query}&limit={limit}"
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

# Usage
results = await search_subreddits("python")
for sub in results['subreddits']:
    print(f"r/{sub['name']} - {sub['subscribers']:,} subscribers")
```

### Bulk Export with Local Caching

```python
import httpx
import gzip
import json
from pathlib import Path
from datetime import datetime, timedelta

class SubDirClient:
    """SubDir client with local caching"""

    BASE_URL = "https://subdir.hammond.im"
    CACHE_FILE = Path("data/subdir_cache.json")
    CACHE_DAYS = 7

    async def refresh_cache(self):
        """Download and cache metadata"""
        url = f"{self.BASE_URL}/api/export/metadata.json.gz"

        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            response.raise_for_status()
            compressed = response.content

        # Decompress
        data = json.loads(gzip.decompress(compressed))

        # Save to cache
        self.CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.CACHE_FILE.write_text(json.dumps(data))

        return data

    def load_cache(self):
        """Load cached metadata"""
        if not self.CACHE_FILE.exists():
            return None

        # Check age
        age = datetime.now() - datetime.fromtimestamp(
            self.CACHE_FILE.stat().st_mtime
        )

        if age.days > self.CACHE_DAYS:
            return None  # Stale

        return json.loads(self.CACHE_FILE.read_text())

    def search_local(self, query: str, limit: int = 50):
        """Search cached metadata (instant, no API calls)"""
        data = self.load_cache()
        if not data:
            return []

        results = []
        query_lower = query.lower()

        for sub in data['subreddits']:
            if query_lower in sub['name'].lower() or \
               query_lower in (sub.get('description') or '').lower():
                results.append(sub)
                if len(results) >= limit:
                    break

        return results

    async def get_thread_ids(self, subreddit: str):
        """Get thread IDs from SubDir"""
        url = f"{self.BASE_URL}/api/subreddits/{subreddit}/threads"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()
                return data['threads']
        except Exception:
            return []  # Fallback to Reddit API

# Usage
client = SubDirClient()

# Refresh cache (weekly)
await client.refresh_cache()

# Search instantly
results = client.search_local("python")

# Get thread IDs
threads = await client.get_thread_ids("python")
print(f"Found {len(threads)} threads for r/python")
```

---

## Integration Flow (Redditarr v1.1)

### 1. Initial Setup

```python
# On first run or settings change
await subdir_client.refresh_cache()
# Downloads ~5MB, saves to local cache
```

### 2. Enhanced Subreddit Search

```python
# User searches "python"
suggestions = subdir_client.search_local("python", limit=10)

# Also query Reddit API for fresh results
reddit_results = await reddit_api.search_subreddits("python", limit=5)

# Merge and deduplicate
all_results = merge_results(suggestions, reddit_results)

# Return to user instantly
return all_results
```

### 3. Thread ID Pre-Population

```python
# User adds r/python
subreddit_name = "python"

# Try SubDir first
thread_ids = await subdir_client.get_thread_ids(subreddit_name)

if thread_ids:
    # Pre-populate database
    for thread_id in thread_ids:
        await db.execute("""
            INSERT INTO posts (id, subreddit, media_status)
            VALUES ($1, $2, 'pending')
            ON CONFLICT (id) DO NOTHING
        """, thread_id, subreddit_name)

    # Metadata worker will fill in details later
    # Saves 2-3 minutes of Reddit API pagination!
else:
    # Fallback to Reddit API pagination (current method)
    await reddit_api.fetch_subreddit_posts(subreddit_name)
```

---

## Rate Limiting

SubDir API is public and free:

- **Rate Limit:** 100 requests/minute per IP
- **Bulk Export:** No rate limit (cached by Cloudflare)
- **Recommended:** Use bulk export + local caching for production

---

## Local Hosting

You can also host SubDir yourself:

```bash
# Clone and run
git clone https://github.com/martiantux/subdir.git
cd subdir
docker-compose up

# Access
# Web UI: http://localhost:7734
# API: http://localhost:7733
```

Then configure Redditarr to use your local instance:

```python
# In Redditarr settings
SUBDIR_URL = "http://localhost:7733"
```

---

## Future Enhancements

### v1.1: AI Categorization
```json
{
  "name": "python",
  "category": "Technology",
  "subcategory": "Programming",
  "related": ["learnpython", "pythontips", "programming"]
}
```

### v1.2: Advanced Filtering
```http
GET /api/search?q=python&category=Technology&nsfw=false&min_subscribers=100000
```

### v1.3: Real-time Updates
```javascript
// WebSocket subscription for new subreddits
ws = new WebSocket("wss://subdir.hammond.im/ws");
ws.on('new_subreddit', (data) => {
    console.log("New subreddit discovered:", data.name);
});
```

---

## Support

- **Documentation:** https://github.com/martiantux/subdir/tree/main/docs
- **Issues:** https://github.com/martiantux/subdir/issues
- **API Docs:** https://subdir.hammond.im/api/docs

---

## License

SubDir is open source (MIT License). Use freely in your projects!
