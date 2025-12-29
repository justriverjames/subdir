import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const query = searchParams.get('q');
  const nsfwParam = searchParams.get('nsfw');

  if (!query || query.trim().length === 0) {
    return NextResponse.json({ suggestions: [] });
  }

  try {
    const db = getDb();
    const queryLower = query.toLowerCase();
    const queryPattern = `${queryLower}%`;

    let sql = `
      SELECT
        name, title, subscribers, over_18, icon_url
      FROM subreddits
      WHERE LOWER(name) LIKE ?
      AND status = 'active'
    `;

    const params: any[] = [queryPattern];

    // Add NSFW filter if provided
    if (nsfwParam !== null) {
      const includeNsfw = nsfwParam === 'true' || nsfwParam === '1';
      if (!includeNsfw) {
        sql += ` AND over_18 = 0`;
      }
    }

    sql += ` ORDER BY subscribers DESC NULLS LAST LIMIT 10`;

    const stmt = db.prepare(sql);
    const rows = stmt.all(...params);

    const suggestions = rows.map((row: any) => ({
      name: row.name,
      title: row.title,
      subscribers: row.subscribers,
      over_18: Boolean(row.over_18),
      icon_url: row.icon_url,
    }));

    return NextResponse.json({ suggestions });
  } catch (error) {
    console.error('Autocomplete error:', error);
    return NextResponse.json({ suggestions: [] });
  }
}
