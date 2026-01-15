#!/bin/bash
# Quick test script for running archiver locally with Docker Desktop

set -e

echo "========================================"
echo "Reddit Archiver - Local Test"
echo "========================================"
echo ""

# Check if .env exists
if [ ! -f ../config/.env ]; then
    echo "❌ config/.env not found!"
    echo "   Copy config/.env.example to config/.env and add your Reddit credentials"
    exit 1
fi

echo "✓ Found config/.env"
echo ""

# Load .env for display
source ../config/.env

echo "Configuration:"
echo "  Reddit Username: $REDDIT_USERNAME"
echo "  Min Subscribers: ${MIN_SUBSCRIBERS:-5000}"
echo "  Batch Size: ${BATCH_SIZE:-10}"
echo "  Rate Limit: ${REQUESTS_PER_MINUTE:-60} QPM"
echo ""

# Start services
echo "Starting PostgreSQL..."
docker-compose up -d postgres

echo "Waiting for PostgreSQL to be ready..."
sleep 5

# Run scanner
echo ""
echo "Starting scanner..."
echo "========================================"
docker-compose up scanner

# Show logs
echo ""
echo "========================================"
echo "To view logs:"
echo "  docker logs -f subdir-archiver-scanner"
echo ""
echo "To stop:"
echo "  docker-compose down"
echo ""
echo "To check database:"
echo "  docker exec -it subdir-archiver-db psql -U archiver -d reddit_archiver"
