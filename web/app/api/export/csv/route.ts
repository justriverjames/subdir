import { NextRequest, NextResponse } from 'next/server';
import { getDb } from '@/lib/db';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const categoryParam = searchParams.get('category');

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

    sql += ` ORDER BY subscribers DESC NULLS LAST`;

    const stmt = db.prepare(sql);
    const rows = stmt.all(...params);

    // Build CSV
    const headers = ['name', 'title', 'description', 'subscribers', 'nsfw', 'category', 'language', 'type'];
    const csvRows = [headers.join(',')];

    for (const row: any of rows) {
      const csvRow = [
        escapeCSV(row.name),
        escapeCSV(row.title || ''),
        escapeCSV(row.description || ''),
        row.subscribers || '0',
        row.over_18 ? 'true' : 'false',
        escapeCSV(row.category || ''),
        escapeCSV(row.language || 'en'),
        escapeCSV(row.subreddit_type || 'public'),
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
