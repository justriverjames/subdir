# Reddit Comprehensive Archiver

Complete archival system for subreddits with 5,000+ subscribers.

## What It Does

Automatically archives Reddit subreddits similar to redditarr, but designed for bulk archival:

✅ **Posts**: Top 1000 all-time + 1000 hot (merged & deduplicated)
✅ **Comments**: Full comment trees with materialized paths, bot filtering
✅ **Media URLs**: All image/video/gallery URLs extracted (NOT downloaded)
✅ **Conservative Rate Limiting**: 60 QPM to stay under Reddit's radar
✅ **PostgreSQL Storage**: Optimized for long-term archival
✅ **Docker Deployment**: Run on Unraid or Docker Desktop

## Quick Start (Docker)

1. **Copy environment file:**
   ```bash
   cp config/.env.example config/.env
   ```

2. **Edit `.env` with your Reddit credentials:**
   - Get credentials at https://www.reddit.com/prefs/apps
   - Create a "script" app
   - Fill in CLIENT_ID, CLIENT_SECRET, USERNAME, PASSWORD

3. **Start services:**
   ```bash
   cd docker
   docker-compose up -d
   ```

4. **Check logs:**
   ```bash
   docker logs -f subdir-archiver-scanner
   ```

## Configuration

See `config/.env.example` for all available options.

Key settings:
- `MIN_SUBSCRIBERS`: Only archive subs with this many subscribers (default: 5000)
- `BATCH_SIZE`: Number of subreddits to process per run (default: 10)
- `REQUESTS_PER_MINUTE`: Conservative rate limit (default: 60)

## Database

PostgreSQL schema at `migrations/001_initial_schema.sql`

Tables:
- `subreddits` - Metadata and processing state
- `posts` - Deduplicated posts (top 1000 + hot 1000)
- `processing_state` - Resume capability

## Import from Subdir

To import subreddits from existing subdir SQLite database:

```bash
# Set in .env:
SUBDIR_SQLITE_PATH=/path/to/subdir/data/subreddit_scanner.db
```

Scanner will automatically import subreddits with 5k+ subscribers on first run.

## Architecture

```
Scanner → Reddit API → PostgreSQL
  ├─ Metadata Processor (subreddit info)
  ├─ Posts Processor (top 1000 + hot 1000)
  └─ Rate Limiter (60 QPM, 3-window)
```

## Complete Implementation Status

✅ **COMPLETE - Ready to test!**

- ✅ PostgreSQL schema (subreddits, posts, comments, media_urls)
- ✅ Database connection pool with transactions
- ✅ Conservative rate limiter (60 QPM, 3-window)
- ✅ Reddit API client with OAuth
- ✅ Metadata processor
- ✅ Posts processor (top 1000 + hot 1000, merged & deduplicated)
- ✅ Comments processor (materialized paths, bot filtering, depth 5, max 500)
- ✅ Media URL extractor (all types: images, videos, galleries)
- ✅ Complete orchestration (metadata → posts → comments → media)
- ✅ Docker configuration for local testing
- ✅ Import from subdir SQLite database

## How It Works

**4-Phase Processing** (just like redditarr):
1. **Metadata**: Fetch subreddit info (subscribers, description, icons)
2. **Posts**: Fetch top 1000 all-time + hot 1000, merge and deduplicate
3. **Comments**: Fetch all comments with materialized paths (root.id1.id2.id3)
4. **Media URLs**: Extract all media URLs for future downloading

Each phase is tracked in the database for resume capability.

## Development

**Local setup without Docker:**

```bash
cd scanner
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows
pip install -r requirements.txt

# Set environment variables
export REDDIT_CLIENT_ID=...
export REDDIT_CLIENT_SECRET=...
export REDDIT_USERNAME=...
export REDDIT_PASSWORD=...
export POSTGRES_HOST=localhost
export POSTGRES_PASSWORD=...

# Run
python main.py
```

## Deployment (Unraid)

1. Create share: `/mnt/user/appdata/subdir-archiver/`
2. Copy project files
3. Edit `config/.env` with credentials
4. Run: `docker-compose -f docker/docker-compose.yml up -d`

Access database on port 5433 (to avoid conflict with redditarr).
