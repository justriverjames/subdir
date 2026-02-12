# SubDir Scanner

Python CLI tool for collecting Reddit subreddit metadata at scale.

---

## Overview

The Scanner is a production-ready tool for gathering comprehensive metadata from 140,000+ active subreddits. It provides the data foundation for the SubDir web application.

**Purpose:** Collect and maintain fresh subreddit metadata  
**Database:** SQLite with WAL mode  
**Rate Limiting:** 60 requests/minute (respects Reddit API limits)

---

## Features

- **Metadata Collection:** Subscribers, descriptions, icons, colors, categories
- **Smart Filtering:** Only active subs with 100+ subscribers
- **Rate-Limited:** Conservative 60 QPM to stay under Reddit's radar
- **Retry Logic:** 404=instant delete, 403=3 retries before removal
- **Anti-Detection:** Randomization, delays, batch pauses
- **Atomic Operations:** Scan + save + cleanup in one pass
- **Update Mode:** Refresh existing subreddit metadata
- **CSV Import:** Bulk import from subreddit lists

---

## Requirements

- Python 3.11+
- Reddit API credentials (free - see setup below)
- ~50MB disk space for database (140k subreddits)

---

## Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Setup environment
cp .env.example .env
# Edit .env with your Reddit API credentials
```

---

## Getting Reddit API Credentials

1. Go to https://www.reddit.com/prefs/apps
2. Click "Create App" or "Create Another App"
3. Fill in:
   - **name:** subdir-scanner
   - **type:** script
   - **description:** Metadata collection for SubDir
   - **redirect uri:** http://localhost:8080
4. Click "Create app"
5. Note your **client_id** and **client_secret**

Add to `.env`:
```env
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USERNAME=your_reddit_username
REDDIT_PASSWORD=your_reddit_password
```

---

## Usage

### Scan from CSV

Import subreddits from CSV and collect metadata:

```bash
# Dedupe CSV first (no API calls)
python main.py --dedupe-csv --csv ../data/subreddits.csv

# Scan new subreddits
python main.py --scan-csv --csv ../data/subreddits.csv --limit 1000

# Custom rate limit
python main.py --scan-csv --csv my-subs.csv --limit 500 --rpm 50
```

**CSV Format:**
```csv
subreddit,subscribers
python,1234567
programming,5432109
learnpython,890123
```

### Update Existing Metadata

Refresh metadata for existing subreddits:

```bash
# Update all subreddits
python main.py --update --limit 5000

# Update only stale (30+ days old)
python main.py --update --limit 5000 --stale-days 30

# Update specific subreddit
python main.py --update-sub python
```

### Database Operations

```bash
# Show statistics
python main.py --stats

# Vacuum database (reclaim space after deletions)
python main.py --vacuum

# Export to CSV
python main.py --export --output subreddits_export.csv
```

---

## Configuration

### Environment Variables (.env)

```env
# Reddit API (REQUIRED)
REDDIT_CLIENT_ID=your_id
REDDIT_CLIENT_SECRET=your_secret
REDDIT_USERNAME=your_username
REDDIT_PASSWORD=your_password

# Database (optional)
DATABASE_PATH=../data/subreddit_scanner.db

# Rate Limiting (optional)
REQUESTS_PER_MINUTE=60
MIN_DELAY=1.0
MAX_DELAY=2.0

# Filtering (optional)
MIN_SUBSCRIBERS=100
```

### Command-Line Options

```bash
# Scan modes
--scan-csv              # Scan from CSV
--update                # Update existing subs
--update-sub NAME       # Update specific sub

# Filtering
--limit N              # Process N subreddits
--min-subs N           # Minimum subscriber count (default: 100)
--stale-days N         # Only update subs older than N days

# Rate limiting
--rpm N                # Requests per minute (default: 60)
--pause-min N          # Min pause between batches (seconds)
--pause-max N          # Max pause between batches (seconds)

# CSV options
--csv FILE             # CSV file path
--dedupe-csv           # Remove duplicates from CSV

# Database
--stats                # Show database statistics
--vacuum               # Compact database
--export               # Export to CSV
--output FILE          # Export output file
```

---

## Database Schema

**Table: subreddits**

```sql
CREATE TABLE subreddits (
    -- Core
    name TEXT PRIMARY KEY,
    title TEXT,
    description TEXT,
    description_full TEXT,
    
    -- Stats
    subscribers INTEGER,
    active_users INTEGER,
    created_utc INTEGER,
    
    -- Flags
    over_18 BOOLEAN,
    subreddit_type TEXT,
    status TEXT,  -- active/deleted/private/banned
    
    -- Visual (v4)
    icon_url TEXT,
    primary_color TEXT,
    advertiser_category TEXT,
    
    -- Categorization (v4)
    category TEXT,
    tags TEXT,  -- JSON array for multi-label
    language TEXT DEFAULT 'en',
    
    -- Submission settings
    submission_type TEXT,
    allow_images BOOLEAN,
    allow_videos BOOLEAN,
    allow_galleries BOOLEAN,
    allow_videogifs BOOLEAN,
    allow_polls BOOLEAN,
    spoilers_enabled BOOLEAN,
    
    -- Tracking
    last_updated INTEGER,
    retry_count INTEGER DEFAULT 0,
    
    -- Indexes
    CREATE INDEX idx_subscribers ON subreddits(subscribers DESC);
    CREATE INDEX idx_status ON subreddits(status);
    CREATE INDEX idx_over18 ON subreddits(over_18);
    CREATE INDEX idx_updated ON subreddits(last_updated);
);
```

---

## How It Works

### Metadata Collection Flow

```
1. Load subreddits from CSV or database
   ↓
2. Filter (status=pending, no metadata yet)
   ↓
3. For each subreddit:
   a. Fetch /r/{name}/about from Reddit API
   b. Extract metadata (subscribers, description, icons, etc.)
   c. Save to database
   d. Update status (active/deleted/private/error)
   ↓
4. Auto-cleanup (< 100 subscribers or deleted/banned)
   ↓
5. Database statistics updated
```

### Rate Limiting

**Conservative approach:**
- 60 requests/minute (Reddit allows 100)
- 1-2 second delays between requests
- 30-60 second pauses every 50 subreddits
- Randomization to avoid detection

**3-Window System:**
- Per-minute: 60 requests
- Per-10-seconds: 10 requests
- Per-second: 1 request

### Smart Filtering

**Automatically removes:**
- Deleted subreddits (404 response)
- Private subreddits (403 after retries)
- Banned/quarantined (status check)
- User profiles (u_* prefix)
- < 100 subscribers (configurable)

**Retry logic:**
- 404 (not found): Instant deletion
- 403 (forbidden): 3 retries, then mark private
- 500 (server error): Retry with backoff
- Other errors: Skip, increment retry_count

---

## Anti-Detection

The scanner implements several techniques to avoid triggering Reddit's abuse detection:

1. **Randomization:**
   - Variable delays (1-2 seconds)
   - Random batch sizes (45-55 subs)
   - Shuffled processing order

2. **Human-like Patterns:**
   - Breaks every 50 subs (30-60 seconds)
   - Occasional long breaks (5-10 minutes)
   - Avoid perfect timing patterns

3. **Conservative Limits:**
   - 60 QPM (well under 100 limit)
   - Multiple rate limit windows
   - Graceful backoff on errors

---

## Production Use

### Daily Metadata Refresh

```bash
#!/bin/bash
# cron: 0 2 * * * /path/to/update-metadata.sh

cd /path/to/scanner
source venv/bin/activate
python main.py --update --limit 5000 --stale-days 30
python main.py --vacuum
```

### Weekly Full Scan

```bash
#!/bin/bash
# cron: 0 3 * * 0 /path/to/weekly-scan.sh

cd /path/to/scanner
source venv/bin/activate
python main.py --update --limit 50000
python main.py --stats
```

---

## Troubleshooting

### Rate Limit Errors (429)

**Cause:** Exceeded Reddit's rate limits

**Fix:**
```bash
# Reduce rate limit
python main.py --update --rpm 50 --limit 1000

# Increase delays
python main.py --update --pause-min 60 --pause-max 120
```

### Authentication Errors (401)

**Cause:** Invalid Reddit credentials

**Fix:**
1. Verify credentials at https://www.reddit.com/prefs/apps
2. Check .env file for typos
3. Ensure app type is "script" not "web app"

### No Subreddits Found

**Cause:** CSV missing or empty

**Fix:**
```bash
# Check CSV format
head -5 subreddits.csv

# Verify subreddits exist in database
python main.py --stats
```

### Database Locked Errors

**Cause:** Multiple processes accessing database

**Fix:**
- Only run one scanner instance at a time
- Close any DB browser tools
- Restart if needed

---

## Performance

### Benchmarks

- **Metadata collection:** ~500 subs/hour (conservative)
- **Database size:** ~350KB per 1000 subs
- **Memory usage:** ~50MB (Python process)
- **CPU usage:** Minimal (network-bound)

### Optimization Tips

1. **Increase rate limit** (max 100 QPM)
2. **Reduce delays** for faster collection
3. **Increase batch size** (process more between pauses)
4. **Disable randomization** (dev only)

**Warning:** Aggressive settings risk account suspension!

---

## Development

### Project Structure

```
scanner/
├── main.py              # CLI entry point
├── scanner.py           # Core scanning logic
├── database.py          # SQLite operations
├── reddit_client.py     # Reddit API wrapper
├── config.py            # Configuration
├── rate_limiter.py      # Rate limiting logic
└── requirements.txt     # Dependencies
```

### Adding New Metadata Fields

1. Update database schema (migration)
2. Update `reddit_client.py` to extract field
3. Update `scanner.py` to save field
4. Update web app to display field

---

## Best Practices

### API Usage

- **Never exceed 100 QPM** (Reddit's hard limit)
- **Use descriptive User-Agent** (identifies your app)
- **Respect retry-after headers** (if provided)
- **Monitor for 429 errors** (rate limit warnings)

### Data Quality

- **Update metadata weekly** (subscriber counts change)
- **Vacuum database monthly** (reclaim deleted space)
- **Export backups regularly** (prevent data loss)
- **Monitor deleted subs** (understand ecosystem changes)

### Security

- **Never commit .env** to version control
- **Rotate credentials** if compromised
- **Use read-only accounts** when possible
- **Monitor API usage** via Reddit's apps page

---

## Integration

### With SubDir Web App

The scanner maintains the SQLite database that powers the SubDir web application:

1. Scanner collects metadata → SQLite database
2. Web app reads database → Search/browse interface
3. Weekly scanner updates → Fresh subscriber counts

### With Other Tools

Export data for use in other applications:

```bash
# Full export
python main.py --export --output all_subs.csv

# Filtered export (via SQL)
sqlite3 ../data/subreddit_scanner.db \
  "SELECT * FROM subreddits WHERE subscribers > 100000" \
  -csv -header > large_subs.csv
```

---

## License

MIT License - See main repository LICENSE for details.

---

## Credits

**Built for the datahoarder and selfhosted communities.**

Part of the SubDir project - A searchable directory of Reddit communities.

---

**Last Updated:** February 2026  
**Version:** v4 Schema (Icons, Colors, Categories)

See main [README.md](../README.md) for SubDir project overview.
