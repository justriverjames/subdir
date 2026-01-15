'use client';

import { useEffect, useState, useMemo } from 'react';
import Link from 'next/link';

interface MiniStats {
  totalActive: number;
  totalSfw: number;
  totalNsfw: number;
  topLanguages: { language: string; count: number; percentage: number }[];
  subscriberDistribution: {
    tiny: number;
    small: number;
    medium: number;
    large: number;
    mega: number;
  };
  topWords: { text: string; count: number }[];
  combinedReach: { totalSubscribers: number; formattedTotal: string };
  funFacts: {
    oldestSub: { name: string; ageYears: number } | null;
    peakYear: string;
    pollsEnabled: number;
    flairAdoption: number;
  };
}

export default function MiniStats() {
  const [stats, setStats] = useState<MiniStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/stats?view=mini')
      .then(res => res.json())
      .then(data => {
        setStats(data);
        setLoading(false);
      })
      .catch(err => {
        console.error('Mini stats error:', err);
        setLoading(false);
      });
  }, []);

  const funFact = useMemo(() => {
    if (!stats) return null;
    const facts = [
      `Combined reach: ${stats.combinedReach.formattedTotal} subscribers`,
      stats.funFacts.oldestSub ? `Oldest community: r/${stats.funFacts.oldestSub.name} (${stats.funFacts.oldestSub.ageYears} years)` : null,
      `Peak creation year: ${stats.funFacts.peakYear}`,
      `${stats.funFacts.flairAdoption}% of communities have post flairs`,
      `${stats.funFacts.pollsEnabled.toLocaleString()} communities allow polls`,
    ].filter(Boolean) as string[];
    return facts[Math.floor(Math.random() * facts.length)];
  }, [stats]);

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto my-8 px-4">
        <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-purple-500/30 animate-pulse">
          <div className="h-6 bg-white/10 rounded w-48 mb-4"></div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="h-20 bg-white/10 rounded"></div>
            <div className="h-20 bg-white/10 rounded"></div>
            <div className="h-20 bg-white/10 rounded"></div>
            <div className="h-20 bg-white/10 rounded"></div>
          </div>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="max-w-5xl mx-auto my-8 px-4">
      <div className="bg-gradient-to-br from-purple-900/30 to-slate-900/30 backdrop-blur-sm rounded-xl p-6 border border-purple-500/30">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xl sm:text-2xl font-bold text-white">Community Stats</h2>
          {funFact && (
            <span className="hidden md:inline-block text-sm text-purple-300 bg-purple-600/20 px-3 py-1 rounded-full">
              {funFact}
            </span>
          )}
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
          <div className="bg-white/5 rounded-lg p-4">
            <div className="text-2xl sm:text-3xl font-bold text-purple-400">
              {stats.totalActive.toLocaleString()}
            </div>
            <div className="text-xs sm:text-sm text-gray-400 mt-1">Active Communities</div>
          </div>

          <div className="bg-white/5 rounded-lg p-4">
            <div className="text-2xl sm:text-3xl font-bold text-yellow-400">
              {stats.combinedReach.formattedTotal}
            </div>
            <div className="text-xs sm:text-sm text-gray-400 mt-1">Combined Reach</div>
          </div>

          <div className="bg-white/5 rounded-lg p-4">
            <div className="text-2xl sm:text-3xl font-bold text-green-400">
              {Math.round((stats.totalSfw / stats.totalActive) * 100)}%
            </div>
            <div className="text-xs sm:text-sm text-gray-400 mt-1">SFW Communities</div>
          </div>

          <div className="bg-white/5 rounded-lg p-4">
            <div className="text-2xl sm:text-3xl font-bold text-red-400">
              {Math.round((stats.totalNsfw / stats.totalActive) * 100)}%
            </div>
            <div className="text-xs sm:text-sm text-gray-400 mt-1">NSFW Communities</div>
          </div>
        </div>

        {/* Mobile fun fact */}
        {funFact && (
          <div className="md:hidden mb-4 text-sm text-purple-300 bg-purple-600/20 px-3 py-2 rounded-lg text-center">
            {funFact}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
          <div className="bg-white/5 rounded-lg p-4">
            <div className="text-sm font-semibold text-gray-300 mb-2">Top Languages</div>
            <div className="flex flex-wrap gap-2">
              {stats.topLanguages.slice(0, 3).map(lang => (
                <span key={lang.language} className="text-xs px-2 py-1 bg-purple-600/30 text-purple-200 rounded">
                  {lang.language.toUpperCase()} ({lang.percentage.toFixed(1)}%)
                </span>
              ))}
            </div>
          </div>

          <div className="bg-white/5 rounded-lg p-4">
            <div className="text-sm font-semibold text-gray-300 mb-2">Popular Topics</div>
            <div className="flex flex-wrap gap-2">
              {stats.topWords.slice(0, 6).map(word => (
                <span key={word.text} className="text-xs px-2 py-1 bg-slate-700/50 text-gray-300 rounded">
                  {word.text}
                </span>
              ))}
            </div>
          </div>
        </div>

        <Link
          href="/stats"
          className="block text-center py-2 px-4 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors text-sm font-medium"
        >
          View Full Statistics →
        </Link>
      </div>
    </div>
  );
}
