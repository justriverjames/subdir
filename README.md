# SubDir

**A searchable directory of 29,000+ subreddits** - metadata service for Reddit communities.

SubDir provides a clean, fast interface for discovering subreddits with full metadata including subscriber counts, descriptions, NSFW flags, and more.

---

## Features

- **29,404 subreddits** with full metadata
- **Instant search** - no Reddit API calls needed
- **NSFW filtering** - toggle adult content on/off
- **Rich metadata** - subscribers, descriptions, icons, categories
- **REST API** for programmatic access
- **Self-hostable** - run locally or deploy to your VPS
- **Lightweight** - 8.7MB database

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

# Import subreddits and collect metadata
python main.py --ingest subreddits.csv
python main.py --metadata
```

See [scanner/README.md](scanner/README.md) for detailed documentation.

---

## Components

### 1. Web Frontend (Next.js + TypeScript)
Modern search interface with:
- Real-time search across 29,000+ subreddits
- NSFW content filtering
- Subreddit icons and branding colors
- Category badges
- Export to JSON/CSV
- Responsive design with Tailwind CSS

**Stack:** Next.js 16, TypeScript, Tailwind CSS, SQLite (read-only)

### 2. Scanner (Python CLI)
Collects subreddit metadata from Reddit API:
- Metadata: subscribers, descriptions, icons, categories
- Rate-limited (85 QPM) to respect Reddit's API limits
- Incremental updates
- Schema migrations

**Stack:** Python 3.11+, httpx, SQLite, asyncio

---

## API Endpoints

The Next.js app provides internal API routes:

- `GET /api/search?q={query}&limit={n}&nsfw={bool}` - Search subreddits
- `GET /api/stats` - Database statistics
- `GET /api/subreddits/{name}` - Get subreddit details
- `GET /api/export/json?format=minimal|full` - JSON export
- `GET /api/export/csv` - CSV export

---

## Database Schema

**Current Version:** v3 (migrating to v4)

**Core Fields:**
- name, title, description
- subscribers, active_users
- over_18, subreddit_type
- created_utc, last_updated

**v4 Additions (in progress):**
- icon_url, primary_color
- advertiser_category (Reddit's category)
- submission_type, allow_images, allow_videos
- category, tags (multi-label categorization)

**Size:** 8.7MB SQLite database

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
├── data/               # SQLite database
│   └── subreddit_scanner.db
│
├── README.md           # This file
├── ROADMAP.md          # Development roadmap
└── MIGRATION_SUMMARY.md # Database migration history
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
python main.py --metadata  # Update existing subreddits
```

**Recommended:** Weekly metadata refresh to keep subscriber counts current.

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for full development plans.

**Current Focus (Pre-v1.0):**
- ✅ Database migration to v3 (completed)
- 🚧 Add visual metadata (icons, colors) - v4 schema
- 🚧 AI-powered categorization using Claude API
- 🚧 Multi-label tagging system
- ⏳ Beta testing

**v1.0 Goals:**
- Production-ready web interface
- Categorized subreddit directory
- Public deployment at subdir.justriverjames.com

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
- **Scanner:** Python 3.11+, httpx, SQLite
- **Database:** SQLite 3 (8.7MB)
- **Deployment:** VPS + Nginx + Cloudflare

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
