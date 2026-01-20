# Next Up: Deferred Features & Improvements

## Community Stats (Deferred)

Currently removed from web UI due to performance concerns at scale (130k+ subreddits).

### Issues to Address

**Performance bottlenecks:**
- Text analysis loads all 130k rows into JavaScript memory
- Percentile calculations pull full subscriber list client-side
- N+1 query patterns for prefix matching
- No process-level caching

**Data quality:**
- Stop words list incomplete (missing "game", "news", "community", etc.)
- Bigrams/trigrams don't filter stop words (shows "discord server", etc.)

### Planned Improvements

**Database optimization:**
1. Use SQLite window functions for percentile calculations
2. Single-query CASE statements for prefix pattern matching
3. Background cache for expensive text analysis (24h TTL)
4. Add indexes on `subscribers`, `over_18`, composite status filters

**Migration to PostgreSQL:**
When database exceeds ~200k active subreddits or performance degrades:
- Better concurrent read performance
- More efficient aggregation queries
- Horizontal scaling support if needed

**Text analysis improvements:**
1. Expand stop words list (see `web/lib/word-analyzer.ts`)
2. Filter bigrams/trigrams to skip stop words
3. Consider moving to background job vs lazy cache

### Code References

- Stats API: `web/app/api/stats/route.ts`
- Text analysis: `web/lib/word-analyzer.ts`
- Stats calculator: `web/lib/stats-calculator.ts`
- Indexes migration: Ready to add as `002_performance_indexes.sql`

### When to Re-Enable

After implementing:
1. Database performance indexes
2. Background stats cache
3. SQL-based percentile calculations
4. Expanded stop words + filtered n-grams

Or after migrating to PostgreSQL if scale demands it.
