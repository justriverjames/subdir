# Testing Instructions for Docker Desktop

## Prerequisites

1. **Docker Desktop** installed and running on your Mac
2. **Reddit API credentials** from https://www.reddit.com/prefs/apps (create a "script" app)

## Setup Steps

### 1. Configure Environment

```bash
cd /Users/river/code/justriverjames/subdir/archiver

# Copy example config
cp config/.env.example config/.env

# Edit config/.env with your Reddit credentials
nano config/.env  # or use any text editor
```

**Required changes in .env:**
- `REDDIT_CLIENT_ID` - from your Reddit app
- `REDDIT_CLIENT_SECRET` - from your Reddit app
- `REDDIT_USERNAME` - your Reddit username
- `REDDIT_PASSWORD` - your Reddit password
- `POSTGRES_PASSWORD` - set any password (e.g., `test123`)

**Recommended for testing:**
- `BATCH_SIZE=3` - start small (3 subreddits)
- `MIN_SUBSCRIBERS=50000` - test with larger subs first

### 2. Build and Start

```bash
cd docker

# Build containers
docker-compose build

# Start PostgreSQL
docker-compose up -d postgres

# Wait for PostgreSQL to be ready (about 10 seconds)
sleep 10

# Check PostgreSQL is healthy
docker-compose ps
```

### 3. Add Test Subreddits Manually

Since you don't have subreddits imported yet, let's add some manually:

```bash
# Connect to PostgreSQL
docker exec -it subdir-archiver-db psql -U archiver -d reddit_archiver

# Add test subreddits (paste these SQL commands):
INSERT INTO subreddits (name, priority, status, first_seen_at) VALUES
  ('python', 1, 'pending', extract(epoch from now())::bigint),
  ('linux', 1, 'pending', extract(epoch from now())::bigint),
  ('datahoarder', 1, 'pending', extract(epoch from now())::bigint);

# Verify
SELECT name, status, priority FROM subreddits;

# Exit
\q
```

### 4. Run Scanner

```bash
# Run scanner (will process BATCH_SIZE subreddits then stop)
docker-compose up scanner

# Watch logs in real-time
docker logs -f subdir-archiver-scanner
```

### 5. Verify Results

While scanner is running, open a new terminal:

```bash
# Check database stats
docker exec -it subdir-archiver-db psql -U archiver -d reddit_archiver -c "
  SELECT
    (SELECT COUNT(*) FROM subreddits WHERE status='active') as active_subs,
    (SELECT COUNT(*) FROM posts) as total_posts,
    (SELECT COUNT(*) FROM comments) as total_comments,
    (SELECT COUNT(*) FROM media_urls) as total_media_urls;
"

# Check what was archived
docker exec -it subdir-archiver-db psql -U archiver -d reddit_archiver -c "
  SELECT name, total_posts, total_comments, total_media_urls
  FROM subreddits
  WHERE status='active'
  ORDER BY total_posts DESC;
"

# Check processing details
docker exec -it subdir-archiver-db psql -U archiver -d reddit_archiver -c "
  SELECT subreddit, current_phase, phase_progress
  FROM processing_state;
"
```

## What to Expect

For each subreddit (e.g., r/python):

1. **Metadata** - ~2 seconds
   - Fetches subreddit info

2. **Posts** - ~2-3 minutes
   - Fetches top 1000 all-time (10 API calls, ~100 posts each)
   - Fetches hot 1000 (10 API calls, ~100 posts each)
   - Merges and deduplicates
   - Should get ~1500-1900 unique posts

3. **Comments** - ~30-45 minutes
   - Fetches comments for each post (1 API call per post)
   - Builds comment trees with materialized paths
   - Filters out bots
   - For 1500 posts × ~200 comments = ~300k comments

4. **Media URLs** - ~5 seconds
   - Extracts URLs from post metadata (no API calls)

**Total per subreddit: ~35-50 minutes**

## Expected Output

```
============================================================
Initializing Reddit Archiver Scanner
============================================================
Comprehensive archiver - posts, comments, media URLs
============================================================
✓ Database connection established
✓ Reddit API authenticated
✓ All processors initialized

Running database migrations
✓ Migrations complete

Initial Database Stats:
  total_subreddits: 3
  active_subreddits: 0
  pending_subreddits: 3
  total_posts: 0
  total_comments: 0
  total_media_urls: 0

============================================================
Starting batch processing (limit: 3)
============================================================
Found 3 subreddits to process

[1/3] Processing r/python
============================================================
Processing r/python
============================================================
[1/4] Fetching metadata for r/python
✓ r/python - 1,234,567 subscribers
[2/4] Fetching posts for r/python
✓ r/python - 1,834 unique posts (top: 1000, hot: 982)
[3/4] Fetching comments for r/python
✓ r/python - 234,567 comments from 1834 posts
[4/4] Extracting media URLs for r/python
✓ r/python - 456 media URLs from 1834 posts

✓ r/python COMPLETE:
  - 1,834 posts
  - 234,567 comments
  - 456 media URLs

[continues for other subreddits...]
```

## Troubleshooting

### Container won't start
```bash
# Check logs
docker-compose logs postgres
docker-compose logs scanner

# Restart
docker-compose down
docker-compose up
```

### Rate limit errors (429)
- Scanner will auto-stop after 2 rate limit hits
- Wait 1 hour, then restart
- Consider lowering `BATCH_SIZE` or `REQUESTS_PER_MINUTE`

### Authentication errors
- Verify Reddit credentials in `.env`
- Ensure app type is "script" not "web app"
- Check username/password are correct

### Database connection errors
- Ensure PostgreSQL is healthy: `docker-compose ps`
- Check PostgreSQL logs: `docker logs subdir-archiver-db`
- Verify password in `.env` matches

## Cleanup

```bash
# Stop containers
docker-compose down

# Remove data (start fresh)
docker-compose down -v

# Remove images
docker-compose down --rmi all -v
```

## Next Steps After Testing

1. **Import from subdir SQLite** (optional):
   - Uncomment volume mount in docker-compose.yml
   - Set `SUBDIR_SQLITE_PATH=/app/data/subreddit_scanner.db`
   - This will import all 5k+ subscriber subreddits automatically

2. **Increase batch size**: Set `BATCH_SIZE=10` or higher

3. **Run continuously**: Remove `docker-compose up scanner` and use `docker-compose up -d` to run in background

4. **Deploy to Unraid**: Use the production docker-compose.yml with Unraid paths
