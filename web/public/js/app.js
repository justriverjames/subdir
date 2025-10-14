/**
 * Main app initialization
 */

document.addEventListener('DOMContentLoaded', async () => {
    const searchInput = document.getElementById('search-input');
    const searchBtn = document.getElementById('search-btn');

    // Load stats
    loadStats();

    // Search on button click
    searchBtn.addEventListener('click', () => {
        const query = searchInput.value.trim();
        if (query) {
            performSearch(query);
        }
    });

    // Search on Enter key
    searchInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            const query = searchInput.value.trim();
            if (query) {
                performSearch(query);
            }
        }
    });

    // Focus search input
    searchInput.focus();
});

async function loadStats() {
    try {
        const stats = await api.getStats();

        document.getElementById('stat-total').textContent = formatNumber(stats.total_subreddits);
        document.getElementById('stat-threads').textContent = formatNumber(stats.total_threads);
        document.getElementById('stat-active').textContent = formatNumber(stats.active_subreddits);

    } catch (error) {
        console.error('Failed to load stats:', error);
        document.getElementById('stat-total').textContent = '29K+';
        document.getElementById('stat-threads').textContent = '782K+';
        document.getElementById('stat-active').textContent = '28K+';
    }
}
