# SubDir: Metadata Service for Redditarr

**Status:** Planned for v1.1
**Priority:** HIGH - Next major feature after v1.0
**Estimated Effort:** 1 week development

---

## Executive Summary

SubDir is a standalone metadata service for Reddit communities, modeled after TheTVDB/TMDB for Sonarr/Radarr. It provides:

- **29,404 subreddits** with metadata (subscribers, NSFW flags, descriptions)
- **782,533 thread IDs** pre-collected from Hot/Top feeds
- **AI-categorized** taxonomy (Technology, Science, Entertainment, etc.)
- **Free public API** for Redditarr and other tools

**Key Benefit:** Instant subreddit discovery and thread ID pre-population, eliminating slow Reddit API pagination.

---

## The Problem SubDir Solves

### Current Redditarr Flow (Slow)
```
User adds "python"
    ↓
Query Reddit API /r/python/about (slow, rate-limited)
    ↓
Paginate through /hot, /top/all, /top/year (very slow, 100 posts at a time)
    ↓
Collect ~1,500 thread IDs (takes 2-3 minutes)
    ↓
Metadata worker fetches post details (another 5-10 minutes)
```

### With SubDir (Fast)
```
User searches "python"
    ↓
Query SubDir local cache (instant, 29k subs indexed)
    ↓
Show rich results:
  r/python - 1.2M subs - "News about Python programming"
  r/learnpython - 890K subs - "Subreddit for learning Python"
    ↓
User selects r/python
    ↓
SubDir provides 1,523 thread IDs instantly (no pagination!)
    ↓
Metadata worker fills in details (5-10 minutes, same as before)
```

**Time Saved:** 2-3 minutes per subreddit on initial discovery + instant search

---

## Architecture: The Sonarr/Radarr Model

### Comparison

| Media Apps | Metadata Service | Content Archive |
|------------|------------------|-----------------|
| Sonarr | TheTVDB | Your NAS/Plex |
| Radarr | TMDB | Your NAS/Plex |
| Lidarr | MusicBrainz | Your NAS/Plex |
| **Redditarr** | **SubDir** | **Your LAN Archive** |

### Key Principles

1. **Separation of Concerns**
   - SubDir = Metadata catalog (public, safe, legal)
   - Redditarr = Personal archiving tool (private, LAN-only)

2. **Metadata vs Content**
   - SubDir: Subreddit names, descriptions, thread IDs (all public data)
   - Redditarr: Actual posts, comments, media (user archives locally)

3. **Legal Safety**
   - SubDir hosts NO Reddit content, only metadata
   - Like a phone book or search engine index
   - Existing precedents: subredditstats.com, pushshift metadata

4. **Optional Integration**
   - Redditarr works standalone (Reddit API only)
   - SubDir is enhancement, not requirement
   - Users choose: use SubDir or pure Reddit API

---

## Current SubDir Data

### Scanner Database (106 MB SQLite)

**Subreddits Table:**
```sql
29,404 subreddits with:
- name (e.g., "python")
- title
- description
- subscribers
- nsfw flag (over_18)
- status (active/banned/private/quarantined)
- created_utc
- last_updated
```

**Thread IDs Table:**
```sql
782,533 thread IDs across all subreddits
- thread_id (e.g., "abc123")
- subreddit (foreign key)
```

**Collection Method:**
- Fetched via Reddit API (rate-limit compliant)
- Hot posts (current trending)
- Top all-time (historical best)
- Top year (recent popular)
- Average: ~26 thread IDs per subreddit

---

## SubDir Service Architecture

### Deployment Stack

```
User/Redditarr
    ↓
subdir.hammond.im (Cloudflare CDN)
    ↓ (99% cached at edge)
Hetzner VPS Finland (€4.51/month)
    ↓
Node.js Express Backend (port 3000)
FastAPI Python API (port 8000)
SQLite Database (106 MB)
Static Web UI
```

### Temporary Domain Setup

**Development/Testing:**
- Web UI: `https://subdir.hammond.im`
- API: `https://subdir.hammond.im/api/*`
- Node.js handles both web UI and proxies API requests

**Future Production:**
- Buy domain: `subdir.io` or `subdir.dev` or similar
- Keep same architecture
- DNS update only

### Technology Choices

**Backend:**
- **Node.js Express** (port 3000): Web UI + API proxy
- **Python FastAPI** (port 8000): Data processing + exports
- **SQLite** (106 MB): Perfect for this scale, read-only
- **Later:** Migrate to PostgreSQL on VPS for better concurrency

**Frontend:**
- **Vue.js or vanilla JS**: Simple, fast, no build complexity
- **Tailwind CSS**: Easy styling
- **Heroicons**: Clean iconography

**Infrastructure:**
- **Cloudflare Free Tier**: CDN, SSL, DDoS protection, caching
- **Hetzner VPS** (CPX11): €4.51/month, plenty for this
- **Docker Compose**: Easy deployment

---

## API Design

### REST Endpoints (FastAPI on port 8000)

```python
# Search
GET /api/search?q=python&limit=50
    → [{name, subscribers, nsfw, description, category}]

# Subreddit metadata
GET /api/subreddit/{name}
    → {name, subscribers, nsfw, description, threads_count, category}

# Thread IDs
GET /api/subreddit/{name}/threads
    → [{thread_id}] (just IDs, no content)

# Categories
GET /api/categories
    → Tree structure of categories

GET /api/category/{name}/subreddits?limit=100
    → Subreddits in category

# Stats
GET /api/stats
    → {total_subs, total_threads, last_updated}
```

### Bulk Export (Recommended for Redditarr)

```python
# Download once, cache locally, search offline

GET /api/export/metadata.json.gz
# All 29k subreddits, ~5 MB gzipped
{
  "version": "2025-10-14",
  "subreddits": [
    {
      "name": "python",
      "subscribers": 1200000,
      "nsfw": false,
      "description": "...",
      "category": "Technology",
      "subcategory": "Programming",
      "threads_count": 1523
    },
    // ... 29,403 more
  ]
}

GET /api/export/threads/{subreddit}.json.gz
# Thread IDs for specific subreddit, ~15 KB
{
  "subreddit": "python",
  "threads": ["abc123", "def456", ...],
  "count": 1523,
  "updated": "2025-10-14"
}
```

### Rate Limiting

```python
# Cloudflare handles DDoS
# Application rate limits:
- Free tier: 100 requests/minute per IP
- Bulk exports: No limit (cached by Cloudflare)
```

---

## AI Categorization Plan

### Using Claude API (Sonnet 4.5)

**Process:**
```python
# Batch categorization
for batch in chunks(subreddits, 100):
    prompt = f"""
    Categorize these 100 subreddits hierarchically.

    Format: Category > Subcategory

    Examples:
    - Technology > Programming > Python
    - Entertainment > Gaming > RPG
    - Science > Physics > Astronomy
    - NSFW > Adult Content > Amateur

    Return JSON array of:
    [{{"subreddit": "name", "category": "...", "subcategory": "..."}}]

    Subreddits:
    {batch_metadata}
    """

    categories = await claude_api.complete(prompt)
    save_to_db(categories)
```

**Cost Estimate:**
- 29,404 subreddits ÷ 100 per batch = ~294 API calls
- ~1,000 tokens input + ~500 tokens output per call
- Total: ~441k tokens
- **Cost: ~$8 one-time**

**Result:**
```
Technology/
├── Programming/
│   ├── Python (r/python, r/learnpython, r/pythontips)
│   ├── JavaScript (r/javascript, r/node, r/react)
│   ├── Rust (r/rust)
│   └── General (r/programming, r/coding, r/learnprogramming)
├── Hardware/
│   ├── PC Building (r/buildapc, r/pcmasterrace)
│   └── Networking (r/homelab, r/networking)
└── Software/
    ├── Linux (r/linux, r/archlinux, r/ubuntu)
    └── Self-Hosted (r/selfhosted, r/homeserver)

Science/
├── Space (r/space, r/astronomy, r/spacex)
├── Physics (r/physics, r/askscience)
└── Biology (r/biology, r/microbiology)

Entertainment/
├── Gaming (r/gaming, r/games, r/truegaming)
├── Movies (r/movies, r/criterion, r/moviesuggestions)
└── Music (r/music, r/listentothis, r/indie)

NSFW/ (34 categories, collapsed by default in UI)
```

---

## Redditarr Integration

### Phase 1: Enhanced Search (v1.1)

```python
# app/subdir_client.py (new file)

import gzip
import json
import aiohttp
from pathlib import Path
from datetime import datetime, timedelta

class SubDirClient:
    """Client for SubDir metadata service"""

    BASE_URL = "https://subdir.hammond.im"
    CACHE_DIR = Path("data/subdir_cache")
    CACHE_DAYS = 7

    def __init__(self):
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.metadata = None

    async def refresh_metadata(self):
        """Download bulk metadata (5 MB, once per week)"""
        url = f"{self.BASE_URL}/api/export/metadata.json.gz"

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                compressed = await resp.read()

        data = json.loads(gzip.decompress(compressed))

        # Save to cache
        cache_file = self.CACHE_DIR / "metadata.json"
        cache_file.write_text(json.dumps(data))

        self.metadata = data
        return data

    def load_cache(self):
        """Load cached metadata"""
        cache_file = self.CACHE_DIR / "metadata.json"

        if not cache_file.exists():
            return None

        # Check age
        age = datetime.now() - datetime.fromtimestamp(cache_file.stat().st_mtime)
        if age.days > self.CACHE_DAYS:
            return None  # Stale

        self.metadata = json.loads(cache_file.read_text())
        return self.metadata

    def search_local(self, query, limit=50):
        """Search locally cached metadata - instant, no API calls"""
        if not self.metadata:
            self.metadata = self.load_cache()

        if not self.metadata:
            return []  # No cache, fallback to Reddit API

        results = []
        query_lower = query.lower()

        for sub in self.metadata['subreddits']:
            if query_lower in sub['name'].lower() or \
               query_lower in sub.get('description', '').lower():
                results.append(sub)
                if len(results) >= limit:
                    break

        return results

    async def get_thread_ids(self, subreddit):
        """Get thread IDs for subreddit from SubDir"""
        url = f"{self.BASE_URL}/api/subreddit/{subreddit}/threads"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get('threads', [])
        except Exception as e:
            logging.warning(f"SubDir fetch failed for {subreddit}: {e}")

        return []  # Not found, fallback to Reddit API
```

### Phase 2: Enhanced Subreddit Suggest Endpoint

```python
# app/routes/subreddits.py

@router.get("/suggest")
async def suggest_subreddits(query: str):
    """
    Enhanced subreddit suggestions using SubDir
    """
    suggestions = []
    sources = {'subdir': 0, 'reddit': 0}

    # Try SubDir first (instant, local cache)
    try:
        subdir_results = app_state.subdir.search_local(query, limit=10)
        suggestions.extend(subdir_results)
        sources['subdir'] = len(subdir_results)
    except Exception as e:
        logging.warning(f"SubDir search failed: {e}")

    # Also query Reddit API for fresh/new subs
    try:
        reddit_results = await app_state.reddit_api.search_subreddits(query, limit=5)

        # Merge and dedupe by name
        existing_names = {s['name'] for s in suggestions}
        for result in reddit_results:
            if result['name'] not in existing_names:
                suggestions.append(result)
                sources['reddit'] += 1
    except Exception as e:
        logging.warning(f"Reddit search failed: {e}")

    return {
        'suggestions': suggestions[:15],  # Cap at 15 total
        'sources': sources
    }
```

### Phase 3: Thread ID Pre-Population

```python
# app/routes/subreddits.py

@router.post("/add")
async def add_subreddit(data: SubredditAdd):
    """
    Enhanced: Pre-populate thread IDs from SubDir
    """
    name = data.name.lower()

    # Add to database
    async with app_state.db_pool.connection() as db:
        await app_state.db_pool.add_subreddit(db, name, data.dict())

    # Try to get thread IDs from SubDir
    thread_ids = await app_state.subdir.get_thread_ids(name)

    if thread_ids:
        # Pre-populate thread IDs in database
        async with app_state.db_pool.connection() as db:
            # Add minimal post records with just thread IDs
            for thread_id in thread_ids:
                await db.execute("""
                    INSERT INTO posts (id, subreddit, downloaded, media_status)
                    VALUES ($1, $2, false, 'pending')
                    ON CONFLICT (id) DO NOTHING
                """, thread_id, name)

        logging.info(f"Pre-populated {len(thread_ids)} thread IDs from SubDir for r/{name}")

        # Metadata worker will fill in details later
        return {
            "status": "added",
            "threads_preloaded": len(thread_ids),
            "source": "subdir"
        }
    else:
        # No SubDir data, will use Reddit API pagination
        return {
            "status": "added",
            "threads_preloaded": 0,
            "source": "reddit_api"
        }
```

### Phase 4: Settings UI

```javascript
// Settings > Metadata Sources

┌─────────────────────────────────────────────────────┐
│ SubDir Integration                                   │
├─────────────────────────────────────────────────────┤
│                                                      │
│ [✓] Use SubDir for subreddit discovery              │
│ [✓] Pre-load thread IDs from SubDir                 │
│                                                      │
│ Cache Status:                                        │
│ Last updated: 2025-10-14 (7 days ago)               │
│ Next auto-update: 2025-10-21                        │
│                                                      │
│ [Refresh SubDir Cache Now]                          │
│                                                      │
│ Stats:                                               │
│ - 29,404 subreddits available                       │
│ - 782,533 thread IDs cached                         │
│ - Cache size: 5.2 MB                                │
│                                                      │
│ Browse Categories:                                   │
│ [Open SubDir Web UI ↗]                              │
│                                                      │
└─────────────────────────────────────────────────────┘
```

---

## Development Roadmap

### Week 1: SubDir Service (Next Session)

**Day 1-2: Backend Development**
- [ ] Setup project structure: `subdir_service/`
- [ ] Node.js Express server (port 3000)
  - Static file serving (web UI)
  - API proxy to Python backend
- [ ] Python FastAPI (port 8000)
  - Copy scanner SQLite DB
  - REST API endpoints
  - Bulk export endpoints
- [ ] Docker Compose configuration
- [ ] Deploy to hammond.im VPS

**Day 3: AI Categorization**
- [ ] Write categorization script
- [ ] Run Claude API on 29k subreddits (~$8)
- [ ] Update SQLite with categories
- [ ] Verify category tree

**Day 4-5: Web UI**
- [ ] Simple search interface
- [ ] Category browser (collapsible tree)
- [ ] Subreddit detail view
- [ ] API documentation page
- [ ] Mobile responsive

**Day 6: Cloudflare + Domain**
- [ ] Configure Cloudflare caching
- [ ] Setup rate limiting
- [ ] Test cache hit rates
- [ ] (Optional) Buy production domain

**Day 7: Testing**
- [ ] Load testing (simulate 1000 req/min)
- [ ] Verify Cloudflare caching working
- [ ] Test all API endpoints
- [ ] Cross-browser testing

### Week 2: Redditarr Integration (v1.1)

**Day 8-9: SubDir Client**
- [ ] Create `app/subdir_client.py`
- [ ] Implement bulk metadata download
- [ ] Local cache management
- [ ] Thread ID fetching

**Day 10: Enhanced Search**
- [ ] Update `/api/subreddits/suggest`
- [ ] Merge SubDir + Reddit results
- [ ] Test search performance

**Day 11: Thread Pre-Population**
- [ ] Update `/api/subreddits` POST endpoint
- [ ] Pre-populate thread IDs on add
- [ ] Test with/without SubDir data

**Day 12: Settings UI**
- [ ] Add SubDir settings page
- [ ] Cache refresh button
- [ ] Status display
- [ ] Link to SubDir web UI

**Day 13-14: Testing + Documentation**
- [ ] Integration testing
- [ ] Update user docs
- [ ] Update HANDOVER.md
- [ ] Prepare v1.1 release

---

## Cost Analysis

### Development Costs
- AI Categorization: **$8 one-time**

### Monthly Operational Costs
- Hetzner VPS (CPX11): **€4.51/month** (~$5)
- Domain (optional): **~$1/month** (if bought)
- Cloudflare: **Free tier** (more than sufficient)
- **Total: ~$5-6/month**

### Scaling Costs (if popular)
- Cloudflare handles 99% of traffic (free, unlimited)
- VPS upgrade only if >10k requests/day bypass cache
- CPX21 (€8.21/month) handles 100k+ req/day easily

---

## Legal & Ethical Considerations

### ✅ Completely Legal

**Why:**
1. **Public metadata only**: Subreddit names, descriptions, subscriber counts
2. **No content hosting**: No posts, comments, images, or videos
3. **Precedents exist**: subredditstats.com, pushshift metadata, reveddit
4. **Fair use**: Public directory service, like a phone book
5. **Rate limit compliant**: Data collected respecting Reddit's API limits

**Reddit ToS:**
- ToS restricts automated Reddit actions (we respect limits ✓)
- Hosting collected metadata separately = not a ToS violation
- We're not redistributing Reddit's API data, we collected it ourselves

**GDPR Compliant:**
- No personal data collected (all public subreddit metadata)
- EU hosting (Finland) = good standing

### Separation Strategy

**SubDir:**
- Public metadata catalog
- Educational/research tool
- No affiliation with content archiving
- Like a search engine for Reddit communities

**Redditarr:**
- Personal archiving tool (private, LAN-only)
- Optionally uses SubDir for discovery
- Users responsible for own archiving compliance
- Clear separation in branding/docs

---

## Next Steps

1. **Current Session:** Finish v1.0 cleanup and testing
2. **Next Session:** Build SubDir backend + web UI
3. **Week After:** Integrate SubDir with Redditarr v1.1
4. **Launch:** Announce to r/selfhosted, r/datahoarder

---

## Files Created This Session

- `SUBDIR_INTEGRATION.md` (this file)
- `subreddit_scanner/` (existing, 29k subs + 782k threads)

## Files to Create Next Session

```
subdir_service/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── main.py (FastAPI)
│   ├── api/
│   │   ├── search.py
│   │   ├── export.py
│   │   └── stats.py
│   └── data/
│       └── subdir.db (copy from scanner)
├── frontend/
│   ├── Dockerfile
│   ├── server.js (Express)
│   ├── public/
│   │   ├── index.html
│   │   ├── search.js
│   │   └── categories.js
│   └── package.json
└── scripts/
    └── categorize.py (Claude API)
```

---

## Questions for Next Session

1. Buy domain now or keep hammond.im?
2. PostgreSQL migration priority or keep SQLite?
3. Authentication needed or fully public API?
4. Analytics/tracking or stay privacy-focused?

**Recommendation:** Start with SQLite + hammond.im, migrate later if needed. Keep it simple.
