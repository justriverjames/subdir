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
  total_subreddits?: number;
  active_subreddits?: number;
}

export default function Home() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<Subreddit[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState(false);
  const [showNsfw, setShowNsfw] = useState(false);
  const [totalSubs, setTotalSubs] = useState<number | null>(null);
  const [suggestions, setSuggestions] = useState<Subreddit[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [browseMode, setBrowseMode] = useState<'search' | 'browse'>('search');
  const [browseFilter, setBrowseFilter] = useState<'all' | 'sfw' | 'nsfw' | 'random'>('all');

  // Fetch active subreddit count on mount
  useEffect(() => {
    fetch('/api/stats')
      .then(res => res.json())
      .then((data: Stats) => {
        if (data.active_subreddits) {
          setTotalSubs(data.active_subreddits);
        }
      })
      .catch(() => {
        // Keep null on error to show loading state
      });
  }, []);

  // Close autocomplete dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target.closest('form')) {
        setShowSuggestions(false);
      }
    };

    if (showSuggestions) {
      document.addEventListener('click', handleClickOutside);
      return () => document.removeEventListener('click', handleClickOutside);
    }
  }, [showSuggestions]);

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    // Dismiss keyboard on mobile
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }

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

  const handleBrowse = async (filter: 'all' | 'sfw' | 'nsfw' | 'random') => {
    setLoading(true);
    setSearched(true);
    setBrowseMode('browse');
    setBrowseFilter(filter);
    setShowSuggestions(false);

    try {
      const res = await fetch(`/api/browse?mode=${filter}&limit=3000`);
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
      <div className="container mx-auto px-4 py-6 sm:py-12">
        {/* Header */}
        <div className="text-center mb-8 sm:mb-12">
          <div
            className="flex items-center justify-center gap-3 sm:gap-4 mb-3 sm:mb-4 cursor-pointer hover:opacity-80 transition-opacity"
            onClick={() => {
              setSearched(false);
              setBrowseMode('search');
              setResults([]);
              setQuery('');
            }}
          >
            <img
              src="/logo.png"
              alt="SubDir Logo"
              className="w-12 h-12 sm:w-16 sm:h-16 md:w-20 md:h-20"
            />
            <h1 className="text-4xl sm:text-5xl md:text-6xl font-bold text-white">
              Sub<span className="text-purple-400">Dir</span>
            </h1>
          </div>
          <p className="text-base sm:text-lg md:text-xl text-gray-300 mb-2">
            {totalSubs === null
              ? 'A searchable directory of active subreddits'
              : `A searchable directory of ${totalSubs.toLocaleString()}+ active subreddits`
            }
          </p>
          <p className="text-xs sm:text-sm text-gray-400">
            Find communities, discover content, power your apps
          </p>
        </div>

        {/* Browse Tabs */}
        <div className="max-w-3xl mx-auto mb-6 flex gap-2 justify-center flex-wrap">
          <button
            onClick={() => handleBrowse('all')}
            className={`px-4 sm:px-6 py-2 rounded-full transition-all text-sm sm:text-base ${
              browseMode === 'browse' && browseFilter === 'all'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            Top 3000 (All)
          </button>
          <button
            onClick={() => handleBrowse('sfw')}
            className={`px-4 sm:px-6 py-2 rounded-full transition-all text-sm sm:text-base ${
              browseMode === 'browse' && browseFilter === 'sfw'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            Top 3000 (SFW)
          </button>
          <button
            onClick={() => handleBrowse('nsfw')}
            className={`px-4 sm:px-6 py-2 rounded-full transition-all text-sm sm:text-base ${
              browseMode === 'browse' && browseFilter === 'nsfw'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            Top 3000 (NSFW)
          </button>
          <button
            onClick={() => handleBrowse('random')}
            className={`px-4 sm:px-6 py-2 rounded-full transition-all text-sm sm:text-base ${
              browseMode === 'browse' && browseFilter === 'random'
                ? 'bg-purple-600 text-white'
                : 'bg-white/10 text-gray-300 hover:bg-white/20'
            }`}
          >
            Random 3000
          </button>
        </div>

        {/* Search Bar */}
        <div className="max-w-3xl mx-auto mb-6 sm:mb-8">
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
              placeholder="Search subreddits..."
              className="w-full px-4 sm:px-6 py-3 sm:py-4 pr-20 sm:pr-32 rounded-full bg-white/10 border border-purple-500/50 text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent backdrop-blur-sm text-base"
              autoComplete="off"
              autoCorrect="off"
              autoCapitalize="off"
              spellCheck="false"
            />
            <button
              type="submit"
              disabled={loading}
              className="absolute right-2 top-1.5 sm:top-2 px-4 sm:px-6 py-1.5 sm:py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-800 disabled:cursor-not-allowed text-white rounded-full transition-colors text-sm sm:text-base"
            >
              {loading ? '...' : 'Search'}
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
        <div className="max-w-3xl mx-auto mb-8 sm:mb-12">
          <div className="flex gap-2 sm:gap-4 justify-center flex-wrap">
            <a
              href="/api/export/json?format=minimal"
              download="subreddits.json"
              className="px-3 sm:px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg backdrop-blur-sm transition-colors text-xs sm:text-sm"
            >
              📦 <span className="hidden sm:inline">Download Full Database </span>(JSON)
            </a>
            <a
              href="/api/export/csv"
              download="subreddits.csv"
              className="px-3 sm:px-4 py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg backdrop-blur-sm transition-colors text-xs sm:text-sm"
            >
              📊 <span className="hidden sm:inline">Download Full Database </span>(CSV)
            </a>
          </div>
          <p className="text-xs text-gray-500 text-center mt-2">
            <span className="hidden sm:inline">Downloads include all </span>{totalSubs !== null ? `${totalSubs.toLocaleString()}+` : ''} active subreddits
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
                  <div className="flex items-center justify-between mb-3 gap-2">
                    <p className="text-gray-300 text-sm sm:text-base">
                      {browseMode === 'browse' ? (
                        <>
                          {browseFilter === 'random' ? 'Random' : 'Top'} {results.length} <span className="hidden sm:inline">subreddits {browseFilter === 'sfw' ? '(SFW only)' : browseFilter === 'nsfw' ? '(NSFW only)' : browseFilter === 'random' ? '(Random)' : '(All)'}</span>
                        </>
                      ) : (
                        <>Found {results.length}<span className="hidden sm:inline"> subreddits</span></>
                      )}
                    </p>
                    <button
                      onClick={() => {
                        setSearched(false);
                        setBrowseMode('search');
                        setResults([]);
                        setQuery('');
                      }}
                      className="px-3 sm:px-4 py-1.5 sm:py-2 bg-white/10 hover:bg-white/20 text-white rounded-lg backdrop-blur-sm transition-colors text-xs sm:text-sm whitespace-nowrap"
                    >
                      ← <span className="hidden sm:inline">Back to Search</span><span className="sm:hidden">Back</span>
                    </button>
                  </div>

                  {/* Download current filtered list */}
                  {browseMode === 'browse' && (
                    <div className="flex gap-2 items-center flex-wrap">
                      <span className="text-xs sm:text-sm text-gray-400">Download:</span>
                      <a
                        href={`/api/export/json?format=minimal&mode=${browseFilter}&limit=3000`}
                        download={`subreddits-top3000-${browseFilter}.json`}
                        className="px-2 sm:px-3 py-1 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 rounded backdrop-blur-sm transition-colors text-xs sm:text-sm border border-purple-500/30"
                      >
                        📦 JSON
                      </a>
                      <a
                        href={`/api/export/csv?mode=${browseFilter}&limit=3000`}
                        download={`subreddits-top3000-${browseFilter}.csv`}
                        className="px-2 sm:px-3 py-1 bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 rounded backdrop-blur-sm transition-colors text-xs sm:text-sm border border-purple-500/30"
                      >
                        📊 CSV
                      </a>
                    </div>
                  )}
                </div>
                {results.map((sub, index) => (
                  <a
                    key={sub.name}
                    href={`https://reddit.com/r/${sub.name}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block p-4 sm:p-6 bg-white/10 hover:bg-white/15 rounded-lg backdrop-blur-sm border border-white/10 transition-all hover:border-purple-500/50 relative"
                  >
                    {/* Ranking Number */}
                    <div className="absolute left-2 sm:left-3 top-2 sm:top-3">
                      <span className="text-xs sm:text-sm font-medium text-purple-400/40">
                        #{index + 1}
                      </span>
                    </div>

                    <div className="flex items-start gap-3 sm:gap-4 pl-8 sm:pl-10">

                      {/* Icon */}
                      <div className="relative w-12 h-12 sm:w-16 sm:h-16 flex-shrink-0">
                        {sub.icon_url && (
                          <img
                            src={sub.icon_url}
                            alt={`r/${sub.name}`}
                            className="w-12 h-12 sm:w-16 sm:h-16 rounded-full bg-slate-700 absolute inset-0"
                            onError={(e) => {
                              e.currentTarget.style.display = 'none';
                            }}
                          />
                        )}
                        <div
                          className={`w-12 h-12 sm:w-16 sm:h-16 rounded-full flex items-center justify-center text-base sm:text-xl font-bold ${sub.icon_url ? 'absolute inset-0 -z-10' : ''}`}
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
                        <div className="flex items-start justify-between gap-2 mb-2">
                          <div className="flex items-center gap-2 flex-wrap flex-1">
                            <h3 className="text-lg sm:text-xl font-semibold text-white break-all">
                              r/{sub.name}
                            </h3>
                            {sub.over_18 && (
                              <span className="px-2 py-0.5 bg-red-500/20 text-red-300 text-xs rounded border border-red-500/30 whitespace-nowrap">
                                NSFW
                              </span>
                            )}
                          </div>
                          {/* Subscriber Count - Moved to top right on mobile */}
                          <div className="text-right flex-shrink-0">
                            <p className="text-lg sm:text-2xl font-bold text-purple-400 whitespace-nowrap">
                              {(sub.subscribers || 0).toLocaleString()}
                            </p>
                            <p className="text-xs text-gray-400 hidden sm:block">subscribers</p>
                          </div>
                        </div>

                        {/* Tags */}
                        {(sub.category || sub.advertiser_category) && (
                          <div className="flex gap-2 mb-2 flex-wrap">
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
                        )}

                        <p className="text-gray-400 text-sm mb-1 sm:mb-2">{sub.title}</p>
                        <p className="text-gray-300 text-xs sm:text-sm line-clamp-2">
                          {sub.description}
                        </p>
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
          <div className="max-w-4xl mx-auto grid sm:grid-cols-2 gap-4 sm:gap-6 md:gap-8 mt-12 sm:mt-16">
            <div className="p-4 sm:p-6 bg-white/5 rounded-lg backdrop-blur-sm border border-white/10">
              <div className="text-3xl sm:text-4xl mb-3 sm:mb-4">🔍</div>
              <h3 className="text-lg sm:text-xl font-semibold text-white mb-2">
                Fast Search
              </h3>
              <p className="text-gray-400 text-xs sm:text-sm">
                Instantly search through {totalSubs !== null ? `${totalSubs.toLocaleString()}+` : 'thousands of'} active subreddits by name, title, or description
              </p>
            </div>

            <div className="p-4 sm:p-6 bg-white/5 rounded-lg backdrop-blur-sm border border-white/10">
              <div className="text-3xl sm:text-4xl mb-3 sm:mb-4">📥</div>
              <h3 className="text-lg sm:text-xl font-semibold text-white mb-2">
                Export Data
              </h3>
              <p className="text-gray-400 text-xs sm:text-sm">
                Download the complete directory in JSON or CSV format for your projects
              </p>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="text-center mt-12 sm:mt-16 text-gray-400 text-xs sm:text-sm space-y-2 sm:space-y-3 pb-6">
          <p>
            Built for the selfhosted community
          </p>
          <p className="hidden sm:block">
            Data sourced from Reddit and updated regularly
          </p>
          <div className="flex items-center justify-center gap-3 sm:gap-4 flex-wrap">
            <a
              href="https://github.com/justriverjames/subdir"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-gray-400 hover:text-gray-300 transition-colors"
            >
              <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
              <span>GitHub</span>
            </a>
            <span className="text-gray-600">•</span>
            <a
              href="https://github.com/sponsors/justriverjames"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 px-2.5 sm:px-3 py-1 rounded-full bg-pink-500/10 hover:bg-pink-500/20 text-pink-400 hover:text-pink-300 border border-pink-500/30 transition-colors"
            >
              <svg className="w-3.5 h-3.5 sm:w-4 sm:h-4" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/>
              </svg>
              <span>Sponsor</span>
            </a>
          </div>
          <p className="text-xs text-gray-500 pt-2">
            Not affiliated with Reddit, Inc. • Data collected via public Reddit API
          </p>
        </div>
      </div>
    </div>
  );
}
