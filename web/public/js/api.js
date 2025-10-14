/**
 * API client for SubDir
 */

// API base URL - use web server's proxy
const API_BASE = '/api';

class SubDirAPI {
    async search(query, limit = 50) {
        const url = `${API_BASE}/search?q=${encodeURIComponent(query)}&limit=${limit}`;
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    }

    async getSubreddit(name) {
        const url = `${API_BASE}/subreddits/${name}`;
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    }

    async getThreads(name) {
        const url = `${API_BASE}/subreddits/${name}/threads`;
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    }

    async getStats() {
        const url = `${API_BASE}/stats`;
        const response = await fetch(url);
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
    }
}

const api = new SubDirAPI();
