/**
 * SubDir API - Node.js backend
 */

const express = require('express');
const sqlite3 = require('sqlite3').verbose();
const path = require('path');
const cors = require('cors');
const zlib = require('zlib');

const app = express();
const PORT = process.env.PORT || 7733;  // SUB = 783 in phone keypad, DIR = 347, combined-ish
const DB_PATH = process.env.DB_PATH || path.join(__dirname, '../data/subreddit_scanner.db');

// Middleware
app.use(cors());
app.use(express.json());

// Open database
const db = new sqlite3.Database(DB_PATH, sqlite3.OPEN_READONLY, (err) => {
    if (err) {
        console.error('Failed to open database:', err);
        process.exit(1);
    }
    console.log(`✓ Database connected: ${DB_PATH}`);
});

// Health check
app.get('/health', (req, res) => {
    const fs = require('fs');
    const stats = fs.statSync(DB_PATH);
    const sizeMB = (stats.size / (1024 * 1024)).toFixed(2);

    res.json({
        status: 'healthy',
        version: '1.0.0',
        database_size_mb: parseFloat(sizeMB)
    });
});

// Search subreddits
app.get('/search', (req, res) => {
    const { q, limit = 50 } = req.query;

    if (!q) {
        return res.status(400).json({ error: 'Query parameter "q" is required' });
    }

    const queryLower = q.toLowerCase();
    const queryPattern = `%${queryLower}%`;

    // Better search: prioritize exact matches, then word boundaries
    db.all(`
        SELECT
            name, title, description, public_description,
            subscribers, active_users, over_18,
            subreddit_type, created_utc, status, last_updated,
            CASE
                WHEN LOWER(name) = ? THEN 1              -- Exact match
                WHEN LOWER(name) LIKE ? THEN 2           -- Starts with
                WHEN LOWER(name) LIKE ? THEN 3           -- Ends with
                WHEN LOWER(name) LIKE ? THEN 4           -- Contains
                WHEN LOWER(title) LIKE ? THEN 5          -- In title
                WHEN LOWER(description) LIKE ? THEN 6    -- In description
                ELSE 7
            END as relevance
        FROM subreddits
        WHERE (
            LOWER(name) LIKE ?
            OR LOWER(title) LIKE ?
            OR LOWER(description) LIKE ?
            OR LOWER(public_description) LIKE ?
        )
        AND status = 'active'
        ORDER BY relevance ASC, subscribers DESC NULLS LAST
        LIMIT ?
    `, [
        queryLower,                    // exact match
        `${queryLower}%`,             // starts with
        `%${queryLower}`,             // ends with
        queryPattern,                  // contains
        queryPattern,                  // title
        queryPattern,                  // description
        queryPattern,                  // name search
        queryPattern,                  // title search
        queryPattern,                  // description search
        queryPattern,                  // public_description search
        parseInt(limit)
    ], (err, rows) => {
        if (err) {
            console.error('Search error:', err);
            return res.status(500).json({ error: 'Database error' });
        }

        res.json({
            subreddits: rows.map(row => {
                const { relevance, ...rest } = row;  // Remove relevance from output
                return {
                    ...rest,
                    over_18: Boolean(rest.over_18)
                };
            }),
            total: rows.length,
            limit: parseInt(limit)
        });
    });
});

// Get subreddit details
app.get('/subreddits/:name', (req, res) => {
    const { name } = req.params;

    db.get(`
        SELECT
            name, title, description, public_description,
            subscribers, active_users, over_18,
            subreddit_type, created_utc, status, last_updated
        FROM subreddits
        WHERE name = ?
    `, [name.toLowerCase()], (err, row) => {
        if (err) {
            return res.status(500).json({ error: 'Database error' });
        }

        if (!row) {
            return res.status(404).json({ error: `Subreddit '${name}' not found` });
        }

        // Get thread count
        db.get(`
            SELECT COUNT(*) as count
            FROM thread_ids
            WHERE subreddit = ?
        `, [name.toLowerCase()], (err, countRow) => {
            res.json({
                ...row,
                over_18: Boolean(row.over_18),
                thread_count: countRow ? countRow.count : 0
            });
        });
    });
});

// Get thread IDs
app.get('/subreddits/:name/threads', (req, res) => {
    const { name } = req.params;

    // Verify subreddit exists
    db.get('SELECT name FROM subreddits WHERE name = ?', [name.toLowerCase()], (err, row) => {
        if (err) {
            return res.status(500).json({ error: 'Database error' });
        }

        if (!row) {
            return res.status(404).json({ error: `Subreddit '${name}' not found` });
        }

        // Get thread IDs
        db.all(`
            SELECT thread_id
            FROM thread_ids
            WHERE subreddit = ?
            ORDER BY thread_id
        `, [name.toLowerCase()], (err, rows) => {
            if (err) {
                return res.status(500).json({ error: 'Database error' });
            }

            res.json({
                subreddit: name.toLowerCase(),
                threads: rows.map(r => r.thread_id),
                count: rows.length
            });
        });
    });
});

// Stats
app.get('/stats', (req, res) => {
    const stats = {};

    db.get('SELECT COUNT(*) as count FROM subreddits', (err, row) => {
        stats.total_subreddits = row.count;

        db.get('SELECT COUNT(*) as count FROM subreddits WHERE status = "active"', (err, row) => {
            stats.active_subreddits = row.count;

            db.get('SELECT COUNT(*) as count FROM subreddits WHERE over_18 = 1 AND status = "active"', (err, row) => {
                stats.nsfw_subreddits = row.count;

                db.get('SELECT COUNT(*) as count FROM thread_ids', (err, row) => {
                    stats.total_threads = row.count;

                    db.get('SELECT MAX(last_updated) as latest FROM subreddits WHERE last_updated IS NOT NULL', (err, row) => {
                        stats.last_updated = row.latest ? new Date(row.latest * 1000).toISOString() : null;
                        res.json(stats);
                    });
                });
            });
        });
    });
});

// Bulk export (JSON)
app.get('/export/metadata.json', (req, res) => {
    db.all(`
        SELECT
            s.name, s.title, s.description, s.public_description,
            s.subscribers, s.active_users, s.over_18,
            s.subreddit_type, s.created_utc, s.status, s.last_updated,
            COUNT(t.thread_id) as thread_count
        FROM subreddits s
        LEFT JOIN thread_ids t ON s.name = t.subreddit
        WHERE s.status = 'active'
        GROUP BY s.name
        ORDER BY s.subscribers DESC NULLS LAST
    `, (err, rows) => {
        if (err) {
            return res.status(500).json({ error: 'Database error' });
        }

        const data = {
            version: '1.0.0',
            total_subreddits: rows.length,
            subreddits: rows.map(row => ({
                ...row,
                over_18: Boolean(row.over_18)
            }))
        };

        res.json(data);
    });
});

// Bulk export (gzipped)
app.get('/export/metadata.json.gz', (req, res) => {
    db.all(`
        SELECT
            s.name, s.title, s.description, s.public_description,
            s.subscribers, s.active_users, s.over_18,
            s.subreddit_type, s.created_utc, s.status, s.last_updated,
            COUNT(t.thread_id) as thread_count
        FROM subreddits s
        LEFT JOIN thread_ids t ON s.name = t.subreddit
        WHERE s.status = 'active'
        GROUP BY s.name
        ORDER BY s.subscribers DESC NULLS LAST
    `, (err, rows) => {
        if (err) {
            return res.status(500).json({ error: 'Database error' });
        }

        const data = {
            version: '1.0.0',
            total_subreddits: rows.length,
            subreddits: rows.map(row => ({
                ...row,
                over_18: Boolean(row.over_18)
            }))
        };

        const json = JSON.stringify(data);
        zlib.gzip(json, (err, compressed) => {
            if (err) {
                return res.status(500).json({ error: 'Compression error' });
            }

            res.set({
                'Content-Type': 'application/gzip',
                'Content-Disposition': 'attachment; filename=subdir_metadata.json.gz',
                'Content-Encoding': 'gzip'
            });
            res.send(compressed);
        });
    });
});

// Root
app.get('/', (req, res) => {
    res.json({
        message: 'SubDir API',
        version: '1.0.0',
        endpoints: {
            health: '/api/health',
            search: '/api/search?q=python',
            subreddit: '/api/subreddits/{name}',
            threads: '/api/subreddits/{name}/threads',
            stats: '/api/stats',
            export: '/api/export/metadata.json',
            export_gz: '/api/export/metadata.json.gz'
        }
    });
});

// CORS preflight
app.options('*', cors());

// Start server
app.listen(PORT, '0.0.0.0', () => {
    console.log(`SubDir API running on http://localhost:${PORT}`);
    console.log(`API docs: http://localhost:${PORT}/api/health`);
});
