"""
Database migration: v3 → v4
Adds visual and categorization helper fields.

Changes:
- Add icon_url (community_icon from Reddit)
- Add primary_color (hex color for branding)
- Add advertiser_category (Reddit's category for bootstrap)
- Add submission_type (what content types allowed)
- Add allow_images (boolean)
- Add allow_videos (boolean)
"""

import sqlite3
import sys
from pathlib import Path

# Support command line argument for DB path
DB_PATH = sys.argv[1] if len(sys.argv) > 1 else '../data/subreddit_scanner.db'

def migrate():
    """Migrate database from v3 to v4."""

    db_path = Path(DB_PATH)
    if not db_path.exists():
        print(f"❌ Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check current version
    cursor.execute("SELECT version FROM schema_version")
    current_version = cursor.fetchone()[0]

    if current_version != 3:
        print(f"❌ Expected schema version 3, found {current_version}")
        print("   This migration only works on v3 databases")
        conn.close()
        sys.exit(1)

    print("="*80)
    print("Database Migration: v3 → v4")
    print("="*80)
    print(f"\nDatabase: {DB_PATH}")
    print(f"Current version: {current_version}")

    # Get current stats
    cursor.execute("SELECT COUNT(*) FROM subreddits")
    total_subs = cursor.fetchone()[0]
    print(f"Total subreddits: {total_subs:,}")

    try:
        print("\n📝 Adding new columns...")

        # Add visual fields
        cursor.execute("ALTER TABLE subreddits ADD COLUMN icon_url TEXT")
        print("  ✓ Added icon_url")

        cursor.execute("ALTER TABLE subreddits ADD COLUMN primary_color TEXT")
        print("  ✓ Added primary_color")

        # Add categorization helper fields
        cursor.execute("ALTER TABLE subreddits ADD COLUMN advertiser_category TEXT")
        print("  ✓ Added advertiser_category")

        cursor.execute("ALTER TABLE subreddits ADD COLUMN submission_type TEXT")
        print("  ✓ Added submission_type")

        cursor.execute("ALTER TABLE subreddits ADD COLUMN allow_images BOOLEAN DEFAULT 1")
        print("  ✓ Added allow_images")

        cursor.execute("ALTER TABLE subreddits ADD COLUMN allow_videos BOOLEAN DEFAULT 1")
        print("  ✓ Added allow_videos")

        # Update schema version
        cursor.execute("UPDATE schema_version SET version = 4")
        print("\n✓ Updated schema version to 4")

        conn.commit()

        # Verify
        cursor.execute("SELECT version FROM schema_version")
        new_version = cursor.fetchone()[0]

        print("\n" + "="*80)
        print("✅ Migration Complete!")
        print("="*80)
        print(f"Schema version: {current_version} → {new_version}")
        print(f"Total subreddits: {total_subs:,}")
        print("\nNew fields added:")
        print("  - icon_url (for subreddit icons)")
        print("  - primary_color (for brand colors)")
        print("  - advertiser_category (Reddit's category)")
        print("  - submission_type (content type)")
        print("  - allow_images (media flag)")
        print("  - allow_videos (media flag)")
        print("\n💡 Next step: Run scanner with --metadata to populate new fields")
        print("="*80)

    except Exception as e:
        print(f"\n❌ Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == '__main__':
    migrate()
