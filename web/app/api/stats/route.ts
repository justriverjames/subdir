import { NextResponse } from 'next/server';
import Database from 'better-sqlite3';
import path from 'path';

export const dynamic = 'force-dynamic';

export async function GET() {
  try {
    const dbPath = path.join(process.cwd(), '..', 'data', 'subreddit_scanner.db');
    const db = new Database(dbPath, { readonly: true });

    const result = db.prepare(`
      SELECT COUNT(*) as count
      FROM subreddits
      WHERE status = 'active'
    `).get() as { count: number };

    db.close();

    return NextResponse.json({
      active_subreddits: result.count
    });
  } catch (error) {
    console.error('Stats error:', error);
    return NextResponse.json(
      { error: 'Failed to fetch stats' },
      { status: 500 }
    );
  }
}
