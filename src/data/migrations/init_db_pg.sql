-- PostgreSQL schema for Supabase
-- Equivalent to init_db.sql but with Postgres syntax

CREATE TABLE IF NOT EXISTS market_data (
    id SERIAL PRIMARY KEY,
    instrument TEXT NOT NULL,
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,
    open DOUBLE PRECISION,
    high DOUBLE PRECISION,
    low DOUBLE PRECISION,
    close DOUBLE PRECISION,
    adj_close DOUBLE PRECISION,
    volume BIGINT,
    known_at TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(ticker, date)
);

CREATE TABLE IF NOT EXISTS fred_series (
    id SERIAL PRIMARY KEY,
    series_id TEXT NOT NULL,
    date TEXT NOT NULL,
    value DOUBLE PRECISION,
    known_at TEXT NOT NULL,
    revision_number INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(series_id, date, revision_number)
);

CREATE TABLE IF NOT EXISTS articles (
    id SERIAL PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    url TEXT,
    published_at TEXT NOT NULL,
    known_at TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reddit_posts (
    id SERIAL PRIMARY KEY,
    post_id TEXT NOT NULL UNIQUE,
    subreddit TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    score INTEGER,
    num_comments INTEGER,
    created_utc TEXT NOT NULL,
    known_at TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gdelt_events (
    id SERIAL PRIMARY KEY,
    date TEXT NOT NULL,
    themes TEXT,
    tone DOUBLE PRECISION,
    num_articles INTEGER,
    locations TEXT,
    known_at TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_signals (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    as_of TEXT NOT NULL,
    confidence DOUBLE PRECISION,
    payload TEXT NOT NULL,
    model_used TEXT,
    prompt_hash TEXT,
    response_hash TEXT,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS council_votes (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    round_number INTEGER NOT NULL,
    as_of TEXT NOT NULL,
    overall_conviction DOUBLE PRECISION,
    views TEXT NOT NULL,
    summary TEXT,
    model_used TEXT,
    prompt_hash TEXT,
    response_hash TEXT,
    latency_ms INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS trade_orders (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    as_of TEXT NOT NULL,
    instrument TEXT NOT NULL,
    direction TEXT NOT NULL,
    weight_delta DOUBLE PRECISION,
    dollar_amount DOUBLE PRECISION,
    cost DOUBLE PRECISION,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    as_of TEXT NOT NULL,
    nav DOUBLE PRECISION NOT NULL,
    weights TEXT NOT NULL,
    cash_weight DOUBLE PRECISION,
    total_cost_incurred DOUBLE PRECISION DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS feedback_log (
    id SERIAL PRIMARY KEY,
    run_id TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    total_return DOUBLE PRECISION,
    sharpe_ratio DOUBLE PRECISION,
    max_drawdown DOUBLE PRECISION,
    agent_scores TEXT,
    feedback_notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_market_data_known_at ON market_data(known_at);
CREATE INDEX IF NOT EXISTS idx_market_data_ticker_date ON market_data(ticker, date);
CREATE INDEX IF NOT EXISTS idx_fred_known_at ON fred_series(known_at);
CREATE INDEX IF NOT EXISTS idx_articles_known_at ON articles(known_at);
CREATE INDEX IF NOT EXISTS idx_reddit_known_at ON reddit_posts(known_at);
CREATE INDEX IF NOT EXISTS idx_signals_run ON agent_signals(run_id, as_of);
CREATE INDEX IF NOT EXISTS idx_council_run ON council_votes(run_id, as_of);
CREATE INDEX IF NOT EXISTS idx_portfolio_run ON portfolio_snapshots(run_id, as_of);
