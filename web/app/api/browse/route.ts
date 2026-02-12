import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const limitParam = searchParams.get('limit');
  const modeParam = searchParams.get('mode'); // 'all', 'sfw', 'nsfw', 'random'

  const limit = Math.min(parseInt(limitParam || '1000'), 5000);
  const mode = modeParam || 'all';

  try {
    const db = getDb();

    let sql = `
      SELECT
        name, title, description,
        subscribers, over_18, icon_url, primary_color,
        advertiser_category, category
      FROM subreddits
      WHERE status = 'active'
    `;

    const params: any[] = [];

    // Filter by NSFW mode
    if (mode === 'sfw') {
      sql += ` AND over_18 = 0`;
    } else if (mode === 'nsfw') {
      sql += ` AND over_18 = 1`;
    }

    // Order randomly or by subscribers
    if (mode === 'random') {
      sql += ` ORDER BY RANDOM() LIMIT ?`;
    } else {
      sql += ` ORDER BY subscribers DESC NULLS LAST LIMIT ?`;
    }
    params.push(limit);

    const stmt = db.prepare(sql);
    const rows = stmt.all(...params);

    const subreddits = rows.map((row: any) => ({
      ...row,
      over_18: Boolean(row.over_18),
    }));

    return NextResponse.json({
      subreddits,
      total: subreddits.length,
      mode,
      limit,
    });
  } catch (error) {
    console.error('Browse error:', error);
    return NextResponse.json(
      { error: 'Database error' },
      { status: 500 }
    );
  }
}
