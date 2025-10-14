# SubDir API

Simple Node.js API for querying subreddit metadata.

## Quick Start

```bash
# Install dependencies
npm install

# Start server
npm start

# Or with auto-reload
npm run dev
```

Access API at: http://localhost:7733

## Environment Variables

- `PORT` - Server port (default: 7733)
- `DB_PATH` - Path to SQLite database (default: `../data/subreddit_scanner.db`)

## Endpoints

- `GET /api/health` - Health check
- `GET /api/search?q=python` - Search subreddits
- `GET /api/subreddits/{name}` - Get subreddit metadata
- `GET /api/subreddits/{name}/threads` - Get thread IDs
- `GET /api/stats` - Database statistics
- `GET /api/export/metadata.json` - Bulk export (JSON)
- `GET /api/export/metadata.json.gz` - Bulk export (gzipped)

## License

MIT - see [../LICENSE](../LICENSE)
