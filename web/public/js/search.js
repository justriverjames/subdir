/**
 * Search functionality
 */

function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
    if (num >= 1000) return (num / 1000).toFixed(1) + 'K';
    return num.toString();
}

function createResultCard(subreddit) {
    const nsfwBadge = subreddit.over_18
        ? `<span class="px-2 py-1 bg-red-100 text-red-800 text-xs font-semibold rounded">NSFW</span>`
        : '';

    const description = subreddit.public_description || subreddit.description || 'No description available';
    const truncatedDesc = description.length > 200
        ? description.substring(0, 200) + '...'
        : description;

    const subscribers = subreddit.subscribers
        ? formatNumber(subreddit.subscribers)
        : 'Unknown';

    return `
        <div class="result-card bg-white rounded-lg shadow-md p-6 fade-in">
            <div class="flex items-start justify-between">
                <div class="flex-1">
                    <div class="flex items-center gap-2 mb-2">
                        <a href="https://reddit.com/r/${subreddit.name}" target="_blank"
                           class="text-xl font-bold text-blue-600 hover:text-blue-800">
                            r/${subreddit.name}
                        </a>
                        ${nsfwBadge}
                    </div>
                    <p class="text-gray-700 mb-3">${escapeHtml(truncatedDesc)}</p>
                    <div class="flex items-center gap-4 text-sm text-gray-600">
                        <span class="flex items-center">
                            <svg class="w-4 h-4 mr-1" fill="currentColor" viewBox="0 0 20 20">
                                <path d="M9 6a3 3 0 11-6 0 3 3 0 016 0zM17 6a3 3 0 11-6 0 3 3 0 016 0zM12.93 17c.046-.327.07-.66.07-1a6.97 6.97 0 00-1.5-4.33A5 5 0 0119 16v1h-6.07zM6 11a5 5 0 015 5v1H1v-1a5 5 0 015-5z"/>
                            </svg>
                            ${subscribers} subscribers
                        </span>
                        ${subreddit.subreddit_type ? `<span class="capitalize">${subreddit.subreddit_type}</span>` : ''}
                    </div>
                </div>
            </div>
        </div>
    `;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

async function performSearch(query) {
    if (!query.trim()) {
        showEmptyState();
        return;
    }

    const resultsContainer = document.getElementById('results-container');
    const loading = document.getElementById('loading');
    const emptyState = document.getElementById('empty-state');
    const resultCount = document.getElementById('result-count');
    const searchTime = document.getElementById('search-time');

    // Show loading
    emptyState.classList.add('hidden');
    resultsContainer.innerHTML = '';
    loading.classList.remove('hidden');

    try {
        const startTime = performance.now();
        const data = await api.search(query, 50);
        const endTime = performance.now();
        const timeMs = Math.round(endTime - startTime);

        // Hide loading
        loading.classList.add('hidden');

        if (data.subreddits.length === 0) {
            showNoResults(query);
            return;
        }

        // Show results
        resultCount.textContent = data.total;
        searchTime.textContent = `(${timeMs}ms)`;
        searchTime.classList.remove('hidden');

        const resultsHTML = data.subreddits
            .map(sub => createResultCard(sub))
            .join('');

        resultsContainer.innerHTML = `
            <div class="grid grid-cols-1 gap-4">
                ${resultsHTML}
            </div>
        `;

    } catch (error) {
        loading.classList.add('hidden');
        showError(error.message);
    }
}

function showEmptyState() {
    document.getElementById('results-container').innerHTML = '';
    document.getElementById('empty-state').classList.remove('hidden');
    document.getElementById('loading').classList.add('hidden');
    document.getElementById('result-count').textContent = '0';
    document.getElementById('search-time').textContent = '';
}

function showNoResults(query) {
    const resultsContainer = document.getElementById('results-container');
    resultsContainer.innerHTML = `
        <div class="text-center py-12">
            <svg class="mx-auto h-16 w-16 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9.172 16.172a4 4 0 015.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <h3 class="mt-4 text-lg font-medium text-gray-900">No results found</h3>
            <p class="mt-2 text-gray-600">No subreddits match "${escapeHtml(query)}"</p>
            <p class="mt-1 text-sm text-gray-500">Try different keywords or check spelling</p>
        </div>
    `;
    document.getElementById('result-count').textContent = '0';
    document.getElementById('search-time').textContent = '';
}

function showError(message) {
    const resultsContainer = document.getElementById('results-container');
    resultsContainer.innerHTML = `
        <div class="bg-red-50 border border-red-200 rounded-lg p-6">
            <div class="flex items-center">
                <svg class="h-6 w-6 text-red-600 mr-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div>
                    <h3 class="text-red-800 font-medium">Search Error</h3>
                    <p class="text-red-700 text-sm mt-1">${escapeHtml(message)}</p>
                </div>
            </div>
        </div>
    `;
}
