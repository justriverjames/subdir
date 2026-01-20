# SubDir

**A searchable directory of over 140,000 active subreddits** - metadata service for Reddit communities.

SubDir provides a clean, fast interface for discovering subreddits with full metadata including subscriber counts, descriptions, icons, NSFW flags, and more.

---

## Features

- **140,000+ active subreddits** with full metadata
- **Instant search** - no Reddit API calls needed, results up to 10k per query
- **NSFW filtering** - toggle adult content on/off
- **Rich metadata** - subscribers, descriptions, icons, colors, categories
- **REST API** for programmatic access
- **Self-hostable** - run locally or deploy to your VPS
- **Browse mode** - explore top 3000 subreddits (all/SFW/NSFW)
- **Optimized** - cached stats, WAL mode, ready for high traffic
- **Database** - 33MB SQLite (only active subreddits, 100+ subscribers)

---

## Quick Start

### Web Frontend (Next.js)

```bash
cd web
npm install
npm run dev
```

Then open: **http://localhost:3000**

### Scanner (Data Collection)

```bash
cd scanner
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with Reddit API credentials

# Dedupe CSV (fast, no API calls)
python main.py --dedupe-csv --csv ../data/subreddits.csv

# Scan new subreddits from CSV
python main.py --scan-csv --csv ../data/subreddits.csv --limit 1000

# Update existing subreddits
python main.py --update --limit 1000
```

See [scanner/README.md](scanner/README.md) for detailed documentation.

---

## Components

### 1. Web Frontend (Next.js + TypeScript)
Modern search interface with:
- Real-time search across 140,000+ active subreddits
- Browse top 3000 (all/SFW/NSFW filtered)
- NSFW content filtering toggle
- Subreddit icons and branding colors
- Autocomplete with icon preview
- Export to JSON/CSV (full database or filtered)
- Responsive mobile-friendly design
- Cached stats (5min) for high traffic

**Stack:** Next.js 16, TypeScript, Tailwind CSS, better-sqlite3 (WAL mode)

### 2. Scanner (Python CLI)
Collects subreddit metadata from Reddit API:
- **Metadata:** subscribers, descriptions, icons, colors, categories
- **Rate-limited (60 QPM)** - balanced for reliability
- **Smart filtering:** Only active subs with 100+ subscribers
- **Retry logic:** 404=instant delete, 403=3 retries before removal
- **Anti-detection:** Randomization, delays, batch pauses
- **Atomic CSV mode:** Scan + save + remove in one pass
- **Update mode:** Refresh existing subreddit metadata

**Stack:** Python 3.11+, httpx, SQLite, asyncio

---

## API Endpoints

The Next.js app provides internal API routes:

- `GET /api/search?q={query}&limit={n}&nsfw={bool}` - Search subreddits (up to 10k results)
- `GET /api/browse?mode={all|sfw|nsfw}&limit={n}` - Browse top subreddits (up to 5k)
- `GET /api/autocomplete?q={query}&nsfw={bool}` - Autocomplete suggestions
- `GET /api/stats` - Database statistics (cached 5min)
- `GET /api/subreddits/{name}` - Get subreddit details
- `GET /api/export/json?format=minimal|full&mode={all|sfw|nsfw}` - JSON export
- `GET /api/export/csv?mode={all|sfw|nsfw}` - CSV export

---

## Database Schema

**Current Version:** v4

**Core Fields:**
- name, title, description
- subscribers, active_users
- over_18, subreddit_type
- created_utc, last_updated
- status (active only - deleted/banned subs removed)
- retry_count (for update failure tracking)

**Visual/Branding (v4):**
- icon_url, primary_color
- advertiser_category (Reddit's internal category)
- submission_type, allow_images, allow_videos, allow_polls

**Search/Discovery (v4):**
- category, tags (for future multi-label categorization)
- language (defaults to 'en')

**Quality Filters:**
- Only active subreddits (status='active')
- Minimum 100 subscribers
- No user profiles (u_*)
- No deleted/banned/quarantined

---

## Use Cases

### For Researchers
- Bulk metadata exports for analysis
- Explore subreddit ecosystem
- Category-based discovery

### For Developers
- Build Reddit tools without hitting API limits
- Pre-populate databases for testing
- Subreddit discovery features

---

## Architecture

```
subdir/
├── scanner/              # Python CLI for data collection
│   ├── main.py          # CLI entry point
│   ├── scanner.py       # Core scanning logic
│   ├── database.py      # SQLite operations
│   ├── reddit_client.py # Reddit API wrapper
│   └── README.md        # Scanner documentation
│
├── web/                 # Next.js web frontend
│   ├── app/             # Next.js App Router
│   │   ├── page.tsx    # Search interface
│   │   └── api/        # API routes
│   └── lib/            # Database connection
│
├── data/               # SQLite database (33MB)
│   └── subreddit_scanner.db
│
├── README.md           # This file
├── ROADMAP.md          # Development roadmap
├── CLAUDE.md           # Developer workflow for Claude
└── CATEGORIZATION.md   # Future categorization plans
```

---

## Deployment

### Production Build

```bash
cd web
npm run build
npm start
```

Set environment variable for database location:
```bash
# web/.env.local
DATABASE_PATH=../data/subreddit_scanner.db
```

### VPS Deployment
- Upload database to VPS
- Build Next.js app
- Run behind Nginx reverse proxy
- Configure Cloudflare DNS

See deployment notes in scanner/README.md for details.

---

## Data Updates

Run scanner periodically to refresh metadata:

```bash
cd scanner
source venv/bin/activate

# Update existing subreddits (refreshes metadata)
python main.py --update --limit 5000

# Scan new subreddits from CSV
python main.py --scan-csv --csv ../data/new_subs.csv

# Show database statistics
python main.py --stats

# Compact database after cleanup
python main.py --vacuum
```

**Recommended:** Weekly metadata refresh to keep subscriber counts current.
**Auto-cleanup:** Scanner automatically removes deleted/banned subs after 3 failed attempts.

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for full development plans.

**Current Status (Pre-v1.0):**
- ✅ Database schema v4 (icons, colors, categories)
- ✅ 140,000+ active subreddits scanned
- ✅ Web UI with search, browse, autocomplete
- ✅ Performance optimizations (caching, WAL mode)
- ✅ Smart scanner with retry logic and anti-detection
- ⏳ AI-powered categorization (future - see CATEGORIZATION.md)
- ⏳ Multi-label tagging system (future)

**v1.0 Goals:**
- Production-ready web interface ✅
- Public deployment at subdir.justriverjames.com
- Weekly automated metadata refresh

---

## Contributing

Built for the datahoarder and selfhosted communities. Contributions welcome!

**Areas of interest:**
- AI categorization improvements
- Search enhancements
- UI/UX improvements
- Documentation

---

## Tech Stack

- **Frontend:** Next.js 16, TypeScript, Tailwind CSS
- **Scanner:** Python 3.11+, httpx, SQLite, asyncio
- **Database:** SQLite 3 with WAL mode
- **Deployment:** Debian 13 VPS + Nginx + Cloudflare
- **Caching:** 5min ISR for stats, HTTP cache headers for CDN

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Disclaimer

SubDir is not affiliated with, endorsed by, or connected to Reddit, Inc. All data is collected through Reddit's public API in accordance with their API terms of service. Subreddit names, descriptions, and metadata are property of their respective communities and Reddit, Inc.

---

## Credits

**Built for the datahoarder and selfhosted communities.**

**Live Site:** https://subdir.justriverjames.com
