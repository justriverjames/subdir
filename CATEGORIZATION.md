# SubDir Categorization System - Planning Notes

## Overview
Multi-category filtering system to allow users to select multiple categories and find matching subreddits. Similar to how content sites organize their libraries.

## Implementation Status
- **Phase 1 Script:** `scanner/categorize_discover.py` - Created, not yet run
- **Phase 2:** Manual category review - Not started
- **Phase 3 Script:** `scanner/categorize_assign.py` - Not created
- **Phase 4:** Database import - Not created
- **Phase 5:** Web UI updates - Not started

## Target Specs
- **Max categories per subreddit:** 5
- **Target total categories:** 50-75
- **Storage:** Existing `tags` field (comma-separated, ordered by priority)
- **API:** Claude Sonnet 4.5 (regular API, not batch)
- **Estimated cost:** ~$37 for 35k subreddits

## NSFW Content Handling - To Be Decided

### The Problem
Claude has content policy restrictions that may cause issues with NSFW subreddits:
1. **Refusals:** May refuse to process chunks with explicit sexual content
2. **Sanitized output:** Might give generic categories like "Adult Content" instead of useful specific ones
3. **Inconsistent handling:** Some adult subreddits categorized, others refused

### Potential Solutions

**Option 1: Separate NSFW Processing (Recommended)**
- Filter NSFW subreddits (`over_18 = 1`) into separate batch
- Process SFW first to establish baseline categories
- For NSFW, use more permissive framing: "content classification for search moderation"
- If Claude refuses, fall back to predefined NSFW categories

**Option 2: Test-First Approach**
- Run `--test` mode with mixed SFW/NSFW sample
- Observe Claude's behavior with adult content
- Adjust approach based on actual results
- May find it handles more than expected with clinical framing

**Option 3: Predefined NSFW Categories**
- Create manual list of appropriate NSFW categories
- Only use Claude for SFW subreddits
- Assign NSFW categories programmatically or through separate process
- Ensures consistent, appropriate categorization

**Option 4: Clinical Framing**
- Frame prompt as "content classification for search engine moderation"
- Keep descriptions minimal and clinical
- Focus on topical categories (genre, style, theme) rather than explicit descriptors
- May work if framed as legitimate content organization task

### Decision Required
Need to test Option 2 first, then decide on fallback strategy.

## Script Files

### Phase 1: Category Discovery
**File:** `scanner/categorize_discover.py`
- Loads active subreddits from database
- Sends in chunks (~1500 per chunk) to Claude API
- Asks for category suggestions only (no assignments)
- Outputs: `scanner/categories_raw.txt`
- Has `--test` flag for testing with 100 subreddits

### Phase 3: Category Assignment
**File:** `scanner/categorize_assign.py` (not yet created)
- Loads approved category list from `categories_approved.txt`
- Sends subreddits in smaller chunks (~500-1000)
- Asks Claude to assign 1-5 categories per subreddit
- Outputs: CSV with `subreddit_name,category1,category2,category3...`

### Phase 4: Database Import
**File:** `scanner/categorize_import.py` (not yet created)
- Reads assignment CSV
- Updates `tags` field in database
- Format: comma-separated, ordered by priority

## Cost Breakdown

### Phase 1: Discovery
- Input: ~4.5M tokens
- Output: ~50K tokens
- Cost: ~$14

### Phase 3: Assignment
- Input: ~5M tokens
- Output: ~500K tokens
- Cost: ~$23

**Total: ~$37**

## Next Steps (When Ready)

1. Test with 100 mixed subreddits: `python categorize_discover.py --test`
2. Review output for NSFW handling
3. Decide on NSFW strategy
4. Run full discovery
5. Manually review and curate categories
6. Create approved list (50-75 categories)
7. Create assignment script
8. Run assignment
9. Import to database
10. Update web UI with category filters

## Database Schema

### Current
```sql
tags TEXT  -- Currently unused, will store comma-separated categories
```

### Alternative (if needed later)
```sql
CREATE TABLE subreddit_categories (
    subreddit_name TEXT NOT NULL,
    category TEXT NOT NULL,
    priority INTEGER NOT NULL,
    PRIMARY KEY (subreddit_name, category)
);
```

## Web UI Updates Needed

When implementing:
1. Add category filter component (multi-select)
2. Update `/api/search` to filter by categories
3. Update `/api/browse` to filter by categories
4. Display assigned categories on subreddit cards
5. Add category browsing page (optional)

## References
- Plan document: `.claude/plans/optimized-riding-kazoo.md`
- Claude API docs: https://platform.claude.com/docs/en/about-claude/pricing
- Discovery script: `scanner/categorize_discover.py`
