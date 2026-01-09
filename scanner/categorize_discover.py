"""
Category Discovery Script for SubDir

Discovers relevant categories by sending subreddit data to Claude API in chunks.
Outputs a raw list of suggested categories to be reviewed and refined.
"""

import os
import sys
import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Set
import anthropic
from dotenv import load_dotenv


# Estimated tokens per subreddit entry (name + title + description)
AVG_TOKENS_PER_SUBREDDIT = 125

# Claude Sonnet 4.5 context window
MAX_CONTEXT_TOKENS = 200_000

# Reserve tokens for system prompt and response
RESERVED_TOKENS = 10_000

# Effective tokens per chunk
EFFECTIVE_TOKENS_PER_CHUNK = MAX_CONTEXT_TOKENS - RESERVED_TOKENS

# Subreddits per chunk (conservative estimate)
SUBREDDITS_PER_CHUNK = int(EFFECTIVE_TOKENS_PER_CHUNK / AVG_TOKENS_PER_SUBREDDIT)


def load_subreddits_from_db(db_path: str, limit: int = None) -> List[Dict[str, str]]:
    """
    Load active subreddits from database.

    Args:
        db_path: Path to SQLite database
        limit: Optional limit for testing

    Returns:
        List of dicts with name, title, description
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = """
        SELECT name, title, description
        FROM subreddits
        WHERE status = 'active'
        AND description IS NOT NULL
        AND description != ''
        ORDER BY subscribers DESC NULLS LAST
    """

    if limit:
        query += f" LIMIT {limit}"

    cursor.execute(query)
    rows = cursor.fetchall()
    conn.close()

    subreddits = []
    for row in rows:
        subreddits.append({
            'name': row['name'],
            'title': row['title'] or '',
            'description': row['description'] or ''
        })

    return subreddits


def create_discovery_prompt(subreddits: List[Dict[str, str]]) -> str:
    """
    Create prompt for category discovery.

    Args:
        subreddits: List of subreddit data

    Returns:
        Formatted prompt string
    """
    # Build subreddit list
    subreddit_list = []
    for sub in subreddits:
        title = sub['title'][:100] if sub['title'] else ''
        desc = sub['description'][:200] if sub['description'] else ''
        subreddit_list.append(f"r/{sub['name']}: {title} - {desc}")

    prompt = f"""Given the following {len(subreddits)} subreddits with their titles and descriptions, suggest broad categories that would be useful for organizing and filtering them.

Return ONLY a list of category names, one per line. Focus on:
- Broad, useful categories that users would want to filter by
- Categories should be 1-3 words maximum
- No explanations, just the category names
- Categories should be general enough to apply to multiple subreddits

Subreddits:
{chr(10).join(subreddit_list)}

Categories (one per line):"""

    return prompt


def call_claude_api(prompt: str, api_key: str) -> str:
    """
    Call Claude API with the given prompt.

    Args:
        prompt: The prompt to send
        api_key: Anthropic API key

    Returns:
        Response text
    """
    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=8000,
        messages=[
            {"role": "user", "content": prompt}
        ]
    )

    return message.content[0].text


def parse_categories(response: str) -> List[str]:
    """
    Parse category names from response.

    Args:
        response: Claude's response text

    Returns:
        List of category names
    """
    lines = response.strip().split('\n')
    categories = []

    for line in lines:
        line = line.strip()
        # Remove common prefixes
        line = line.removeprefix('-').removeprefix('*').removeprefix('•').strip()

        if line and len(line) <= 50:  # Reasonable category name length
            categories.append(line)

    return categories


def estimate_cost(total_input_tokens: int, total_output_tokens: int) -> float:
    """
    Estimate API cost.

    Args:
        total_input_tokens: Estimated input tokens
        total_output_tokens: Estimated output tokens

    Returns:
        Estimated cost in USD
    """
    # Claude Sonnet 4.5 pricing
    input_cost_per_mtok = 3.00
    output_cost_per_mtok = 15.00

    input_cost = (total_input_tokens / 1_000_000) * input_cost_per_mtok
    output_cost = (total_output_tokens / 1_000_000) * output_cost_per_mtok

    return input_cost + output_cost


def main():
    """Main entry point."""
    print("=" * 80)
    print("SubDir Category Discovery Script")
    print("=" * 80)
    print()

    # Load environment
    load_dotenv()
    api_key = os.getenv('ANTHROPIC_API_KEY')

    if not api_key:
        print("❌ Error: ANTHROPIC_API_KEY not found in environment")
        print("Please add it to your .env file")
        return 1

    # Get database path
    db_path = Path(__file__).parent.parent / 'data' / 'subreddit_scanner.db'

    if not db_path.exists():
        print(f"❌ Error: Database not found at {db_path}")
        return 1

    # Check for test mode
    test_mode = '--test' in sys.argv
    limit = 100 if test_mode else None

    if test_mode:
        print("🧪 TEST MODE: Processing only 100 subreddits")
        print()

    # Load subreddits
    print("📊 Loading subreddits from database...")
    subreddits = load_subreddits_from_db(str(db_path), limit=limit)
    total_subreddits = len(subreddits)
    print(f"   Loaded {total_subreddits:,} active subreddits")
    print()

    # Calculate chunks
    num_chunks = (total_subreddits + SUBREDDITS_PER_CHUNK - 1) // SUBREDDITS_PER_CHUNK

    print(f"📦 Chunk Configuration:")
    print(f"   Subreddits per chunk: {SUBREDDITS_PER_CHUNK:,}")
    print(f"   Total chunks needed: {num_chunks}")
    print()

    # Estimate cost
    estimated_input_tokens = total_subreddits * AVG_TOKENS_PER_SUBREDDIT
    estimated_output_tokens = num_chunks * 500  # ~500 tokens per chunk response
    estimated_cost = estimate_cost(estimated_input_tokens, estimated_output_tokens)

    print(f"💰 Cost Estimate:")
    print(f"   Input tokens: ~{estimated_input_tokens:,}")
    print(f"   Output tokens: ~{estimated_output_tokens:,}")
    print(f"   Estimated cost: ${estimated_cost:.2f}")
    print()

    # Confirm
    confirm = input("Proceed with category discovery? (yes/no): ").lower().strip()
    if confirm not in ('yes', 'y'):
        print("Cancelled.")
        return 0

    print()
    print("=" * 80)
    print("Processing Chunks")
    print("=" * 80)
    print()

    # Process chunks
    all_categories: Set[str] = set()

    for chunk_idx in range(num_chunks):
        start_idx = chunk_idx * SUBREDDITS_PER_CHUNK
        end_idx = min(start_idx + SUBREDDITS_PER_CHUNK, total_subreddits)
        chunk = subreddits[start_idx:end_idx]

        print(f"📦 Chunk {chunk_idx + 1}/{num_chunks} ({len(chunk)} subreddits)")

        # Create prompt
        prompt = create_discovery_prompt(chunk)

        # Call API
        print("   Calling Claude API...")
        try:
            response = call_claude_api(prompt, api_key)

            # Parse categories
            categories = parse_categories(response)
            print(f"   Found {len(categories)} categories")

            # Add to set
            all_categories.update(categories)

            print(f"   ✓ Total unique categories so far: {len(all_categories)}")
            print()

        except Exception as e:
            print(f"   ❌ Error: {e}")
            print(f"   Saving progress and exiting...")
            break

    # Save results
    output_file = Path(__file__).parent / 'categories_raw.txt'

    print("=" * 80)
    print("Saving Results")
    print("=" * 80)
    print()

    sorted_categories = sorted(all_categories)

    with open(output_file, 'w') as f:
        for category in sorted_categories:
            f.write(category + '\n')

    print(f"✓ Saved {len(sorted_categories)} unique categories to: {output_file}")
    print()
    print("Next Steps:")
    print("1. Review and edit categories_raw.txt")
    print("2. Remove duplicates and merge similar categories")
    print("3. Save final list as categories_approved.txt")
    print("4. Run categorize_assign.py to assign categories to subreddits")
    print()

    return 0


if __name__ == '__main__':
    sys.exit(main())
