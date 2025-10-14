# SubDir Web UI

Simple web interface for browsing and searching subreddits.

## Features

- Instant search across 29k+ subreddits
- Clean, responsive design (Tailwind CSS)
- Stats dashboard
- Mobile-friendly
- No build step - vanilla JS

## Running Locally

```bash
# Install dependencies
npm install

# Start server
npm start

# Or with auto-reload
npm run dev
```

Access at: http://localhost:7734

## Environment Variables

- `PORT` - Server port (default: 7734)
- `API_URL` - API backend URL (default: http://localhost:7733)

## Structure

```
web/
├── public/
│   ├── index.html       # Main HTML
│   └── js/
│       ├── api.js       # API client
│       ├── search.js    # Search logic
│       └── app.js       # App initialization
├── server.js            # Express server
├── package.json
└── Dockerfile
```

## Development

The UI is built with:
- **HTML/CSS** - Tailwind CSS via CDN
- **JavaScript** - Vanilla JS (ES6+)
- **Express** - Static file server + API proxy

No build step required - edit files and refresh!

## License

MIT - see [../LICENSE](../LICENSE)
