# SubDir Archiver - Docker Test Plan

## Prerequisites ✅

All configuration is complete:
- ✅ Reddit credentials configured in `.env`
- ✅ User-Agent set to proper format
- ✅ SCANNER_MODE set to `threads`
- ✅ Scanner database mounted at `/app/data`
- ✅ Priority CSV mounted at `/app/priority_subreddits.csv`

---

## Test Sequence

### Step 1: Build Containers

```bash
cd /Users/river/code/justriverjames/subdir/archiver/docker

# Build scanner image
docker-compose build scanner

# Expected: Build completes successfully
```

### Step 2: Start PostgreSQL

```bash
# Start PostgreSQL in background
docker-compose up -d postgres

# Wait for health check
sleep 15

# Check status
docker-compose ps

# Expected: postgres shows "healthy" status
```

### Step 3: Verify Database Connection

```bash
# Connect to database
docker-compose exec postgres psql -U archiver -d reddit_archiver -c "SELECT version();"

# Expected: Shows PostgreSQL version
```

### Step 4: Run Database Migrations

```bash
# The migrations run automatically on first scanner start
# Just verify the migration file exists
ls -la /Users/river/code/justriverjames/subdir/archiver/migrations/

# Expected: 001_initial_schema.sql exists
```

### Step 5: Import Priority CSV (208 Subreddits)

```bash
# Import the 208 priority subreddits (155 SFW + 53 NSFW)
docker-compose run --rm scanner python main.py import-csv /app/priority_subreddits.csv

# Expected output:
# - "Added: 208 new subreddits"
# - No errors
```

### Step 6: Verify Import

```bash
# Check subreddits table
docker-compose exec postgres psql -U archiver -d reddit_archiver -c \
  "SELECT COUNT(*), posts_status, comments_status FROM subreddits GROUP BY posts_status, comments_status;"

# Expected:
# - 208 subreddits with posts_status='pending'
```

### Step 7: Test Threads Mode (5 Subreddits)

```bash
# Run scanner in threads mode for 5 subreddits
docker-compose run --rm scanner python main.py run --limit 5

# Expected:
# - Processes 5 subreddits
# - Fetches posts + media URLs
# - No 429 rate limit errors
# - Takes ~10-15 minutes
```

### Step 8: Verify Results

```bash
# Check completed subreddits
docker-compose exec postgres psql -U archiver -d reddit_archiver -c \
  "SELECT display_name, posts_status, comments_status, total_posts, total_media_urls
   FROM subreddits
   WHERE posts_status='completed'
   ORDER BY subscribers DESC;"

# Expected:
# - 5 rows with posts_status='completed'
# - comments_status='deferred'
# - Non-zero total_posts and total_media_urls
```

### Step 9: Check Posts Table

```bash
# Verify posts were saved
docker-compose exec postgres psql -U archiver -d reddit_archiver -c \
  "SELECT subreddit, COUNT(*) as post_count
   FROM posts
   GROUP BY subreddit
   ORDER BY post_count DESC;"

# Expected:
# - 5 subreddits with ~500-2000 posts each
```

### Step 10: Check Media URLs

```bash
# Verify media URLs were extracted
docker-compose exec postgres psql -U archiver -d reddit_archiver -c \
  "SELECT COUNT(*) as total_media_urls FROM media_urls;"

# Expected:
# - Several hundred to thousands of media URLs
```

### Step 11: Verify Comments NOT Fetched

```bash
# Verify comments table is empty (threads mode)
docker-compose exec postgres psql -U archiver -d reddit_archiver -c \
  "SELECT COUNT(*) FROM comments;"

# Expected:
# - count = 0 (comments deferred in threads mode)
```

---

## Optional: Test Scanner SQLite Sync

If you want to test syncing from the scanner database:

```bash
# Sync subreddits with 50k+ subscribers from scanner DB
docker-compose run --rm scanner python main.py sync \
  --scanner-db /app/data/subreddit_scanner.db \
  --min-subscribers 50000

# Expected:
# - Shows count of subreddits found
# - Reports added/updated counts
```

---

## Optional: Test Comments Mode

After completing threads mode test, test comments mode:

```bash
# 1. Edit .env and change SCANNER_MODE
nano /Users/river/code/justriverjames/subdir/archiver/docker/.env
# Change: SCANNER_MODE=comments

# 2. Run comments mode
docker-compose run --rm scanner python main.py run --limit 5

# Expected:
# - Processes comments for the 5 completed subreddits
# - Slower than threads mode
# - Populates comments table
```

---

## Monitoring Commands

### View Logs
```bash
# Follow scanner logs in real-time
docker-compose logs -f scanner

# View last 100 lines
docker-compose logs --tail=100 scanner
```

### Check Rate Limiting
```bash
# Look for rate limit info in logs
docker-compose logs scanner | grep -i "rate\|429\|403"

# Expected: No 429 errors, rate limit compliance messages
```

### Database Stats
```bash
# Overall stats
docker-compose exec postgres psql -U archiver -d reddit_archiver -c \
  "SELECT
    (SELECT COUNT(*) FROM subreddits) as total_subs,
    (SELECT COUNT(*) FROM subreddits WHERE posts_status='completed') as completed_subs,
    (SELECT COUNT(*) FROM posts) as total_posts,
    (SELECT COUNT(*) FROM comments) as total_comments,
    (SELECT COUNT(*) FROM media_urls) as total_media_urls;"
```

---

## Cleanup (if needed)

```bash
# Stop all containers
docker-compose down

# Remove volumes (WARNING: deletes all data)
docker-compose down -v

# Remove images
docker-compose down --rmi all
```

---

## Success Criteria

- ✅ PostgreSQL starts and stays healthy
- ✅ Database migrations run successfully
- ✅ Priority CSV imports all 208 subreddits
- ✅ Threads mode processes 5 subreddits without errors
- ✅ Posts and media URLs saved to database
- ✅ Comments table remains empty (deferred)
- ✅ No 429 rate limit errors
- ✅ Rate limiting stays under 75 QPM
- ✅ Anti-detection breaks triggered

---

## Troubleshooting

**Issue: Can't connect to database**
```bash
# Check if postgres is running
docker-compose ps postgres

# Check logs
docker-compose logs postgres

# Restart
docker-compose restart postgres
```

**Issue: Rate limit errors (429)**
```bash
# Increase delays in .env
REQUESTS_PER_MINUTE=50  # Lower from 60
SUBREDDIT_PAUSE_MIN=60  # Increase from 30
```

**Issue: Scanner crashes**
```bash
# Check logs
docker-compose logs scanner

# Run with debug logging
# Edit .env: LOG_LEVEL=DEBUG
```

---

All configuration is complete and ready to test!
