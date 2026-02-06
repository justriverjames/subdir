#!/bin/bash
set -e

echo "======================================"
echo "SubDir Archiver - Quick Test Script"
echo "======================================"
echo ""

cd "$(dirname "$0")"

echo "[1/8] Building scanner image..."
docker-compose build scanner

echo ""
echo "[2/8] Starting PostgreSQL..."
docker-compose up -d postgres

echo ""
echo "[3/8] Waiting for PostgreSQL to be healthy..."
sleep 15

echo ""
echo "[4/8] Verifying database connection..."
docker-compose exec postgres psql -U archiver -d reddit_archiver -c "SELECT version();"

echo ""
echo "[5/8] Importing priority CSV (208 subreddits)..."
docker-compose run --rm scanner python main.py import-csv /app/priority_subreddits.csv

echo ""
echo "[6/8] Verifying import..."
docker-compose exec postgres psql -U archiver -d reddit_archiver -c \
  "SELECT COUNT(*) as total, posts_status FROM subreddits GROUP BY posts_status;"

echo ""
echo "[7/8] Running threads mode test (5 subreddits)..."
echo "This will take ~10-15 minutes..."
echo "Press Ctrl+C to cancel, or wait for completion..."
echo ""
docker-compose run --rm scanner python main.py run --limit 5

echo ""
echo "[8/8] Checking results..."
docker-compose exec postgres psql -U archiver -d reddit_archiver -c \
  "SELECT display_name, posts_status, comments_status, total_posts, total_media_urls
   FROM subreddits
   WHERE posts_status='completed'
   ORDER BY subscribers DESC;"

echo ""
echo "======================================"
echo "Test Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Review the output above"
echo "2. Check for any errors"
echo "3. Verify 5 subreddits completed"
echo "4. Verify comments_status='deferred'"
echo ""
echo "To view logs:"
echo "  docker-compose logs -f scanner"
echo ""
echo "To get stats:"
echo "  docker-compose exec postgres psql -U archiver -d reddit_archiver -c \\"
echo "    \"SELECT COUNT(*) FROM posts;\""
echo ""
