'use client';

import { useState } from 'react';

interface Subreddit {
  name: string;
  title: string;
  description: string;
  subscribers: number;
  over_18: boolean;
  category: string | null;
}

export default function Home() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Subreddit[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [showNsfw, setShowNsfw] = useState(false);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setSearched(true);

    try {
      const nsfwParam = showNsfw ? 'true' : 'false';
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=20&nsfw=${nsfwParam}`);
      const data = await res.json();
      setResults(data.subreddits || []);
    } catch (error) {
      console.error('Search error:', error);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <div className="container mx-auto px-4 py-12">
        {/* Header */}
        <div className="text-center mb-12">
          <h1 className="text-6xl font-bold text-white mb-4">
            Sub<span className="text-purple-400">Dir</span>
          </h1>
          <p className="text-xl text-gray-300 mb-2">
            A searchable directory of 29,000+ subreddits
          </p>
          <p className="text-sm text-gray-400">
            Find communities, discover content, power your apps
          </p>
        </div>

        {/* Search Bar */}
        <div className="max-w-3xl mx-auto mb-8">
          <form onSubmit={handleSearch} className="relative">
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search for subreddits... (e.g., python, gaming, cats)"
              className="w-full px-6 py-4 pr-32 rounded-full bg-white/10 border border-purple-500/50 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent backdrop-blur-sm"
            />
            <button
              type="submit"
              disabled={loading}
              className="absolute right-2 top-2 px-6 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-800 disabled:cursor-not-allowed text-white rounded-full transition-colors"
            >
              {loading ? 'Searching...' : 'Search'}
            </button>
          </form>

          {/* NSFW Toggle */}
          <div className="flex justify-center mt-4">
            <label className="flex items-center gap-2 cursor-pointer text-gray-300 hover:text-white transition-colors">
              <input
                type="checkbox"
                checked={showNsfw}
                onChange={(e) => setShowNsfw(e.target.checked)}
                className="w-4 h-4 rounded border-purple-500/50 bg-white/10 text-purple-600 focus:ring-purple-500 focus:ring-offset-0"
              />
              <span className="text-sm">Show NSFW subreddits</span>
            </label>
          </div>
        </div>

        {/* Quick Links */}
        <div className="max-w-3xl mx-auto mb-12 flex gap-4 justify-center flex-wrap">
          <a
            href="/api/export/json?format=minimal"
            download="subreddits.json"
            className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg backdrop-blur-sm transition-colors"
          >
            📦 Download JSON
          </a>
          <a
            href="/api/export/csv"
            download="subreddits.csv"
            className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg backdrop-blur-sm transition-colors"
          >
            📊 Download CSV
          </a>
        </div>

        {/* Results */}
        {searched && (
          <div className="max-w-4xl mx-auto">
            {loading ? (
              <div className="text-center text-gray-300 py-12">
                <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-purple-500"></div>
                <p className="mt-4">Searching...</p>
              </div>
            ) : results.length > 0 ? (
              <div className="space-y-4">
                <p className="text-gray-300 mb-4">
                  Found {results.length} subreddits
                </p>
                {results.map((sub) => (
                  <a
                    key={sub.name}
                    href={`https://reddit.com/r/${sub.name}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block p-6 bg-white/10 hover:bg-white/15 rounded-lg backdrop-blur-sm border border-white/10 transition-all hover:border-purple-500/50"
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-3 mb-2">
                          <h3 className="text-xl font-semibold text-white">
                            r/{sub.name}
                          </h3>
                          {sub.over_18 && (
                            <span className="px-2 py-0.5 bg-red-500/20 text-red-300 text-xs rounded border border-red-500/30">
                              NSFW
                            </span>
                          )}
                          {sub.category && (
                            <span className="px-2 py-0.5 bg-purple-500/20 text-purple-300 text-xs rounded border border-purple-500/30">
                              {sub.category}
                            </span>
                          )}
                        </div>
                        <p className="text-gray-400 text-sm mb-2">{sub.title}</p>
                        <p className="text-gray-300 text-sm line-clamp-2">
                          {sub.description}
                        </p>
                      </div>
                      <div className="ml-4 text-right">
                        <p className="text-2xl font-bold text-purple-400">
                          {(sub.subscribers || 0).toLocaleString()}
                        </p>
                        <p className="text-xs text-gray-400">subscribers</p>
                      </div>
                    </div>
                  </a>
                ))}
              </div>
            ) : (
              <div className="text-center text-gray-300 py-12 bg-white/5 rounded-lg backdrop-blur-sm">
                <p className="text-lg mb-2">No subreddits found</p>
                <p className="text-sm text-gray-400">Try a different search term</p>
              </div>
            )}
          </div>
        )}

        {/* Features Section */}
        {!searched && (
          <div className="max-w-6xl mx-auto grid md:grid-cols-3 gap-8 mt-16">
            <div className="p-6 bg-white/5 rounded-lg backdrop-blur-sm border border-white/10">
              <div className="text-4xl mb-4">🔍</div>
              <h3 className="text-xl font-semibold text-white mb-2">
                Fast Search
              </h3>
              <p className="text-gray-400 text-sm">
                Instantly search through 29,000+ subreddits by name, title, or description
              </p>
            </div>

            <div className="p-6 bg-white/5 rounded-lg backdrop-blur-sm border border-white/10">
              <div className="text-4xl mb-4">🏷️</div>
              <h3 className="text-xl font-semibold text-white mb-2">
                Smart Categories
              </h3>
              <p className="text-gray-400 text-sm">
                Filter by categories to discover communities in topics you love
              </p>
            </div>

            <div className="p-6 bg-white/5 rounded-lg backdrop-blur-sm border border-white/10">
              <div className="text-4xl mb-4">📥</div>
              <h3 className="text-xl font-semibold text-white mb-2">
                Export Data
              </h3>
              <p className="text-gray-400 text-sm">
                Download the complete directory in JSON or CSV format for your projects
              </p>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="text-center mt-16 text-gray-400 text-sm">
          <p>
            Built for Redditarr and the community
          </p>
          <p className="mt-2">
            Data sourced from Reddit and updated regularly
          </p>
        </div>
      </div>
    </div>
  );
}
