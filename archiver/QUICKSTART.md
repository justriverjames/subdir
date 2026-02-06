# SubDir Archiver - Quick Start Guide

## Setup Complete ✅

All configuration has been completed and the archiver is ready for testing!

### What's Been Configured:

1. **Toggle Mode Implemented** ✅
   - Threads mode: Fetch posts + media URLs only
   - Comments mode: Fetch comments for completed posts
   - No simultaneous processing (clean separation)

2. **Scanner Sync Command** ✅
   - Import subreddits from scanner SQLite database
   - Preserve processing state
   - Priority-based sorting

3. **Priority CSV Ready** ✅
   - 208 subreddits total (155 SFW + 53 NSFW)
   - Covers all knowledge preservation categories
   - Mounted in Docker container

4. **User-Agent Configured** ✅
   - Format: `linux:subdir-archiver:v1.0.0 (by /u/OutragedRaptor)`
   - Prevents rate limiting

5. **Docker Environment** ✅
   - PostgreSQL 16 database
   - Scanner container
   - Volumes and networks configured
   - Scanner database mounted

---

## Quick Test (Automated)

Run the automated test script:

```bash
cd /Users/river/code/justriverjames/subdir/archiver/docker
./quick-test.sh
```

This will:
1. Build the Docker image
2. Start PostgreSQL
3. Import 208 priority subreddits
4. Process 5 subreddits in threads mode
5. Show results

**Time:** ~15-20 minutes total

---

## Manual Test (Step by Step)

Follow the detailed test plan:

```bash
cd /Users/river/code/justriverjames/subdir/archiver/docker

# Read the test plan
cat TEST_PLAN.md

# Or open in editor
nano TEST_PLAN.md
```

---

## Key Commands

### Build & Start
```bash
docker-compose build scanner
docker-compose up -d postgres
```

### Import Priority Subreddits
```bash
docker-compose run --rm scanner python main.py import-csv /app/priority_subreddits.csv
```

### Run Threads Mode
```bash
# Process 5 subreddits (test)
docker-compose run --rm scanner python main.py run --limit 5

# Process 50 subreddits (production batch)
docker-compose run --rm scanner python main.py run --limit 50

# Process all pending subreddits
docker-compose up scanner
```

### Sync from Scanner Database
```bash
# Sync subreddits with 50k+ subscribers
docker-compose run --rm scanner python main.py sync \
  --scanner-db /app/data/subreddit_scanner.db \
  --min-subscribers 50000
```

### Switch to Comments Mode
```bash
# 1. Edit .env
nano docker/.env
# Change: SCANNER_MODE=comments

# 2. Run comments mode
docker-compose run --rm scanner python main.py run --limit 5
```

### Check Database
```bash
# Overall stats
docker-compose exec postgres psql -U archiver -d reddit_archiver -c \
  "SELECT
    (SELECT COUNT(*) FROM subreddits) as total_subs,
    (SELECT COUNT(*) FROM subreddits WHERE posts_status='completed') as completed_subs,
    (SELECT COUNT(*) FROM posts) as total_posts,
    (SELECT COUNT(*) FROM media_urls) as total_media_urls;"

# Completed subreddits
docker-compose exec postgres psql -U archiver -d reddit_archiver -c \
  "SELECT display_name, total_posts, total_media_urls
   FROM subreddits
   WHERE posts_status='completed'
   ORDER BY subscribers DESC;"
```

### View Logs
```bash
# Follow logs
docker-compose logs -f scanner

# Last 100 lines
docker-compose logs --tail=100 scanner

# Search for errors
docker-compose logs scanner | grep -i error
```

---

## Production Workflow

### Phase 1: Priority Subreddits (208)

```bash
# 1. Import priority CSV
docker-compose run --rm scanner python main.py import-csv /app/priority_subreddits.csv

# 2. Process all priority subreddits in threads mode
docker-compose up scanner

# Expected: ~10-15 hours for 208 subreddits
# Result: ~200k posts, ~750k media URLs
```

### Phase 2: Bulk Sync from Scanner (228k+ subreddits)

```bash
# 1. Sync all active subreddits with 100+ subscribers
docker-compose run --rm scanner python main.py sync \
  --scanner-db /app/data/subreddit_scanner.db \
  --min-subscribers 100

# 2. Process in chunks (auto-processes 50 at a time)
docker-compose up -d scanner

# Monitor progress
docker-compose logs -f scanner

# Expected: 150-200 hours for 228k subreddits @ 75 QPM
```

### Phase 3: Comments Mode (Optional)

```bash
# 1. Switch to comments mode
# Edit docker/.env: SCANNER_MODE=comments

# 2. Run comments fetching
docker-compose up -d scanner

# Expected: 5-10x longer than threads mode
```

---

## File Locations

- **Configuration:** `/Users/river/code/justriverjames/subdir/archiver/docker/.env`
- **Docker Compose:** `/Users/river/code/justriverjames/subdir/archiver/docker/docker-compose.yml`
- **Priority CSV:** `/Users/river/code/justriverjames/subdir/archiver/priority_subreddits.csv`
- **Scanner DB:** `/Users/river/code/justriverjames/subdir/data/subreddit_scanner.db`
- **Migrations:** `/Users/river/code/justriverjames/subdir/archiver/migrations/001_initial_schema.sql`

---

## Database Details

- **Host:** localhost
- **Port:** 5433 (to avoid conflict with other PostgreSQL instances)
- **Database:** reddit_archiver
- **User:** archiver
- **Password:** archiver_secure_pass_2024

**Connect directly:**
```bash
psql -h localhost -p 5433 -U archiver -d reddit_archiver
```

---

## Expected Performance

### Threads Mode (Posts + Media URLs)
- **Rate:** ~30-40 minutes per 1000 subreddits @ 75 QPM
- **API Calls:** ~20-30 per subreddit
- **Storage:** ~100-500 posts per subreddit, varies by size

### Comments Mode (Comments)
- **Rate:** ~2-5 hours per 1000 posts
- **API Calls:** ~1 per post
- **Storage:** ~50-500 comments per post, varies by discussion

### Anti-Detection Features (Automatic)
- Random breaks every 10-25 subreddits (1-5 minutes)
- 5% chance of long break (15-60 minutes)
- Random delays between subreddits (30-60 seconds)
- Chunked shuffling (processes in groups of 3000, shuffled)
- Gaussian jitter on timing

---

## Troubleshooting

**Port conflict (5433 already in use):**
```bash
# Edit docker/.env and change:
POSTGRES_PORT=5434  # or another free port
```

**Rate limit errors (429):**
```bash
# Edit docker/.env:
REQUESTS_PER_MINUTE=50  # Lower from 75
SUBREDDIT_PAUSE_MIN=60  # Increase from 30
```

**Database connection errors:**
```bash
# Restart PostgreSQL
docker-compose restart postgres

# Check status
docker-compose ps postgres
```

**Scanner crashes:**
```bash
# Check logs
docker-compose logs scanner

# Enable debug logging
# Edit docker/.env: LOG_LEVEL=DEBUG
```

---

## Ready to Test!

Run the automated test:
```bash
cd /Users/river/code/justriverjames/subdir/archiver/docker
./quick-test.sh
```

Or follow the manual test plan:
```bash
cat docker/TEST_PLAN.md
```

---

**Next:** After successful test, run production archival of 208 priority subreddits!
