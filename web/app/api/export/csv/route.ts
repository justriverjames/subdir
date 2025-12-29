import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const categoryParam = searchParams.get('category');
  const modeParam = searchParams.get('mode'); // 'all', 'sfw', 'nsfw'
  const limitParam = searchParams.get('limit');

  try {
    const db = getDb();

    let sql = `
      SELECT
        name, title, description,
        subscribers, over_18, category, language, subreddit_type
      FROM subreddits
      WHERE status = 'active'
    `;

    const params: any[] = [];

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

    // Build CSV
    const headers = ['name', 'title', 'description', 'subscribers', 'nsfw', 'category', 'language', 'type'];
    const csvRows = [headers.join(',')];

    for (const row of rows) {
      const r = row as any;
      const csvRow = [
        escapeCSV(r.name),
        escapeCSV(r.title || ''),
        escapeCSV(r.description || ''),
        r.subscribers || '0',
        r.over_18 ? 'true' : 'false',
        escapeCSV(r.category || ''),
        escapeCSV(r.language || 'en'),
        escapeCSV(r.subreddit_type || 'public'),
      ];
      csvRows.push(csvRow.join(','));
    }

    const csv = csvRows.join('\n');

    return new NextResponse(csv, {
      headers: {
        'Content-Type': 'text/csv',
        'Content-Disposition': 'attachment; filename="subreddits.csv"',
        'Cache-Control': 'public, max-age=3600',
      },
    });
  } catch (error) {
    console.error('CSV export error:', error);
    return NextResponse.json(
      { error: 'Database error' },
      { status: 500 }
    );
  }
}

function escapeCSV(value: string): string {
  if (value.includes(',') || value.includes('"') || value.includes('\n')) {
    return `"${value.replace(/"/g, '""')}"`;
  }
  return value;
}
