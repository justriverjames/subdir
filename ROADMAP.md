# SubDir Roadmap

This document outlines the development plan for SubDir - a metadata service for Reddit communities.

---

## Current Status: v1.0+ (February 2026)

### Core Features Completed
- ✅ Scanner CLI for subreddit metadata collection
- ✅ SQLite database (140,000+ active subreddits)
- ✅ Next.js web UI (search, browse, autocomplete)
- ✅ REST API for programmatic access
- ✅ Database schema v4 (icons, colors, categories)
- ✅ Self-hostable deployment
- ✅ Production VPS deployment

### What's Available Now
- Complete subreddit catalog with rich metadata
- Instant search across 140k+ subreddits
- NSFW content filtering
- Browse mode (top 3000 subs)
- JSON/CSV export
- Public instance: https://subdir.justriverjames.com

---

## v1.1: AI Categorization & Enhanced Search (Q1 2026)

### Priority: HIGH

#### AI-Powered Categorization
Use Claude API (Sonnet 4.5) to categorize all 140k subreddits:

**Category Tree:**
```
Technology/
├── Programming/
│   ├── Python
│   ├── JavaScript
│   └── Web Development
├── Hardware/
│   ├── PC Building
│   └── Networking
└── Software/
    ├── Linux
    └── Self-Hosted

Science/
├── Space & Astronomy
├── Physics
└── Biology

Entertainment/
├── Gaming
├── Movies
└── Music

Lifestyle/
├── Food & Cooking
├── Fitness
└── Travel

NSFW/
├── [Multiple subcategories]
└── [Collapsed by default in UI]
```

**Implementation:**
- Batch process subreddits via Claude API
- Multi-label tagging system (tags field)
- Category indexes for fast filtering
- Update database schema with category fields

#### Enhanced Search Features
- **Category Filtering:** Browse by category tree
- **NSFW Filtering:** ALL/SFW/NSFW toggle (already implemented)
- **Advanced Sorting:**
  - By subscribers (desc)
  - By activity
  - By name (alphabetical)
  - By creation date
- **Fuzzy Search:** Typo-tolerant matching

#### API Enhancements
```
GET  /api/categories                    # Category tree
GET  /api/categories/{name}/subreddits  # Filter by category
GET  /api/search?q=...&category=...     # Category filter
```

#### Web UI Improvements
- Category browser sidebar
- Advanced search filters
- Better mobile experience
- Dark mode toggle

**Estimated Time:** 2-3 days

---

## v1.2: Data Enrichment (Q2 2026)

### Priority: MEDIUM

#### Additional Metadata
- **Related Subreddits:** Detect community relationships
- **Growth Trends:** Track subscriber changes over time
- **Activity Metrics:** Estimated activity levels
- **Mod Team Info:** Public moderator lists
- **Content Quality Scores:** Description richness metrics

#### Historical Data
- Periodic metadata refreshes (weekly automation)
- Subscriber growth tracking
- Activity trend analysis
- Subreddit lifecycle tracking

#### Enhanced Database Fields
- Language detection for international communities
- Submission types (text/link/image)
- Community rules availability
- Wiki presence indicators

**Estimated Time:** 1 week

---

## v1.3: Performance & Scalability (Q2 2026)

### Priority: MEDIUM

#### Caching Improvements
- Extend cache TTLs for static data
- Edge caching with Cloudflare
- ETags for conditional requests
- Response compression (gzip/brotli)

#### Query Optimization
- Full-text search indexes (FTS5)
- Optimized autocomplete queries
- Query result pagination
- Rate limiting per-endpoint

#### Database Optimizations
- WAL mode (already implemented)
- Analyze query patterns
- Index optimization
- Periodic VACUUM automation

**Estimated Time:** 3-4 days

---

## v1.4: User Features (Q3 2026)

### Priority: LOW-MEDIUM

#### Optional User Accounts
- Email/password auth
- OAuth (Reddit, GitHub)
- API keys for programmatic access

#### Saved Searches
- Save frequently used searches
- Email alerts for new subreddits matching criteria
- Watchlist for tracking specific subreddits

#### Collections
- User-curated subreddit lists
- Public/private sharing
- Export as CSV/JSON
- Embed widgets for blogs/websites

#### Analytics Dashboard
- Personal discovery history
- Subreddit comparison tools
- Discover similar communities
- Trending subreddit detection

**Estimated Time:** 2 weeks

---

## v2.0: Community Platform (Q4 2026+)

### Priority: FUTURE

#### Community Features
- User reviews/ratings of subreddits
- Comments and discussions about communities
- Community-curated recommendations
- Tag system (user-generated)

#### Advanced Discovery
- Machine learning recommendations
- Similar subreddit detection (beyond basic matching)
- Topic modeling and clustering
- Real-time trending detection

#### API Ecosystem
- Public API with tiered access
- Developer portal
- API documentation (Swagger/ReDoc)
- Client libraries (Python, JavaScript, Go)

#### Moderation Tools
- Report incorrect metadata
- Suggest corrections
- Community-contributed data
- Verification system

**Estimated Time:** 4-6 weeks

---

## Deferred Features

### Community Stats Dashboard

**Status:** Removed from v1.0 due to performance at scale (140k+ subreddits)

**Issues:**
- Text analysis loads all rows into memory
- Client-side percentile calculations
- No process-level caching

**Required before re-enabling:**
1. Database performance indexes
2. SQLite window functions for percentiles
3. Background stats cache (24h TTL)
4. SQL-based aggregations vs client-side

**Code references:**
- `web/app/api/stats/route.ts` - Stats API
- `web/lib/word-analyzer.ts` - Text analysis
- `web/lib/stats-calculator.ts` - Calculations

**Target:** Re-enable in v1.3 after performance optimizations

---

## Infrastructure Roadmap

### Short Term (v1.1-1.2)
- [x] Cloudflare CDN
- [x] SSL/HTTPS
- [ ] Basic monitoring (uptime, response times)
- [ ] Log aggregation
- [ ] Automated database backups

### Medium Term (v1.3-1.4)
- [ ] Horizontal scaling (multiple instances)
- [ ] Load balancer
- [ ] Redis caching layer (optional)
- [ ] Prometheus + Grafana monitoring
- [ ] CI/CD pipeline

### Long Term (v2.0+)
- [ ] Multi-region deployment
- [ ] CDN edge workers
- [ ] High availability setup
- [ ] PostgreSQL migration (optional)
- [ ] Kubernetes deployment (if needed)

---

## Security & Compliance

### Ongoing Priorities
- **Rate Limiting:** Prevent abuse (current: reasonable limits)
- **CORS Policy:** Allow legitimate integrations
- **Data Privacy:** No personal data collection
- **Legal Compliance:** GDPR-friendly (public metadata only)
- **Reddit ToS:** Respect API limits, ethical data collection

### Future Enhancements
- API authentication/authorization
- DDoS protection (Cloudflare baseline active)
- Security audits
- Responsible disclosure policy

---

## Community & Documentation

### Continuous Improvement
- Expand API documentation
- Add integration examples
- Video tutorials
- Blog posts about architecture/design
- Community contributions guide

### Outreach
- r/selfhosted announcement
- r/datahoarder announcement
- r/redditdev announcement
- Integration with other discovery tools

---

## Decision Points

### Questions for Future Sessions

**1. Domain Name**
- Current: subdir.justriverjames.com (custom domain)
- Consider: subdir.io or subdir.dev for branding
- **Current Decision:** Custom domain sufficient for now

**2. Database**
- Current: SQLite with WAL mode (excellent for read-heavy workloads)
- Future: PostgreSQL for multi-writer scenarios
- **Current Decision:** SQLite for v1.x, PostgreSQL optional in v2.0+

**3. User Accounts**
- Current: Fully anonymous/public
- Future: Optional accounts for features
- **Current Decision:** No accounts until v1.4+, fully public for now

**4. Monetization**
- Current: Free forever
- Future: Optional donations if costs scale
- **Current Decision:** Free, donations only if infrastructure costs require it

---

## Success Metrics

### v1.0 Goals (Q4 2025 - Completed)
- [x] Launch public instance
- [x] 140,000+ subreddits cataloged
- [x] Zero downtime deployment

### v1.1 Goals (Q1 2026)
- [ ] Complete AI categorization
- [ ] 500+ unique visitors/week
- [ ] Featured on r/selfhosted or r/datahoarder

### v1.2 Goals (Q2 2026)
- [ ] Enhanced metadata collection
- [ ] 1000+ unique visitors/week
- [ ] Community contributions (PRs, issues)
- [ ] 99.9% uptime

### Long Term Goals (2026+)
- 5000+ weekly users
- Integrations with discovery tools
- Active community contributions
- Self-sustaining infrastructure

---

## Contributing

We welcome contributions in these areas:

**Code:**
- Bug fixes and performance improvements
- New API endpoints
- Web UI enhancements
- Database optimizations

**Data:**
- Subreddit categorization suggestions
- Data quality improvements
- Missing subreddit reports

**Documentation:**
- API usage examples
- Integration guides
- Deployment tutorials
- Troubleshooting tips

See CLAUDE.md for developer workflow guidelines.

---

**Last Updated:** February 2026
**Current Version:** v1.0+
**Next Milestone:** v1.1 (AI Categorization)

**Built for the datahoarder and selfhosted communities.**
