import { NextResponse } from 'next/server';
import { getDb, Stats } from '@/lib/db';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const db = getDb();

    const stats: Partial<Stats> = {};

    // Total subreddits
    const totalRow = db.prepare('SELECT COUNT(*) as count FROM subreddits').get() as { count: number };
    stats.total_subreddits = totalRow.count;

    // Active subreddits
    const activeRow = db.prepare("SELECT COUNT(*) as count FROM subreddits WHERE status = 'active'").get() as { count: number };
    stats.active_subreddits = activeRow.count;

    // NSFW subreddits
    const nsfwRow = db.prepare("SELECT COUNT(*) as count FROM subreddits WHERE over_18 = 1 AND status = 'active'").get() as { count: number };
    stats.nsfw_subreddits = nsfwRow.count;

    // Last updated
    const lastUpdatedRow = db.prepare('SELECT MAX(last_updated) as latest FROM subreddits WHERE last_updated IS NOT NULL').get() as { latest: number | null };
    stats.last_updated = lastUpdatedRow.latest ? new Date(lastUpdatedRow.latest * 1000).toISOString() : null;

    // Category distribution (if categories exist)
    const categoryRows = db.prepare(`
      SELECT category, COUNT(*) as count
      FROM subreddits
      WHERE status = 'active' AND category IS NOT NULL
      GROUP BY category
      ORDER BY count DESC
    `).all() as { category: string; count: number }[];
    stats.categories = categoryRows;

    return NextResponse.json(stats);
  } catch (error) {
    console.error('Stats error:', error);
    return NextResponse.json(
      { error: 'Database error' },
      { status: 500 }
    );
  }
}
