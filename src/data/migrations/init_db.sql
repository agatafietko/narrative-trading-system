-- Schema for the narrative trading system SQLite database
-- All tables include known_at for temporal discipline enforcement

-- Market data (supplementary to Parquet; used for quick lookups)
CREATE TABLE IF NOT EXISTS market_data (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument TEXT NOT NULL,
    ticker TEXT NOT NULL,
    date TEXT NOT NULL,            -- YYYY-MM-DD
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    adj_close REAL,
    volume INTEGER,
    known_at TEXT NOT NULL,        -- ISO 8601 datetime
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(ticker, date)
);

-- FRED economic series
CREATE TABLE IF NOT EXISTS fred_series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id TEXT NOT NULL,
    date TEXT NOT NULL,            -- YYYY-MM-DD
    value REAL,
    known_at TEXT NOT NULL,        -- When FRED released this data point
    revision_number INTEGER DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(series_id, date, revision_number)
);

-- News articles
CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT,
    url TEXT,
    published_at TEXT NOT NULL,    -- Article publication timestamp
    known_at TEXT NOT NULL,        -- Same as published_at for news
    content_hash TEXT NOT NULL,    -- SHA-256 of (title + source + date) for dedup
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(content_hash)
);

-- Reddit posts
CREATE TABLE IF NOT EXISTS reddit_posts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id TEXT NOT NULL UNIQUE,
    subreddit TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT,
    score INTEGER,
    num_comments INTEGER,
    created_utc TEXT NOT NULL,     -- Post creation time
    known_at TEXT NOT NULL,        -- Same as created_utc
    created_at TEXT DEFAULT (datetime('now'))
);

-- GDELT events
CREATE TABLE IF NOT EXISTS gdelt_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    themes TEXT,                   -- Comma-separated GDELT themes
    tone REAL,                     -- Average tone score
    num_articles INTEGER,
    locations TEXT,                -- JSON array of locations
    known_at TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Agent signals (structured outputs from gathering agents)
CREATE TABLE IF NOT EXISTS agent_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    signal_type TEXT NOT NULL,     -- macro | technical | narrative | sentiment
    as_of TEXT NOT NULL,           -- Point-in-time this signal was generated for
    confidence REAL,
    payload TEXT NOT NULL,         -- JSON serialized signal data
    model_used TEXT,
    prompt_hash TEXT,              -- SHA-256 of the prompt for reproducibility
    response_hash TEXT,            -- SHA-256 of the raw LLM response
    latency_ms INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Council votes
CREATE TABLE IF NOT EXISTS council_votes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    agent_name TEXT NOT NULL,      -- strategist | contrarian | synthesizer
    round_number INTEGER NOT NULL,
    as_of TEXT NOT NULL,
    overall_conviction REAL,
    views TEXT NOT NULL,           -- JSON array of InstrumentView
    summary TEXT,
    model_used TEXT,
    prompt_hash TEXT,
    response_hash TEXT,
    latency_ms INTEGER,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Trade orders executed
CREATE TABLE IF NOT EXISTS trade_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    as_of TEXT NOT NULL,
    instrument TEXT NOT NULL,
    direction TEXT NOT NULL,       -- buy | sell
    weight_delta REAL,
    dollar_amount REAL,
    cost REAL,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Portfolio state snapshots
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    as_of TEXT NOT NULL,
    nav REAL NOT NULL,
    weights TEXT NOT NULL,         -- JSON: instrument -> weight
    cash_weight REAL,
    total_cost_incurred REAL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now'))
);

-- Backtest evaluator feedback
CREATE TABLE IF NOT EXISTS feedback_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    period_start TEXT NOT NULL,
    period_end TEXT NOT NULL,
    total_return REAL,
    sharpe_ratio REAL,
    max_drawdown REAL,
    agent_scores TEXT,             -- JSON: agent_name -> score
    feedback_notes TEXT,           -- JSON: agent_name -> feedback string
    created_at TEXT DEFAULT (datetime('now'))
);

-- Indexes for point-in-time queries
CREATE INDEX IF NOT EXISTS idx_market_data_known_at ON market_data(known_at);
CREATE INDEX IF NOT EXISTS idx_market_data_ticker_date ON market_data(ticker, date);
CREATE INDEX IF NOT EXISTS idx_fred_known_at ON fred_series(known_at);
CREATE INDEX IF NOT EXISTS idx_fred_series_date ON fred_series(series_id, date);
CREATE INDEX IF NOT EXISTS idx_articles_known_at ON articles(known_at);
CREATE INDEX IF NOT EXISTS idx_reddit_known_at ON reddit_posts(known_at);
CREATE INDEX IF NOT EXISTS idx_gdelt_known_at ON gdelt_events(known_at);
CREATE INDEX IF NOT EXISTS idx_signals_run ON agent_signals(run_id, as_of);
CREATE INDEX IF NOT EXISTS idx_council_run ON council_votes(run_id, as_of);
CREATE INDEX IF NOT EXISTS idx_portfolio_run ON portfolio_snapshots(run_id, as_of);
