import { NextRequest, NextResponse } from 'next/server';
import { getDb, Stats, MiniStats, FullStats } from '@/lib/db';
import {
  calculateBasicStats,
  calculateSubscriberDistribution,
  calculateLanguageStats,
  calculateAgeDistribution,
  calculateContentPermissions,
  calculateSubscriberPercentiles,
  calculateSubredditTypes,
  calculateCombinedReach,
  calculateTopSubreddits,
  calculateCommunityMaturity,
  calculateAgeInsights,
  calculateNamePatterns,
  calculateNsfwByTier,
} from '@/lib/stats-calculator';
import { analyzeText } from '@/lib/word-analyzer';

// Revalidate every 5 minutes (300 seconds) for legacy, 1 hour for new views
export const revalidate = 300;

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const view = searchParams.get('view'); // 'mini' | 'full' | null (legacy)

  try {
    const db = getDb();

    // Legacy stats endpoint (backward compatibility)
    if (!view) {
      const stats: Partial<Stats> = {};

      const totalRow = db.prepare('SELECT COUNT(*) as count FROM subreddits').get() as { count: number };
      stats.total_subreddits = totalRow.count;

      const activeRow = db.prepare("SELECT COUNT(*) as count FROM subreddits WHERE status = 'active'").get() as { count: number };
      stats.active_subreddits = activeRow.count;

      const nsfwRow = db.prepare("SELECT COUNT(*) as count FROM subreddits WHERE over_18 = 1 AND status = 'active'").get() as { count: number };
      stats.nsfw_subreddits = nsfwRow.count;

      const lastUpdatedRow = db.prepare('SELECT MAX(last_updated) as latest FROM subreddits WHERE last_updated IS NOT NULL').get() as { latest: number | null };
      stats.last_updated = lastUpdatedRow.latest ? new Date(lastUpdatedRow.latest * 1000).toISOString() : null;

      const categoryRows = db.prepare(`
        SELECT category, COUNT(*) as count
        FROM subreddits
        WHERE status = 'active' AND category IS NOT NULL
        GROUP BY category
        ORDER BY count DESC
      `).all() as { category: string; count: number }[];
      stats.categories = categoryRows;

      return NextResponse.json(stats, {
        headers: {
          'Cache-Control': 'public, s-maxage=300, stale-while-revalidate=600',
        },
      });
    }

    // Mini stats view
    if (view === 'mini') {
      const basicStats = calculateBasicStats(db);
      const subDistribution = calculateSubscriberDistribution(db);
      const topLanguages = calculateLanguageStats(db, false);
      const wordAnalysis = analyzeText(db);
      const combinedReach = calculateCombinedReach(db);
      const ageInsights = calculateAgeInsights(db);
      const contentPermissions = calculateContentPermissions(db);
      const maturity = calculateCommunityMaturity(db);

      const miniStats: MiniStats = {
        totalActive: basicStats.totalActive,
        totalSfw: basicStats.totalSfw,
        totalNsfw: basicStats.totalNsfw,
        topLanguages,
        subscriberDistribution: subDistribution,
        topWords: wordAnalysis.words.slice(0, 10),
        combinedReach,
        funFacts: {
          oldestSub: ageInsights.oldestSubs[0] ? {
            name: ageInsights.oldestSubs[0].name,
            ageYears: ageInsights.oldestSubs[0].ageYears,
          } : null,
          peakYear: ageInsights.peakCreationYear,
          pollsEnabled: contentPermissions.allowsPolls,
          flairAdoption: Math.round(maturity.flairPercentage),
        },
      };

      return NextResponse.json(miniStats, {
        headers: {
          'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=7200',
        },
      });
    }

    // Full stats view
    if (view === 'full') {
      const basicStats = calculateBasicStats(db);
      const subDistribution = calculateSubscriberDistribution(db);
      const topLanguages = calculateLanguageStats(db, false);
      const allLanguages = calculateLanguageStats(db, true);
      const ageDistribution = calculateAgeDistribution(db);
      const contentPermissions = calculateContentPermissions(db);
      const subscriberPercentiles = calculateSubscriberPercentiles(db);
      const subredditTypes = calculateSubredditTypes(db);
      const wordAnalysis = analyzeText(db);
      const combinedReach = calculateCombinedReach(db);
      const topSubreddits = calculateTopSubreddits(db, 10);
      const communityMaturity = calculateCommunityMaturity(db);
      const ageInsights = calculateAgeInsights(db);
      const namePatterns = calculateNamePatterns(db);
      const nsfwByTier = calculateNsfwByTier(db);

      const fullStats: FullStats = {
        totalActive: basicStats.totalActive,
        totalSfw: basicStats.totalSfw,
        totalNsfw: basicStats.totalNsfw,
        topLanguages,
        subscriberDistribution: subDistribution,
        topWords: wordAnalysis.words.slice(0, 10),
        combinedReach,
        funFacts: {
          oldestSub: ageInsights.oldestSubs[0] ? {
            name: ageInsights.oldestSubs[0].name,
            ageYears: ageInsights.oldestSubs[0].ageYears,
          } : null,
          peakYear: ageInsights.peakCreationYear,
          pollsEnabled: contentPermissions.allowsPolls,
          flairAdoption: Math.round(communityMaturity.flairPercentage),
        },
        allLanguages,
        ageDistribution,
        contentPermissions,
        subscriberPercentiles,
        subredditTypes,
        allBigrams: wordAnalysis.bigrams,
        allTrigrams: wordAnalysis.trigrams,
        topSubreddits,
        communityMaturity,
        ageInsights,
        namePatterns,
        nsfwByTier,
      };

      return NextResponse.json(fullStats, {
        headers: {
          'Cache-Control': 'public, s-maxage=3600, stale-while-revalidate=7200',
        },
      });
    }

    return NextResponse.json({ error: 'Invalid view parameter' }, { status: 400 });
  } catch (error) {
    console.error('Stats error:', error);
    return NextResponse.json(
      { error: 'Database error' },
      { status: 500 }
    );
  }
}
