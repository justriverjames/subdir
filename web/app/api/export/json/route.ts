import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const format = searchParams.get('format') || 'full'; // 'full' or 'minimal'
  const categoryParam = searchParams.get('category');
  const modeParam = searchParams.get('mode'); // 'all', 'sfw', 'nsfw'
  const limitParam = searchParams.get('limit');

  try {
    const db = getDb();

    let sql: string;
    const params: any[] = [];

    if (format === 'minimal') {
      // Minimal format (smaller payload)
      sql = `
        SELECT name, title, subscribers, over_18, category, language
        FROM subreddits
        WHERE status = 'active'
      `;
    } else {
      // Full format
      sql = `
        SELECT
          name, title, description,
          subscribers, active_users, over_18,
          subreddit_type, created_utc, status, last_updated,
          category, tags, language
        FROM subreddits
        WHERE status = 'active'
      `;
    }

    // Add category filter if provided
    if (categoryParam) {
      sql += ` AND category = ?`;
      params.push(categoryParam);
    }

    // Add NSFW filter if mode specified
    if (modeParam === 'sfw') {
      sql += ` AND over_18 = 0`;
    } else if (modeParam === 'nsfw') {
      sql += ` AND over_18 = 1`;
    }

    sql += ` ORDER BY subscribers DESC NULLS LAST`;

    // Add limit if specified
    if (limitParam) {
      const limit = Math.min(parseInt(limitParam), 10000);
      sql += ` LIMIT ?`;
      params.push(limit);
    }

    const stmt = db.prepare(sql);
    const rows = stmt.all(...params);

    const subreddits = rows.map((row: any) => ({
      ...row,
      over_18: Boolean(row.over_18),
    }));

    const data = {
      version: '1.0.0',
      format,
      total_subreddits: subreddits.length,
      generated_at: new Date().toISOString(),
      subreddits,
    };

    return NextResponse.json(data, {
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'public, max-age=3600', // Cache for 1 hour
      },
    });
  } catch (error) {
    console.error('Export error:', error);
    return NextResponse.json(
      { error: 'Database error' },
      { status: 500 }
    );
  }
}
