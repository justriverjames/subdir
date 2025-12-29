import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> }
) {
  const { name: paramName } = await params;
  const name = paramName.toLowerCase();

  try {
    const db = getDb();
    const stmt = db.prepare(`
      SELECT
        name, title, description,
        subscribers, active_users, over_18,
        subreddit_type, created_utc, status, last_updated,
        category, tags, language
      FROM subreddits
      WHERE name = ?
    `);

    const row = stmt.get(name);

    if (!row) {
      return NextResponse.json(
        { error: `Subreddit '${name}' not found` },
        { status: 404 }
      );
    }

    const subreddit = {
      ...row,
      over_18: Boolean((row as any).over_18),
    };

    return NextResponse.json(subreddit);
  } catch (error) {
    console.error('Subreddit fetch error:', error);
    return NextResponse.json(
      { error: 'Database error' },
      { status: 500 }
    );
  }
}
