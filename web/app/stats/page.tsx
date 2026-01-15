'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import WordCloud from '@/components/stats/WordCloud';
import SubscriberChart from '@/components/stats/SubscriberChart';
import LanguageChart from '@/components/stats/LanguageChart';
import AgeChart from '@/components/stats/AgeChart';

interface FullStats {
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
  allLanguages: { language: string; count: number; percentage: number }[];
  ageDistribution: { year: string; count: number }[];
  contentPermissions: {
    allowsImages: number;
    allowsVideos: number;
    allowsGalleries: number;
    allowsPolls: number;
  };
  subscriberPercentiles: {
    median: number;
    mean: number;
    p90: number;
    p99: number;
  };
  subredditTypes: { type: string; count: number; percentage: number }[];
  allBigrams: { text: string; count: number }[];
  allTrigrams: { text: string; count: number }[];
  topSubreddits: { name: string; subscribers: number }[];
  communityMaturity: {
    flairEnabled: number;
    flairPercentage: number;
    spoilersEnabled: number;
    spoilersPercentage: number;
    wellFeatured: number;
  };
  ageInsights: {
    oldestSubs: { name: string; created: string; ageYears: number }[];
    newestLargeSubs: { name: string; created: string; subscribers: number }[];
    averageAgeYears: number;
    peakCreationYear: string;
    peakCreationCount: number;
  };
  namePatterns: {
    commonPrefixes: { prefix: string; count: number }[];
    avgNameLength: number;
    longestName: string;
    shortestName: string;
    withNumbers: number;
  };
  nsfwByTier: { tier: string; total: number; nsfw: number; percentage: number }[];
}

export default function StatsPage() {
  const [stats, setStats] = useState<FullStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch('/api/stats?view=full')
      .then(res => res.json())
      .then(data => {
        setStats(data);
        setLoading(false);
      })
      .catch(err => {
        console.error('Full stats error:', err);
        setLoading(false);
      });
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-16 w-16 border-b-2 border-purple-500"></div>
          <p className="mt-4 text-gray-300">Loading statistics...</p>
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
        <div className="text-center text-gray-300">
          <p>Failed to load statistics.</p>
          <Link href="/" className="text-purple-400 hover:text-purple-300 mt-4 inline-block">
            ← Back to Home
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">
      <div className="container mx-auto px-4 py-8">
        {/* Header */}
        <div className="text-center mb-8">
          <Link href="/" className="inline-block mb-4">
            <h1 className="text-4xl sm:text-5xl font-bold text-white hover:opacity-80 transition-opacity">
              Sub<span className="text-purple-400">Dir</span> <span className="text-3xl sm:text-4xl">Stats</span>
            </h1>
          </Link>
          <p className="text-gray-300">
            Comprehensive analytics for {stats.totalActive.toLocaleString()} active communities
          </p>
        </div>

        {/* Overview Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 max-w-5xl mx-auto mb-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-4 border border-purple-500/30">
            <div className="text-3xl font-bold text-purple-400">{stats.totalActive.toLocaleString()}</div>
            <div className="text-sm text-gray-400 mt-1">Active Communities</div>
          </div>
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-4 border border-yellow-500/30">
            <div className="text-3xl font-bold text-yellow-400">{stats.combinedReach.formattedTotal}</div>
            <div className="text-sm text-gray-400 mt-1">Combined Reach</div>
          </div>
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-4 border border-green-500/30">
            <div className="text-3xl font-bold text-green-400">{stats.totalSfw.toLocaleString()}</div>
            <div className="text-sm text-gray-400 mt-1">SFW ({Math.round((stats.totalSfw / stats.totalActive) * 100)}%)</div>
          </div>
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-4 border border-red-500/30">
            <div className="text-3xl font-bold text-red-400">{stats.totalNsfw.toLocaleString()}</div>
            <div className="text-sm text-gray-400 mt-1">NSFW ({Math.round((stats.totalNsfw / stats.totalActive) * 100)}%)</div>
          </div>
        </div>

        {/* Top 10 Largest Subreddits */}
        <div className="max-w-5xl mx-auto mb-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-purple-500/30">
            <h2 className="text-2xl font-bold text-white mb-4">Top 10 Largest Communities</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
              {stats.topSubreddits.map((sub, idx) => (
                <div key={sub.name} className="flex items-center justify-between bg-white/5 rounded-lg p-3">
                  <div className="flex items-center gap-3">
                    <span className="text-purple-400 font-bold w-6">{idx + 1}</span>
                    <a href={`https://reddit.com/r/${sub.name}`} target="_blank" rel="noopener noreferrer" className="text-white hover:text-purple-300">
                      r/{sub.name}
                    </a>
                  </div>
                  <span className="text-gray-400">{sub.subscribers.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Subscriber Distribution */}
        <div className="max-w-5xl mx-auto mb-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-purple-500/30">
            <h2 className="text-2xl font-bold text-white mb-4">Subscriber Distribution</h2>
            <SubscriberChart distribution={stats.subscriberDistribution} />
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2 mt-4 text-xs sm:text-sm">
              <div className="text-center">
                <div className="text-purple-400 font-semibold">{stats.subscriberDistribution.tiny.toLocaleString()}</div>
                <div className="text-gray-400">Tiny (&lt;1k)</div>
              </div>
              <div className="text-center">
                <div className="text-purple-400 font-semibold">{stats.subscriberDistribution.small.toLocaleString()}</div>
                <div className="text-gray-400">Small (1k-10k)</div>
              </div>
              <div className="text-center">
                <div className="text-purple-400 font-semibold">{stats.subscriberDistribution.medium.toLocaleString()}</div>
                <div className="text-gray-400">Medium (10k-100k)</div>
              </div>
              <div className="text-center">
                <div className="text-purple-400 font-semibold">{stats.subscriberDistribution.large.toLocaleString()}</div>
                <div className="text-gray-400">Large (100k-1M)</div>
              </div>
              <div className="text-center">
                <div className="text-purple-400 font-semibold">{stats.subscriberDistribution.mega.toLocaleString()}</div>
                <div className="text-gray-400">Mega (1M+)</div>
              </div>
            </div>
          </div>
        </div>

        {/* Word Cloud */}
        <div className="max-w-5xl mx-auto mb-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-purple-500/30">
            <h2 className="text-2xl font-bold text-white mb-4">Popular Topics</h2>
            <WordCloud words={stats.topWords.slice(0, 100)} />
          </div>
        </div>

        {/* Language Distribution */}
        <div className="max-w-5xl mx-auto mb-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-purple-500/30">
            <h2 className="text-2xl font-bold text-white mb-4">Language Distribution</h2>
            <LanguageChart languages={stats.topLanguages.slice(0, 10)} />
          </div>
        </div>

        {/* Age Distribution */}
        <div className="max-w-5xl mx-auto mb-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-purple-500/30">
            <h2 className="text-2xl font-bold text-white mb-4">Community Age Distribution</h2>
            <AgeChart distribution={stats.ageDistribution} />
          </div>
        </div>

        {/* Common Phrases */}
        <div className="max-w-5xl mx-auto mb-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-purple-500/30">
            <h2 className="text-2xl font-bold text-white mb-4">Common Phrases</h2>
            <div className="mb-4">
              <h3 className="text-lg font-semibold text-gray-300 mb-2">Two-Word Phrases</h3>
              <div className="flex flex-wrap gap-2">
                {stats.allBigrams.slice(0, 20).map((bigram, idx) => (
                  <span key={idx} className="px-3 py-1 bg-purple-600/20 text-purple-200 rounded-lg text-sm">
                    {bigram.text} <span className="text-purple-400">({bigram.count})</span>
                  </span>
                ))}
              </div>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-300 mb-2">Three-Word Phrases</h3>
              <div className="flex flex-wrap gap-2">
                {stats.allTrigrams.slice(0, 15).map((trigram, idx) => (
                  <span key={idx} className="px-3 py-1 bg-slate-700/50 text-gray-300 rounded-lg text-sm">
                    {trigram.text} <span className="text-gray-400">({trigram.count})</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* Community Maturity */}
        <div className="max-w-5xl mx-auto mb-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-purple-500/30">
            <h2 className="text-2xl font-bold text-white mb-4">Community Features</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-purple-400">{Math.round(stats.communityMaturity.flairPercentage)}%</div>
                <div className="text-sm text-gray-400 mt-1">Have Post Flairs</div>
              </div>
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-purple-400">{Math.round(stats.communityMaturity.spoilersPercentage)}%</div>
                <div className="text-sm text-gray-400 mt-1">Enable Spoilers</div>
              </div>
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-purple-400">{Math.round((stats.contentPermissions.allowsPolls / stats.totalActive) * 100)}%</div>
                <div className="text-sm text-gray-400 mt-1">Allow Polls</div>
              </div>
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-purple-400">{Math.round((stats.contentPermissions.allowsGalleries / stats.totalActive) * 100)}%</div>
                <div className="text-sm text-gray-400 mt-1">Allow Galleries</div>
              </div>
            </div>
          </div>
        </div>

        {/* Age Insights */}
        <div className="max-w-5xl mx-auto mb-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-purple-500/30">
            <h2 className="text-2xl font-bold text-white mb-4">Age Insights</h2>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-purple-400">{stats.ageInsights.averageAgeYears} years</div>
                <div className="text-sm text-gray-400 mt-1">Average Community Age</div>
              </div>
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-purple-400">{stats.ageInsights.peakCreationYear}</div>
                <div className="text-sm text-gray-400 mt-1">Peak Creation Year</div>
              </div>
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-purple-400">{stats.ageInsights.peakCreationCount.toLocaleString()}</div>
                <div className="text-sm text-gray-400 mt-1">Created That Year</div>
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <h3 className="text-lg font-semibold text-gray-300 mb-2">Oldest Active Communities</h3>
                <div className="space-y-1">
                  {stats.ageInsights.oldestSubs.slice(0, 5).map((sub) => (
                    <div key={sub.name} className="flex justify-between text-sm">
                      <a href={`https://reddit.com/r/${sub.name}`} target="_blank" rel="noopener noreferrer" className="text-purple-300 hover:text-purple-200">
                        r/{sub.name}
                      </a>
                      <span className="text-gray-400">{sub.ageYears} years</span>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <h3 className="text-lg font-semibold text-gray-300 mb-2">Newest Large Communities (100k+)</h3>
                <div className="space-y-1">
                  {stats.ageInsights.newestLargeSubs.slice(0, 5).map((sub) => (
                    <div key={sub.name} className="flex justify-between text-sm">
                      <a href={`https://reddit.com/r/${sub.name}`} target="_blank" rel="noopener noreferrer" className="text-purple-300 hover:text-purple-200">
                        r/{sub.name}
                      </a>
                      <span className="text-gray-400">{sub.subscribers.toLocaleString()}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Name Patterns */}
        <div className="max-w-5xl mx-auto mb-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-purple-500/30">
            <h2 className="text-2xl font-bold text-white mb-4">Naming Patterns</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-purple-400">{stats.namePatterns.avgNameLength}</div>
                <div className="text-sm text-gray-400 mt-1">Avg Name Length</div>
              </div>
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-purple-400">{stats.namePatterns.withNumbers.toLocaleString()}</div>
                <div className="text-sm text-gray-400 mt-1">Names with Numbers</div>
              </div>
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-lg font-bold text-purple-400 truncate" title={stats.namePatterns.longestName}>r/{stats.namePatterns.longestName.slice(0, 12)}...</div>
                <div className="text-sm text-gray-400 mt-1">Longest Name</div>
              </div>
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-lg font-bold text-purple-400">r/{stats.namePatterns.shortestName}</div>
                <div className="text-sm text-gray-400 mt-1">Shortest Name</div>
              </div>
            </div>
            <div>
              <h3 className="text-lg font-semibold text-gray-300 mb-2">Common Prefixes</h3>
              <div className="flex flex-wrap gap-2">
                {stats.namePatterns.commonPrefixes.map((p) => (
                  <span key={p.prefix} className="px-3 py-1 bg-purple-600/20 text-purple-200 rounded-lg text-sm">
                    {p.prefix}* <span className="text-purple-400">({p.count})</span>
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* NSFW by Tier */}
        <div className="max-w-5xl mx-auto mb-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-purple-500/30">
            <h2 className="text-2xl font-bold text-white mb-4">NSFW Distribution by Size</h2>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
              {stats.nsfwByTier.map((tier) => (
                <div key={tier.tier} className="bg-white/5 rounded-lg p-3 text-center">
                  <div className="text-xl font-bold text-red-400">{tier.percentage.toFixed(1)}%</div>
                  <div className="text-xs text-gray-400 capitalize">{tier.tier}</div>
                  <div className="text-xs text-gray-500">{tier.nsfw}/{tier.total}</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Subscriber Stats */}
        <div className="max-w-5xl mx-auto mb-8">
          <div className="bg-white/5 backdrop-blur-sm rounded-xl p-6 border border-purple-500/30">
            <h2 className="text-2xl font-bold text-white mb-4">Subscriber Statistics</h2>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-purple-400">{stats.subscriberPercentiles.median.toLocaleString()}</div>
                <div className="text-sm text-gray-400 mt-1">Median</div>
              </div>
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-purple-400">{stats.subscriberPercentiles.mean.toLocaleString()}</div>
                <div className="text-sm text-gray-400 mt-1">Mean</div>
              </div>
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-purple-400">{stats.subscriberPercentiles.p90.toLocaleString()}</div>
                <div className="text-sm text-gray-400 mt-1">90th Percentile</div>
              </div>
              <div className="bg-white/5 rounded-lg p-4 text-center">
                <div className="text-2xl font-bold text-purple-400">{stats.subscriberPercentiles.p99.toLocaleString()}</div>
                <div className="text-sm text-gray-400 mt-1">99th Percentile</div>
              </div>
            </div>
          </div>
        </div>

        {/* Back Button */}
        <div className="text-center mb-8">
          <Link
            href="/"
            className="inline-block px-6 py-3 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors font-medium"
          >
            ← Back to Home
          </Link>
        </div>
      </div>
    </div>
  );
}
