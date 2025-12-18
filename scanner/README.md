# SubDir Scanner

Python CLI tool for collecting subreddit metadata and thread IDs from Reddit's public API.

---

## Features

- Collect subreddit metadata (subscribers, descriptions, NSFW flags, etc.)
- Collect thread IDs from Hot/Top feeds
- SQLite storage with efficient indexing
- Rate-limit compliant (respects Reddit's 100 QPM limit)
- Resumable (tracks progress, handles errors gracefully)
- Batch processing with cooldown periods

---

## Requirements

- Python 3.11+
- Reddit API credentials (free - see setup below)
- ~150MB disk space for database

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
   - **name:** subdir-scanner (or anything)
   - **type:** script
   - **description:** (optional)
   - **redirect uri:** http://localhost:8080
4. Click "Create app"
5. Note your **client_id** (under app name) and **client_secret**

Add these to `.env`:
```
REDDIT_CLIENT_ID=your_client_id_here
REDDIT_CLIENT_SECRET=your_client_secret_here
REDDIT_USERNAME=your_reddit_username
REDDIT_PASSWORD=your_reddit_password
```

---

## Usage

### Step 1: Ingest Subreddits from CSV

```bash
python main.py --ingest

# Custom CSV file
python main.py --ingest --csv my-subreddits.csv
```

**CSV Format:**
```csv
subreddit,subscribers
python,1234567
learnpython,890123
programming,5432109
```

Only adds NEW subreddits (skips existing ones).

### Step 2: Collect Metadata

```bash
python main.py --metadata
```

Collects full metadata for all pending subreddits:
- Title, description, public description
- Subscriber count, active users
- NSFW flag, subreddit type
- Created date
- Status (public/private/banned/etc.)

### Step 3: Collect Thread IDs

```bash
python main.py --threads
```

Collects thread IDs from:
- Hot posts (current trending)
- Top all-time posts
- Top year posts

Skip specific feeds:
```bash
python main.py --threads --no-hot          # Skip hot
python main.py --threads --no-top-all      # Skip top all-time
python main.py --threads --no-top-year     # Skip top year
```

### Maintenance Commands

**Clean up user profiles:**
```bash
python main.py --cleanup
```

Removes `u_*` entries (user profiles, not real subreddits).

**Compact database:**
```bash
python main.py --vacuum
```

Run after cleanup or large deletions to reclaim disk space.

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `REDDIT_CLIENT_ID` | Yes | - | Reddit API client ID |
| `REDDIT_CLIENT_SECRET` | Yes | - | Reddit API client secret |
| `REDDIT_USERNAME` | Yes | - | Your Reddit username |
| `REDDIT_PASSWORD` | Yes | - | Your Reddit password |
| `SCANNER_DB_PATH` | No | `subreddit_scanner.db` | Database file path |
| `SCANNER_LOG_DIR` | No | `logs` | Log directory |
| `LOG_LEVEL` | No | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |

### Command Line Options

```bash
# Database location
python main.py --metadata --db /path/to/db.sqlite

# Logging
python main.py --metadata --log-dir /path/to/logs --log-level DEBUG

# Rate limiting (default: 60 QPM)
python main.py --metadata --rate-limit 50

# Cooldown between subreddits (default: 30s)
python main.py --metadata --cooldown 60
```

---

## Database Schema

### Tables

**subreddits**
- name (PRIMARY KEY)
- title, description, public_description
- subscribers, active_users
- over_18 (NSFW flag)
- subreddit_type (public/private/restricted/archived)
- created_utc
- status (pending/active/private/banned/quarantined/deleted/error)
- last_updated, last_checked
- retry_count, error_message
- metadata_collected, threads_collected (flags)

**thread_ids**
- thread_id (PRIMARY KEY)
- subreddit (FOREIGN KEY → subreddits.name)

**schema_version**
- version (tracks database migrations)

### Indexes

- `thread_ids.subreddit` - Fast thread lookup by subreddit
- `subreddits.status` - Filter by status
- `subreddits.subscribers` - Sort by popularity
- `subreddits.metadata_collected` - Find pending metadata
- `subreddits.threads_collected` - Find pending threads

---

## Workflow

### Initial Setup (First Time)

```bash
# 1. Ingest subreddits from CSV
python main.py --ingest
# Output: Added 10,000 new subreddits

# 2. Collect metadata (takes ~3-4 hours for 10k subs)
python main.py --metadata
# Progress: [▓▓▓▓▓░░░░░] 5432/10000 (54%)

# 3. Collect thread IDs (takes ~5-6 hours for 10k subs)
python main.py --threads
# Progress: [▓▓▓▓▓▓▓▓░░] 8234/10000 (82%)
```

### Maintenance (Periodic Updates)

```bash
# Re-collect metadata (updates subscriber counts, descriptions, etc.)
python main.py --metadata

# Re-collect thread IDs (gets new posts)
python main.py --threads
```

### Schedule with Cron

```bash
# Update metadata weekly (Sundays at 2 AM)
0 2 * * 0 cd /path/to/subdir/scanner && source venv/bin/activate && python main.py --metadata

# Update thread IDs weekly (Sundays at 4 AM)
0 4 * * 0 cd /path/to/subdir/scanner && source venv/bin/activate && python main.py --threads
```

---

## Rate Limiting

The scanner respects Reddit's API limits:
- **Reddit Limit:** 100 requests per minute (averaged over 10 minutes)
- **Scanner Default:** 60 requests per minute (conservative, 40% buffer)
- **Cooldown:** 30 seconds between subreddits (prevents sustained high load)

Adjust if needed:
```bash
python main.py --metadata --rate-limit 80 --cooldown 15
```

Never exceed 100 QPM to avoid temporary bans.

---

## Error Handling

### Common Errors

**Private Subreddit:**
```
Status: private
Error: Subreddit is private
```
✓ Normal - marked as private, skipped

**Banned/Quarantined:**
```
Status: banned
Error: Subreddit does not exist or is banned
```
✓ Normal - marked as banned, skipped

**Rate Limit Hit:**
```
Error: 429 Too Many Requests
```
✓ Scanner waits and retries automatically

**Network Error:**
```
Error: Connection timeout
```
✓ Retry count incremented, will retry later (max 3 attempts)

### Retry Logic

- Subreddits are retried up to 3 times on transient errors
- After 3 failures, marked as error status
- Re-running metadata/threads mode will retry error subreddits

---

## Performance

### Expected Times (10,000 subreddits)

| Task | Time | Rate |
|------|------|------|
| Metadata collection | 3-4 hours | ~40-50 subs/min |
| Thread ID collection | 5-6 hours | ~25-30 subs/min |
| Total (first time) | 8-10 hours | - |

### Optimization Tips

- Run overnight or during off-hours
- Increase `--rate-limit` if you have multiple IP addresses (advanced)
- Use `--no-top-all` or `--no-top-year` to skip less important feeds
- Database is efficient - no optimization needed until 100k+ subs

---

## Troubleshooting

### "No subreddits in database"
Run `--ingest` first to import subreddits from CSV.

### "Invalid credentials"
Check `.env` file has correct Reddit API credentials.

### "Database locked"
Only one scanner instance can run at a time. Stop other instances.

### "Too many retries"
Some subreddits are private/banned. This is normal. Review logs for details.

### Slow performance
- Check network connection
- Verify rate limit settings (default 60 QPM is conservative)
- Ensure no other Reddit API clients are sharing your IP

---

## Logs

Logs are saved to `logs/scanner_YYYY-MM-DD_HH-MM-SS.log`:

```
[2025-10-14 12:34:56] [INFO] Starting metadata collection...
[2025-10-14 12:35:01] [INFO] ✓ r/python - 1,234,567 subscribers
[2025-10-14 12:35:06] [INFO] ✓ r/learnpython - 890,123 subscribers
[2025-10-14 12:35:11] [WARNING] ✗ r/private_sub - Subreddit is private
```

Console output is cleaner, logs contain full details including stack traces.

---

## Advanced Usage

### Custom Database Location
```bash
export SCANNER_DB_PATH="/mnt/storage/reddit_subs.db"
python main.py --metadata
```

### Parallel Scanning (Multiple IPs)
If you have multiple IPs/VPNs:
```bash
# Terminal 1 (IP 1)
python main.py --metadata --rate-limit 60

# Terminal 2 (IP 2)
python main.py --metadata --rate-limit 60 --db scanner2.db
```
Then merge databases manually (advanced).

---

## File Structure

```
scanner/
├── main.py              # CLI entry point
├── scanner.py           # Core scanning logic
├── database.py          # SQLite operations
├── reddit_client.py     # Reddit API wrapper
├── rate_limiter.py      # Rate limiting
├── config.py            # Configuration management
├── requirements.txt     # Python dependencies
├── .env.example         # Environment template
├── .env                 # Your credentials (gitignored)
└── logs/                # Log files (gitignored)
```

---

## API Clients

### Reddit API
- Uses official Reddit API (oauth.reddit.com)
- OAuth2 authentication
- Respects rate limits
- Handles retries automatically

---

## Contributing

Improvements welcome:
- Better error handling
- Performance optimizations
- Additional metadata fields
- Parallel processing
- Progress resumption improvements

---

## License

MIT License - see [../LICENSE](../LICENSE)

---

## Support

- Issues: https://github.com/justriverjames/subdir/issues
- Documentation: https://github.com/justriverjames/subdir/tree/main/docs
