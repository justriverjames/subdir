# SubDir Roadmap

This document outlines the development plan for SubDir - a metadata service for Reddit communities.

---

## Current Version: v1.0 (October 2025)

### Core Features Completed
- ✅ Scanner CLI for metadata and thread ID collection
- ✅ SQLite database (29,404 subreddits, 782,533 threads)
- ✅ REST API (FastAPI backend)
- ✅ Web UI (search and browse interface)
- ✅ Docker Compose deployment
- ✅ VPS deployment documentation

### What v1.0 Provides
- Complete subreddit catalog with metadata
- Instant search across 29k+ subreddits
- Thread ID bulk exports
- Self-hostable service
- Public instance: subdir.hammond.im

---

## v1.1: AI Categorization & Enhanced Search (Q4 2025)

### Priority: HIGH

#### AI-Powered Categorization
Use Claude API (Sonnet 4.5) to categorize all 29k subreddits:

**Categories:**
```
Technology/
├── Programming/
│   ├── Python
│   ├── JavaScript
│   ├── Rust
│   └── General
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

NSFW/
├── [34 subcategories]
└── [collapsed by default in UI]
```

**Implementation:**
- Batch process 100 subreddits per API call
- Estimated cost: ~$8 one-time
- Update database with category/subcategory fields
- Add category indexes for fast filtering

#### Enhanced Search Features
- **Fuzzy Search:** Typo-tolerant matching
- **Category Filtering:** Browse by category tree
- **NSFW Filtering:** ALL/SFW/NSFW toggle
- **Advanced Sorting:**
  - By subscribers (desc)
  - By activity
  - By name (alphabetical)
  - By creation date
- **Saved Searches:** For logged-in users (future)

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
- Dark mode

**Estimated Time:** 2-3 days

---

## v1.2: Redditarr Integration (Q4 2025)

### Priority: HIGH

#### Integration with Redditarr
Enable Redditarr to use SubDir for faster subreddit discovery:

**Benefits:**
- Instant search (vs slow Reddit API queries)
- Pre-populated thread IDs (skip 2-3 min pagination)
- Offline subreddit browsing

#### Implementation

**Redditarr Side:**
1. Create `app/subdir_client.py`
   - Bulk metadata download (~5MB, weekly refresh)
   - Local SQLite cache
   - Instant search without API calls

2. Update `/api/subreddits/suggest` endpoint
   - Merge SubDir results + live Reddit API
   - Deduplicate by name

3. Thread ID pre-population
   - When adding subreddit, fetch thread IDs from SubDir
   - Pre-populate posts table with thread IDs
   - Metadata worker fills in details later

4. Settings UI
   - Enable/disable SubDir integration
   - Cache refresh controls
   - Link to SubDir web UI

**SubDir Side:**
- Ensure stable API
- Document integration pattern
- Provide example code

**Estimated Time:** 3-4 days

---

## v1.3: Data Enrichment (Q1 2026)

### Priority: MEDIUM

#### Additional Metadata
- **Related Subreddits:** Detect community relationships
- **Growth Trends:** Track subscriber changes over time
- **Activity Metrics:** Posts per day/week/month
- **Mod Team Info:** Public moderator lists
- **Wiki/Description Quality:** Content richness scores

#### Historical Data
- Periodic re-scans to track changes
- Subscriber growth charts
- Activity trends
- Subreddit lifecycle (created → active → archived)

#### Enhanced Thread Data
- Thread scores (upvotes)
- Comment counts
- Post timestamps
- Flair information (if available)

**Estimated Time:** 1 week

---

## v1.4: Performance & Scalability (Q1 2026)

### Priority: MEDIUM

#### PostgreSQL Migration
**Why:**
- Better concurrency for high-traffic deployments
- Advanced querying capabilities
- Real-time updates without file locking

**Implementation:**
- Create migration script (SQLite → PostgreSQL)
- Update API to support both databases
- Deployment guide for PostgreSQL setup
- Keep SQLite as default for simplicity

#### Caching Layer
- Redis for API response caching
- Edge caching with Cloudflare
- ETags for conditional requests
- Response compression (gzip/brotli)

#### Query Optimization
- Full-text search indexes
- Materialized views for complex queries
- Query result pagination
- Rate limiting per-endpoint

**Estimated Time:** 1 week

---

## v1.5: User Features (Q2 2026)

### Priority: LOW-MEDIUM

#### User Accounts (Optional)
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

#### Advanced Analytics
- Personal dashboard
- Subreddit comparison tools
- Discover similar communities
- Growth predictions

**Estimated Time:** 2 weeks

---

## v2.0: Community Platform (Q3-Q4 2026)

### Priority: FUTURE

#### Community Features
- User reviews/ratings of subreddits
- Comments and discussions
- Subreddit recommendations
- Tag system (user-generated)

#### Advanced Discovery
- Machine learning recommendations
- Similar subreddit detection (beyond basic matching)
- Topic modeling and clustering
- Trending subreddits

#### API Ecosystem
- Public API with tiered access
- Developer portal
- API documentation (Swagger/ReDoc)
- Client libraries (Python, JavaScript, Go)

#### Moderation Tools
- Report incorrect data
- Suggest corrections
- Community-contributed metadata
- Verification system

**Estimated Time:** 4-6 weeks

---

## Infrastructure Roadmap

### Short Term (v1.1-1.2)
- Cloudflare CDN (done)
- SSL/HTTPS (done)
- Basic monitoring (uptime, response times)
- Log aggregation

### Medium Term (v1.3-1.5)
- Database backups (automated)
- Horizontal scaling (multiple API instances)
- Load balancer
- Redis caching layer
- Prometheus + Grafana monitoring

### Long Term (v2.0+)
- Multi-region deployment
- CDN edge workers
- Elasticsearch for advanced search
- Kubernetes deployment
- High availability setup

---

## Security & Compliance

### Ongoing Priorities
- **Rate Limiting:** Prevent abuse (100 req/min per IP)
- **CORS Policy:** Allow legitimate integrations
- **Data Privacy:** No personal data collection
- **Legal Compliance:** GDPR-friendly (public metadata only)
- **Reddit ToS:** Respect API limits, ethical data collection

### Future Enhancements
- API authentication/authorization
- DDoS protection (Cloudflare already provides baseline)
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
- Integration with other archiving tools

---

## Decision Points

### Questions for Future Sessions

**1. Domain Name**
- Keep subdir.hammond.im (free)
- Buy subdir.io (~$29/year)
- Buy subdir.dev (~$12/year)
- **Current Decision:** Start with hammond.im, buy later if popular

**2. Database**
- Keep SQLite (simple, great for read-only)
- Migrate to PostgreSQL (better concurrency)
- **Current Decision:** SQLite for v1.0, PostgreSQL optional in v1.4

**3. User Accounts**
- Fully anonymous/public (current)
- Optional accounts for features
- Required accounts (adds complexity)
- **Current Decision:** No accounts until v1.5, fully public for now

**4. Monetization**
- Free forever (ideal for community project)
- Optional donations/Patreon
- Paid tier for API rate limits
- **Current Decision:** Free, donations only if costs scale

---

## Success Metrics

### v1.0 Goals (October 2025)
- [x] Launch public instance
- [ ] 100+ unique visitors/week
- [ ] 10+ Redditarr integrations
- [ ] Zero downtime

### v1.1 Goals (Q4 2025)
- [ ] Complete AI categorization
- [ ] 500+ unique visitors/week
- [ ] 50+ Redditarr integrations
- [ ] Featured on r/selfhosted

### v1.2 Goals (Q4 2025)
- [ ] Redditarr integration shipped
- [ ] 1000+ unique visitors/week
- [ ] Community contributions (PRs, issues)
- [ ] 99.9% uptime

### Long Term Goals (2026+)
- 5000+ weekly users
- Integrations with multiple archiving tools
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

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

**Last Updated:** October 2025
**Current Version:** v1.0
**Next Milestone:** v1.1 (AI Categorization)

For detailed technical specifications, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
