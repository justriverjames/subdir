-- Reddit Archiver Schema
-- PostgreSQL 16+
-- Two-tier processing: tier1 (posts/media), tier2 (comments)

-- Subreddits table: metadata and processing state
CREATE TABLE IF NOT EXISTS subreddits (
    name VARCHAR(255) PRIMARY KEY,
    display_name VARCHAR(255),
    title TEXT,
    public_description TEXT,
    description TEXT,

    -- Metrics
    subscribers INTEGER,
    active_users INTEGER,
    created_utc BIGINT,

    -- Visual/branding
    icon_url TEXT,
    banner_url TEXT,
    primary_color VARCHAR(7),
    key_color VARCHAR(7),

    -- Classification
    over_18 BOOLEAN DEFAULT FALSE,
    subreddit_type VARCHAR(50),
    category VARCHAR(100),
    tags TEXT[],

    -- Processing state
    status VARCHAR(50) DEFAULT 'pending',
    priority INTEGER DEFAULT 2,

    -- Timestamps
    first_seen_at BIGINT,
    last_metadata_update BIGINT,
    last_posts_fetch BIGINT,
    last_comments_fetch BIGINT,

    -- Statistics
    total_posts INTEGER DEFAULT 0,
    total_comments INTEGER DEFAULT 0,
    total_media_urls INTEGER DEFAULT 0,

    -- Configuration
    max_posts INTEGER DEFAULT 2000,
    max_comments_per_post INTEGER DEFAULT 500,
    max_comment_depth INTEGER DEFAULT 5,
    fetch_hot BOOLEAN DEFAULT TRUE,
    fetch_top_all BOOLEAN DEFAULT TRUE,
    archive_comments BOOLEAN DEFAULT TRUE,

    -- Error tracking
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,

    -- Two-tier processing state (posts + media, then comments)
    posts_status VARCHAR(50) DEFAULT 'pending',
    posts_completed_at BIGINT,
    comments_status VARCHAR(50) DEFAULT 'pending',
    comments_completed_at BIGINT,
    posts_pending_comments INTEGER DEFAULT 0,

    -- Additional metadata
    metadata JSONB
);

-- Posts table: deduplicated from top 1000 + hot 1000
CREATE TABLE IF NOT EXISTS posts (
    id VARCHAR(20) PRIMARY KEY,
    subreddit VARCHAR(255) NOT NULL REFERENCES subreddits(name) ON DELETE CASCADE,

    -- Core metadata
    author VARCHAR(255),
    title TEXT NOT NULL,
    selftext TEXT,
    url TEXT,
    domain VARCHAR(255),

    -- Post type and content
    post_type VARCHAR(50) NOT NULL,
    is_self BOOLEAN DEFAULT FALSE,
    is_video BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_utc BIGINT NOT NULL,
    edited_utc BIGINT,
    archived_at BIGINT NOT NULL,

    -- Engagement metrics
    score INTEGER DEFAULT 0,
    upvote_ratio FLOAT,
    num_comments INTEGER DEFAULT 0,
    num_crossposts INTEGER DEFAULT 0,

    -- Flags
    over_18 BOOLEAN DEFAULT FALSE,
    spoiler BOOLEAN DEFAULT FALSE,
    stickied BOOLEAN DEFAULT FALSE,
    locked BOOLEAN DEFAULT FALSE,
    archived BOOLEAN DEFAULT FALSE,

    -- Flair
    link_flair_text TEXT,
    link_flair_css_class TEXT,
    author_flair_text TEXT,

    -- Processing state
    comment_fetch_status VARCHAR(50) DEFAULT 'pending',
    comment_count_archived INTEGER DEFAULT 0,
    media_extracted BOOLEAN DEFAULT FALSE,

    -- Source tracking (deduplication)
    source_listing VARCHAR(20),

    -- Additional metadata
    metadata JSONB
);

-- Comments table: threaded comments with materialized paths
CREATE TABLE IF NOT EXISTS comments (
    id VARCHAR(20) PRIMARY KEY,
    post_id VARCHAR(20) NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    parent_id VARCHAR(20),

    -- Content
    author VARCHAR(255),
    body TEXT,
    body_html TEXT,

    -- Timestamps
    created_utc BIGINT NOT NULL,
    edited_utc BIGINT,
    archived_at BIGINT NOT NULL,

    -- Engagement
    score INTEGER DEFAULT 0,
    controversiality INTEGER DEFAULT 0,
    gilded INTEGER DEFAULT 0,

    -- Threading (materialized path for efficient tree queries)
    depth INTEGER NOT NULL DEFAULT 0,
    path TEXT NOT NULL,

    -- Flags
    stickied BOOLEAN DEFAULT FALSE,
    is_submitter BOOLEAN DEFAULT FALSE,
    score_hidden BOOLEAN DEFAULT FALSE,
    distinguished VARCHAR(50),

    -- Bot detection
    is_bot BOOLEAN DEFAULT FALSE,

    -- Additional metadata
    metadata JSONB
);

-- Media URLs table: extracted from posts
CREATE TABLE IF NOT EXISTS media_urls (
    id BIGSERIAL PRIMARY KEY,
    post_id VARCHAR(20) NOT NULL REFERENCES posts(id) ON DELETE CASCADE,

    -- URL and type
    url TEXT NOT NULL,
    media_type VARCHAR(50) NOT NULL,
    source VARCHAR(50),

    -- Position for galleries
    position INTEGER DEFAULT 0,

    -- Media metadata
    width INTEGER,
    height INTEGER,
    duration INTEGER,

    -- Download tracking (for future use)
    downloaded BOOLEAN DEFAULT FALSE,
    download_path TEXT,
    file_size BIGINT,
    content_hash VARCHAR(64),

    -- Processing state
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,

    extracted_at BIGINT NOT NULL,
    metadata JSONB,

    -- Prevent duplicate media URLs for same post
    UNIQUE(post_id, url, position)
);

-- Processing state: resume capability
CREATE TABLE IF NOT EXISTS processing_state (
    subreddit VARCHAR(255) PRIMARY KEY REFERENCES subreddits(name) ON DELETE CASCADE,

    -- Cursor for pagination
    last_post_cursor VARCHAR(100),

    -- Batch tracking
    posts_fetched_this_run INTEGER DEFAULT 0,
    comments_fetched_this_run INTEGER DEFAULT 0,

    -- Status
    current_phase VARCHAR(50),
    phase_started_at BIGINT,
    phase_progress JSONB,

    -- Resume tracking
    last_processed_post_id VARCHAR(20),
    posts_needing_comments TEXT[],

    updated_at BIGINT
);

-- Scanner state: global settings and rate budget (singleton)
CREATE TABLE IF NOT EXISTS scanner_state (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    active_mode VARCHAR(20) DEFAULT 'both',
    posts_rate_budget FLOAT DEFAULT 0.8,
    comments_rate_budget FLOAT DEFAULT 0.2,
    last_posts_activity BIGINT,
    last_comments_activity BIGINT,
    posts_subs_processed INTEGER DEFAULT 0,
    comments_posts_processed INTEGER DEFAULT 0,
    pause_until BIGINT,
    break_count INTEGER DEFAULT 0,
    last_break_at BIGINT,
    created_at BIGINT DEFAULT EXTRACT(EPOCH FROM NOW())::BIGINT,
    updated_at BIGINT
);

INSERT INTO scanner_state (id) VALUES (1) ON CONFLICT DO NOTHING;

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_subreddits_status ON subreddits(status);
CREATE INDEX IF NOT EXISTS idx_subreddits_priority ON subreddits(priority, status);
CREATE INDEX IF NOT EXISTS idx_subreddits_subscribers ON subreddits(subscribers DESC);
CREATE INDEX IF NOT EXISTS idx_subreddits_posts_status ON subreddits(posts_status);
CREATE INDEX IF NOT EXISTS idx_subreddits_comments_status ON subreddits(comments_status);
CREATE INDEX IF NOT EXISTS idx_subreddits_posts_completed ON subreddits(posts_completed_at) WHERE posts_completed_at IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_posts_subreddit ON posts(subreddit);
CREATE INDEX IF NOT EXISTS idx_posts_created_utc ON posts(created_utc DESC);
CREATE INDEX IF NOT EXISTS idx_posts_score ON posts(score DESC);
CREATE INDEX IF NOT EXISTS idx_posts_comment_status ON posts(comment_fetch_status);
CREATE INDEX IF NOT EXISTS idx_posts_source_listing ON posts(source_listing);

CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_comments_parent_id ON comments(parent_id);
CREATE INDEX IF NOT EXISTS idx_comments_path ON comments(path);
CREATE INDEX IF NOT EXISTS idx_comments_created_utc ON comments(created_utc);
CREATE INDEX IF NOT EXISTS idx_comments_is_bot ON comments(is_bot);

CREATE INDEX IF NOT EXISTS idx_media_urls_post_id ON media_urls(post_id);
CREATE INDEX IF NOT EXISTS idx_media_urls_status ON media_urls(status);
CREATE INDEX IF NOT EXISTS idx_media_urls_media_type ON media_urls(media_type);
CREATE INDEX IF NOT EXISTS idx_media_urls_content_hash ON media_urls(content_hash) WHERE content_hash IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_processing_state_current_phase ON processing_state(current_phase);
