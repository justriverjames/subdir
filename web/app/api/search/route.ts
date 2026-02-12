import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const query = searchParams.get('q');
  const limitParam = searchParams.get('limit');
  const categoryParam = searchParams.get('category');
  const nsfwParam = searchParams.get('nsfw');

  const limit = Math.min(parseInt(limitParam || '1000'), 10000);

  if (!query || query.trim().length === 0) {
    return NextResponse.json(
      { error: 'Query parameter "q" is required' },
      { status: 400 }
    );
  }

  try {
    const db = getDb();
    const queryLower = query.toLowerCase();
    const queryPattern = `%${queryLower}%`;

    let sql = `
      SELECT
        name, title, description,
        subscribers, active_users, over_18,
        subreddit_type, created_utc, status, last_updated,
        category, tags, language,
        icon_url, primary_color, advertiser_category,
        CASE
          WHEN LOWER(name) = ? THEN 1
          WHEN LOWER(name) LIKE ? THEN 2
          WHEN LOWER(name) LIKE ? THEN 3
          WHEN LOWER(name) LIKE ? THEN 4
          WHEN LOWER(title) LIKE ? THEN 5
          WHEN LOWER(description) LIKE ? THEN 6
          ELSE 7
        END as relevance
      FROM subreddits
      WHERE (
        LOWER(name) LIKE ?
        OR LOWER(title) LIKE ?
        OR LOWER(description) LIKE ?
      )
      AND status = 'active'
    `;

    const params: any[] = [
      queryLower,
      `${queryLower}%`,
      `%${queryLower}`,
      queryPattern,
      queryPattern,
      queryPattern,
      queryPattern,
      queryPattern,
      queryPattern,
    ];

    // Add category filter if provided
    if (categoryParam) {
      sql += ` AND category = ?`;
      params.push(categoryParam);
    }

    // Add NSFW filter if provided
    if (nsfwParam !== null) {
      const includeNsfw = nsfwParam === 'true' || nsfwParam === '1';
      if (!includeNsfw) {
        sql += ` AND over_18 = 0`;
      }
    }

    sql += ` ORDER BY relevance ASC, subscribers DESC NULLS LAST LIMIT ?`;
    params.push(limit);

    const stmt = db.prepare(sql);
    const rows = stmt.all(...params);

    // Remove relevance field and transform data
    const subreddits = rows.map((row: any) => {
      const { relevance, ...rest } = row;
      return {
        ...rest,
        over_18: Boolean(rest.over_18),
      };
    });

    return NextResponse.json({
      subreddits,
      total: subreddits.length,
      limit,
    });
  } catch (error) {
    console.error('Search error:', error);
    return NextResponse.json(
      { error: 'Database error' },
      { status: 500 }
    );
  }
}
