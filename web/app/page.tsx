'use client';

import { useState, useEffect } from 'react';

interface Subreddit {
  name: string;
  title: string;
  description: string;
  subscribers: number;
  over_18: boolean;
  category: string | null;
  icon_url: string | null;
  primary_color: string | null;
  advertiser_category: string | null;
}

interface Stats {
  total_subreddits: number;
}

export default function Home() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Subreddit[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [showNsfw, setShowNsfw] = useState(false);
  const [totalSubs, setTotalSubs] = useState<number>(29000); // Fallback
  const [suggestions, setSuggestions] = useState<Subreddit[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [browseMode, setBrowseMode] = useState<'search' | 'browse'>('search');
  const [browseFilter, setBrowseFilter] = useState<'all' | 'sfw' | 'nsfw'>('all');

  // Fetch total subreddit count on mount
  useEffect(() => {
    fetch('/api/stats')
      .then(res => res.json())
      .then((data: Stats) => {
        if (data.total_subreddits) {
          setTotalSubs(data.total_subreddits);
        }
      })
      .catch(() => {
        // Use fallback on error
      });
  }, []);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    setSearched(true);
    setBrowseMode('search');
    setShowSuggestions(false);

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

  const handleAutocomplete = async (value: string) => {
    if (value.trim().length < 2) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }

    try {
      const nsfwParam = showNsfw ? 'true' : 'false';
      const res = await fetch(`/api/autocomplete?q=${encodeURIComponent(value)}&nsfw=${nsfwParam}`);
      const data = await res.json();
      setSuggestions(data.suggestions || []);
      setShowSuggestions(true);
    } catch (error) {
      console.error('Autocomplete error:', error);
      setSuggestions([]);
    }
  };

  const handleBrowse = async (filter: 'all' | 'sfw' | 'nsfw') => {
    setLoading(true);
    setSearched(true);
    setBrowseMode('browse');
    setBrowseFilter(filter);
    setShowSuggestions(false);

    try {
      const res = await fetch(`/api/browse?mode=${filter}&limit=1000`);
      const data = await res.json();
      setResults(data.subreddits || []);
    } catch (error) {
      console.error('Browse error:', error);
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const selectSuggestion = (subName: string) => {
    setQuery(subName);
    setShowSuggestions(false);
    handleSearch({ preventDefault: () => {} } as React.FormEvent);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <div className="container mx-auto px-4 py-12">
        {/* Header */}
        <div className="text-center mb-12">
          <h1
            className="text-6xl font-bold text-white mb-4 cursor-pointer hover:opacity-80 transition-opacity"
            onClick={() => {
              setSearched(false);
              setBrowseMode('search');
              setResults([]);
              setQuery('');
            }}
          >
            Sub<span className="text-purple-400">Dir</span>
          </h1>
          <p className="text-xl text-gray-300 mb-2">
            A searchable directory of {totalSubs.toLocaleString()}+ subreddits
          </p>
          <p className="text-sm text-gray-400">
            Find communities, discover content, power your apps
          </p>
        </div>

        {/* Browse Tabs */}
        <div className="max-w-3xl mx-auto mb-6 flex gap-2 justify-center">
          <button
            onClick={() => handleBrowse('all')}
            className={`px-6 py-2 rounded-full transition-all ${
              browseMode === 'browse' && browseFilter === 'all'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            Top 1000 (All)
          </button>
          <button
            onClick={() => handleBrowse('sfw')}
            className={`px-6 py-2 rounded-full transition-all ${
              browseMode === 'browse' && browseFilter === 'sfw'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            Top 1000 (SFW)
          </button>
          <button
            onClick={() => handleBrowse('nsfw')}
            className={`px-6 py-2 rounded-full transition-all ${
              browseMode === 'browse' && browseFilter === 'nsfw'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            Top 1000 (NSFW)
          </button>
        </div>

        {/* Search Bar */}
        <div className="max-w-3xl mx-auto mb-8">
          <form onSubmit={handleSearch} className="relative">
            <input
              type="text"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                handleAutocomplete(e.target.value);
              }}
              onFocus={() => {
                if (suggestions.length > 0) setShowSuggestions(true);
              }}
              onBlur={() => {
                setTimeout(() => setShowSuggestions(false), 200);
              }}
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

            {/* Autocomplete Dropdown */}
            {showSuggestions && suggestions.length > 0 && (
              <div className="absolute top-full mt-2 w-full bg-slate-800 rounded-lg shadow-xl border border-purple-500/30 overflow-hidden z-50">
                {suggestions.map((sub) => (
                  <button
                    key={sub.name}
                    type="button"
                    onClick={() => selectSuggestion(sub.name)}
                    className="w-full px-4 py-3 flex items-center gap-3 hover:bg-purple-600/20 transition-colors text-left"
                  >
                    <div className="relative w-8 h-8 flex-shrink-0">
                      {sub.icon_url && (
                        <img
                          src={sub.icon_url}
                          alt=""
                          className="w-8 h-8 rounded-full bg-slate-700 absolute inset-0"
                          onError={(e) => {
                            e.currentTarget.style.display = 'none';
                          }}
                        />
                      )}
                      <div className={`w-8 h-8 rounded-full bg-purple-600/30 flex items-center justify-center text-xs text-purple-300 ${sub.icon_url ? 'absolute inset-0 -z-10' : ''}`}>
                        r/
                      </div>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-white font-medium">r/{sub.name}</span>
                        {sub.over_18 && (
                          <span className="text-xs text-red-400">NSFW</span>
                        )}
                      </div>
                      <div className="text-xs text-gray-400 truncate">{sub.title}</div>
                    </div>
                    <div className="text-sm text-purple-400">
                      {(sub.subscribers || 0).toLocaleString()}
                    </div>
                  </button>
                ))}
              </div>
            )}
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
        <div className="max-w-3xl mx-auto mb-12">
          <div className="flex gap-4 justify-center flex-wrap">
            <a
              href="/api/export/json?format=minimal"
              download="subreddits.json"
              className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg backdrop-blur-sm transition-colors"
            >
              📦 Download Full Database (JSON)
            </a>
            <a
              href="/api/export/csv"
              download="subreddits.csv"
              className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg backdrop-blur-sm transition-colors"
            >
              📊 Download Full Database (CSV)
            </a>
          </div>
          <p className="text-xs text-gray-500 text-center mt-2">
            Downloads include all {totalSubs.toLocaleString()}+ subreddits from the database
          </p>
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
                <div className="mb-4">
                  <div className="flex items-center justify-between mb-3">
                    <p className="text-gray-300">
                      {browseMode === 'browse' ? (
                        <>
                          Top {results.length} subreddits {browseFilter === 'sfw' ? '(SFW only)' : browseFilter === 'nsfw' ? '(NSFW only)' : '(All)'}
                        </>
                      ) : (
                        <>Found {results.length} subreddits</>
                      )}
                    </p>
                    <button
                      onClick={() => {
                        setSearched(false);
                        setBrowseMode('search');
                        setResults([]);
                        setQuery('');
                      }}
                      className="px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg backdrop-blur-sm transition-colors text-sm"
                    >
                      ← Back to Search
                    </button>
                  </div>

                  {/* Download current filtered list */}
                  {browseMode === 'browse' && (
                    <div className="flex gap-2 items-center">
                      <span className="text-sm text-gray-400">Download this list:</span>
                      <a
                        href={`/api/export/json?format=minimal&mode=${browseFilter}&limit=1000`}
                        download={`subreddits-top1000-${browseFilter}.json`}
                        className="px-3 py-1 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 rounded backdrop-blur-sm transition-colors text-sm border border-purple-500/30"
                      >
                        📦 JSON
                      </a>
                      <a
                        href={`/api/export/csv?mode=${browseFilter}&limit=1000`}
                        download={`subreddits-top1000-${browseFilter}.csv`}
                        className="px-3 py-1 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 rounded backdrop-blur-sm transition-colors text-sm border border-purple-500/30"
                      >
                        📊 CSV
                      </a>
                    </div>
                  )}
                </div>
                {results.map((sub) => (
                  <a
                    key={sub.name}
                    href={`https://reddit.com/r/${sub.name}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block p-6 bg-white/10 hover:bg-white/15 rounded-lg backdrop-blur-sm border border-white/10 transition-all hover:border-purple-500/50"
                  >
                    <div className="flex items-start gap-4">
                      {/* Icon */}
                      <div className="relative w-16 h-16 flex-shrink-0">
                        {sub.icon_url && (
                          <img
                            src={sub.icon_url}
                            alt={`r/${sub.name}`}
                            className="w-16 h-16 rounded-full bg-slate-700 absolute inset-0"
                            onError={(e) => {
                              e.currentTarget.style.display = 'none';
                            }}
                          />
                        )}
                        <div
                          className={`w-16 h-16 rounded-full flex items-center justify-center text-xl font-bold ${sub.icon_url ? 'absolute inset-0 -z-10' : ''}`}
                          style={{
                            backgroundColor: sub.primary_color || '#7c3aed',
                            color: 'white'
                          }}
                        >
                          r/
                        </div>
                      </div>

                      {/* Content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-3 mb-2 flex-wrap">
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
                          {sub.advertiser_category && (
                            <span className="px-2 py-0.5 bg-blue-500/20 text-blue-300 text-xs rounded border border-blue-500/30">
                              {sub.advertiser_category}
                            </span>
                          )}
                        </div>
                        <p className="text-gray-400 text-sm mb-2">{sub.title}</p>
                        <p className="text-gray-300 text-sm line-clamp-2">
                          {sub.description}
                        </p>
                      </div>

                      {/* Subscriber Count */}
                      <div className="text-right flex-shrink-0">
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
                Instantly search through {totalSubs.toLocaleString()}+ subreddits by name, title, or description
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
        <div className="text-center mt-16 text-gray-400 text-sm space-y-3">
          <p>
            Built for Redditarr and the community
          </p>
          <p>
            Data sourced from Reddit and updated regularly
          </p>
          <p className="flex items-center justify-center gap-2">
            <span>Find this useful?</span>
            <a
              href="https://github.com/sponsors/justriverjames"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-pink-500/10 hover:bg-pink-500/20 text-pink-400 hover:text-pink-300 border border-pink-500/30 transition-colors"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
              </svg>
              <span>Sponsor</span>
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
