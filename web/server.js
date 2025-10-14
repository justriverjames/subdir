/**
 * Express server for SubDir Web UI
 */

const express = require('express');
const path = require('path');

const app = express();
const PORT = process.env.PORT || 7734;  // Paired with API 7733
const API_URL = process.env.API_URL || 'http://localhost:7733';

// Serve static files
app.use(express.static('public'));

// API proxy - forwards /api/* to API server (strips /api prefix)
app.use('/api', async (req, res) => {
    const url = `${API_URL}${req.url}`;  // req.url already has the path after /api
    console.log(`Proxying: /api${req.url} -> ${url}`);

    try {
        const fetch = (await import('node-fetch')).default;
        const response = await fetch(url);

        if (!response.ok) {
            console.error(`API error: ${response.status} for ${url}`);
            return res.status(response.status).json({
                error: `API returned ${response.status}`
            });
        }

        const data = await response.json();
        res.json(data);
    } catch (error) {
        console.error('API proxy error:', error);
        res.status(500).json({ error: 'API request failed: ' + error.message });
    }
});

// Serve index.html for all other routes (SPA fallback)
app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

app.listen(PORT, '0.0.0.0', () => {
    console.log(`SubDir Web UI running on http://localhost:${PORT}`);
});
