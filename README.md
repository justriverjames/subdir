# SubDir

**Metadata service for Reddit communities** - like TheTVDB for Sonarr/Radarr, but for Reddit.

SubDir provides a searchable catalog of 29,000+ subreddits with pre-collected thread IDs, enabling instant discovery and faster archiving workflows.

---

## Features

- **29,404 subreddits** with full metadata (subscribers, descriptions, NSFW flags, etc.)
- **782,533 thread IDs** pre-collected from Hot/Top feeds
- **Instant search** across all subreddits (no Reddit API calls needed)
- **REST API** for programmatic access
- **Web UI** for browsing and discovery
- **Bulk exports** for offline use (~5MB gzipped)
- **Self-hostable** - run locally or deploy to your own server

---

## Quick Start

### Local Development

Run both services in separate terminals:

**Terminal 1 - API (port 7733):**
```bash
cd api
npm install
npm start
```

**Terminal 2 - Web UI (port 7734):**
```bash
cd web
npm install
npm start
```

Then open: **http://localhost:7734**

**Scanner (optional - for collecting fresh data):**
```bash
cd scanner
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with Reddit API credentials
python main.py --ingest       # Import subreddits from CSV
python main.py --metadata     # Collect subreddit metadata
python main.py --threads      # Collect thread IDs
```

### Public Instance

Live instance will be hosted at: **[subdir.hammond.im](https://subdir.hammond.im)** (coming soon)

**Ports:**
- API: 7733
- Web UI: 7734
- (Sequential, unique to SubDir project)

---

## Components

### 1. Scanner (Python CLI)
Collects subreddit metadata and thread IDs from Reddit API.

```bash
cd scanner

# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your Reddit API credentials

# Usage
python main.py --ingest      # Import subreddits from CSV
python main.py --metadata    # Collect metadata
python main.py --threads     # Collect thread IDs
```

See [scanner/README.md](scanner/README.md) for detailed documentation.

### 2. API (FastAPI)
REST API for querying subreddit data.

**Endpoints:**
- `GET /api/search?q=python` - Search subreddits
- `GET /api/subreddits/{name}` - Get metadata
- `GET /api/subreddits/{name}/threads` - Get thread IDs
- `GET /api/export/metadata.json.gz` - Bulk metadata export
- `GET /api/stats` - Database statistics

See [docs/API.md](docs/API.md) for full API documentation.

### 3. Web UI
Simple search interface for browsing subreddits.

- Instant search across 29k+ subreddits
- View subscribers, descriptions, NSFW status
- Click through to Reddit or view thread list
- Mobile responsive

---

## Use Cases

### For Redditarr Users
SubDir provides instant subreddit discovery and pre-populated thread IDs, eliminating slow Reddit API pagination:

**Without SubDir:**
- Search "python" → Query Reddit API (rate-limited)
- Paginate through posts (2-3 minutes for 1500 threads)

**With SubDir:**
- Search "python" → Instant results from local cache
- Get 1523 thread IDs instantly → Skip pagination entirely

See [docs/INTEGRATION.md](docs/INTEGRATION.md) for integration guide.

### For Researchers
- Bulk download metadata for analysis
- Explore subreddit ecosystem
- Find related communities
- Track subscriber growth (with periodic re-scanning)

### For Developers
- Build Reddit-related tools without hitting API limits
- Pre-populate databases for testing
- Subreddit discovery features in your apps

---

## Architecture

```
subdir/
├── scanner/        # Python CLI for data collection
├── api/            # FastAPI backend
├── web/            # Web UI (HTML/JS)
├── data/           # SQLite database (106MB)
└── docs/           # Documentation
```

**Tech Stack:**
- **Scanner:** Python 3.11+, httpx, SQLite (data collection)
- **API:** Node.js, Express, SQLite (read-only)
- **Web UI:** Vanilla JS, Tailwind CSS, Express
- **Deployment:** VPS with Nginx + Cloudflare

---

## Deployment

### VPS Deployment (Production)

```bash
# On your VPS
git clone https://github.com/justriverjames/subdir.git
cd subdir

# Start services
docker-compose -f docker-compose.prod.yml up -d

# Setup Nginx reverse proxy (see docs/DEPLOYMENT.md)
# Setup SSL with Let's Encrypt
# Configure Cloudflare DNS + caching
```

See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for complete deployment guide.

### Data Updates

Run scanner periodically to keep data fresh:

```bash
# Manually
cd scanner
python main.py --metadata
python main.py --threads

# Or setup cron job
0 2 * * 0 cd /path/to/subdir/scanner && python main.py --metadata && python main.py --threads
```

---

## API Integration

### Bulk Metadata Export
```bash
# Download entire dataset (5MB gzipped)
curl https://subdir.hammond.im/api/export/metadata.json.gz -o metadata.json.gz
gunzip metadata.json.gz
```

### Search Example
```bash
curl "https://subdir.hammond.im/api/search?q=python&limit=10"
```

### Thread IDs Example
```bash
curl "https://subdir.hammond.im/api/subreddits/python/threads"
```

See [docs/API.md](docs/API.md) for complete API documentation.

---

## Data & Privacy

### What's Collected
- Subreddit names and metadata (subscribers, descriptions, NSFW flags)
- Thread IDs (post IDs, no content)
- All data sourced from public Reddit API

### What's NOT Collected
- Post content, titles, or comments
- User data or personal information
- Private subreddit data

### Legal
SubDir hosts only **metadata** - no Reddit content. Similar services:
- subredditstats.com (statistics)
- pushshift (metadata archives)
- Reddit's own public API

All data is publicly available via Reddit's API. SubDir simply aggregates and provides convenient access.

---

## Development

### Project Structure
```
subdir/
├── scanner/               # Data collection
│   ├── main.py           # CLI entry point
│   ├── scanner.py        # Core scanning logic
│   ├── database.py       # SQLite operations
│   └── reddit_client.py  # Reddit API wrapper
│
├── api/                  # REST API
│   ├── main.py          # FastAPI app
│   ├── routes/          # API endpoints
│   └── models.py        # Data models
│
├── web/                 # Web UI
│   ├── public/          # Static files
│   └── server.js        # Express server
│
├── data/                # Shared database
│   └── subreddit_scanner.db
│
└── docs/                # Documentation
    ├── API.md
    ├── DEPLOYMENT.md
    └── INTEGRATION.md
```

### Running Tests
```bash
# API tests
cd api
pytest

# Scanner tests
cd scanner
pytest
```

---

## Contributing

We welcome contributions! Areas of interest:

- **AI Categorization:** Categorize subreddits (Technology/Science/Entertainment/etc.)
- **Enhanced Search:** Fuzzy search, category filters, advanced sorting
- **Web UI:** Improve design, add features
- **Performance:** Optimize queries, caching strategies
- **Documentation:** Improve guides and examples

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for planned features and development timeline.

**v1.0 (Current):**
- ✅ Scanner CLI
- ✅ REST API
- ✅ Basic Web UI
- ✅ Docker deployment

**v1.1 (Next):**
- AI-powered categorization
- Enhanced search features
- Redditarr integration

**Future:**
- PostgreSQL migration
- User accounts & saved searches
- Historical data tracking
- Advanced analytics

---

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Credits

**Built for the datahoarder and selfhosted communities.**

SubDir is complementary to [Redditarr](https://github.com/justriverjames/redditarr) - a self-hosted Reddit archiving tool.

---

## Support

- **Issues:** [GitHub Issues](https://github.com/justriverjames/subdir/issues)
- **Documentation:** [docs/](docs/)
- **Discussions:** [GitHub Discussions](https://github.com/justriverjames/subdir/discussions)

---

**Stats:** 29,404 subreddits | 782,533 thread IDs | 106MB database | Updated October 2025
