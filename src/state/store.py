"""DataStore — point-in-time data access layer.

Supports both SQLite (local dev) and PostgreSQL (Supabase production).
Backend is selected via DATABASE_URL env var:
  - Not set or "sqlite": uses local SQLite at data/db/trading.db
  - "postgresql://...": uses Postgres

This is the ONLY way agents access historical data during backtesting.
All queries filter by known_at <= as_of to prevent look-ahead bias.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from src.utils.logging import get_logger

logger = get_logger("store")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_DIR = PROJECT_ROOT / "data" / "db"
MIGRATIONS_DIR = PROJECT_ROOT / "src" / "data" / "migrations"


def _get_database_url() -> str:
    """Get DATABASE_URL from env vars or Streamlit secrets."""
    url = os.getenv("DATABASE_URL", "")
    if url:
        return url
    # Fall back to Streamlit secrets (for Streamlit Cloud deployment)
    try:
        import streamlit as st
        return st.secrets.get("DATABASE_URL", "")
    except Exception:
        return ""


def _detect_backend() -> str:
    """Detect database backend from DATABASE_URL."""
    url = _get_database_url()
    if url.startswith("postgresql://") or url.startswith("postgres://"):
        return "postgres"
    return "sqlite"


class DataStore:
    """Point-in-time data access layer.

    All data queries enforce known_at <= as_of to prevent look-ahead bias.
    This is enforced at the architecture level, not by convention.
    """

    def __init__(self, db_path: str | Path | None = None):
        self.backend = _detect_backend()

        if self.backend == "postgres":
            self._pg_url = _get_database_url()
            # Use %s placeholders
            self._ph = "%s"
            logger.info("Using PostgreSQL backend")
        else:
            if db_path is None:
                DB_DIR.mkdir(parents=True, exist_ok=True)
                db_path = DB_DIR / "trading.db"
            self.db_path = Path(db_path)
            # Use ? placeholders
            self._ph = "?"
            logger.info(f"Using SQLite backend: {self.db_path}")

        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        if self.backend == "postgres":
            pg_migration = MIGRATIONS_DIR / "init_db_pg.sql"
            if pg_migration.exists():
                with self._connect() as conn:
                    cur = conn.cursor()
                    cur.execute(pg_migration.read_text())
                    conn.commit()
        else:
            migration_file = MIGRATIONS_DIR / "init_db.sql"
            if migration_file.exists():
                with self._connect() as conn:
                    conn.executescript(migration_file.read_text())

    @contextmanager
    def _connect(self):
        """Create a database connection (context manager)."""
        if self.backend == "postgres":
            import psycopg2
            import psycopg2.extras
            conn = psycopg2.connect(self._pg_url)
            try:
                yield conn
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(str(self.db_path))
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            try:
                yield conn
            finally:
                conn.close()

    def _execute(self, conn, query: str, params: tuple | list = ()) -> Any:
        """Execute a query, handling backend differences."""
        if self.backend == "postgres":
            cur = conn.cursor()
            cur.execute(query, params)
            return cur
        else:
            return conn.execute(query, params)

    def _fetchall_dicts(self, conn, query: str, params: tuple | list = ()) -> list[dict]:
        """Execute and fetch all as list of dicts."""
        if self.backend == "postgres":
            import psycopg2.extras
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(query, params)
            return [dict(row) for row in cur.fetchall()]
        else:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def _q(self, query: str) -> str:
        """Convert a query with ? placeholders to the current backend's format."""
        if self.backend == "postgres":
            return query.replace("?", "%s")
        return query

    def _upsert_keyword(self) -> str:
        """Return the correct INSERT-or-ignore syntax."""
        if self.backend == "postgres":
            return "INSERT INTO"
        return "INSERT OR IGNORE INTO"

    def _conflict_clause(self, columns: str) -> str:
        """Return ON CONFLICT clause for Postgres, empty for SQLite."""
        if self.backend == "postgres":
            return f" ON CONFLICT ({columns}) DO NOTHING"
        return ""

    # ------------------------------------------------------------------
    # Point-in-time query methods (the core of temporal discipline)
    # ------------------------------------------------------------------

    def get_market_data_as_of(
        self,
        as_of: datetime,
        ticker: str | None = None,
        lookback_days: int = 252,
    ) -> pd.DataFrame:
        """Get market data available as of the given timestamp."""
        query = self._q("""
            SELECT instrument, ticker, date, open, high, low, close,
                   adj_close, volume, known_at
            FROM market_data
            WHERE known_at <= ?
        """)
        params: list[Any] = [as_of.isoformat()]

        if ticker:
            query += self._q(" AND ticker = ?")
            params.append(ticker)

        query += self._q(" ORDER BY date DESC LIMIT ?")
        params.append(lookback_days * 15 if not ticker else lookback_days)

        with self._connect() as conn:
            df = pd.read_sql_query(query, conn, params=params)

        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")

        return df

    def get_fred_data_as_of(
        self,
        as_of: datetime,
        series_id: str | None = None,
    ) -> pd.DataFrame:
        """Get FRED economic data available as of the given timestamp."""
        query = self._q("""
            SELECT series_id, date, value, known_at, revision_number
            FROM fred_series
            WHERE known_at <= ?
        """)
        params: list[Any] = [as_of.isoformat()]

        if series_id:
            query += self._q(" AND series_id = ?")
            params.append(series_id)

        query += " ORDER BY date DESC"

        with self._connect() as conn:
            df = pd.read_sql_query(query, conn, params=params)

        if not df.empty:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("revision_number").drop_duplicates(
                subset=["series_id", "date"], keep="last"
            )
            df = df.sort_values("date")

        return df

    def get_articles_as_of(
        self, as_of: datetime, lookback_days: int = 7,
    ) -> list[dict]:
        """Get news articles available as of the given timestamp."""
        cutoff = datetime(
            as_of.year, as_of.month, as_of.day
        ) - pd.Timedelta(days=lookback_days)

        query = self._q("""
            SELECT source, title, content, url, published_at, known_at
            FROM articles
            WHERE known_at <= ? AND known_at >= ?
            ORDER BY published_at DESC
        """)
        with self._connect() as conn:
            return self._fetchall_dicts(
                conn, query, (as_of.isoformat(), cutoff.isoformat())
            )

    def get_reddit_posts_as_of(
        self, as_of: datetime, lookback_days: int = 3,
    ) -> list[dict]:
        """Get Reddit posts available as of the given timestamp."""
        cutoff = datetime(
            as_of.year, as_of.month, as_of.day
        ) - pd.Timedelta(days=lookback_days)

        query = self._q("""
            SELECT subreddit, title, body, score, num_comments, created_utc, known_at
            FROM reddit_posts
            WHERE known_at <= ? AND known_at >= ?
            ORDER BY score DESC
        """)
        with self._connect() as conn:
            return self._fetchall_dicts(
                conn, query, (as_of.isoformat(), cutoff.isoformat())
            )

    def get_gdelt_data_as_of(
        self, as_of: datetime, lookback_days: int = 7,
    ) -> pd.DataFrame:
        """Get GDELT event data available as of the given timestamp."""
        cutoff = datetime(
            as_of.year, as_of.month, as_of.day
        ) - pd.Timedelta(days=lookback_days)

        query = self._q("""
            SELECT date, themes, tone, num_articles, known_at
            FROM gdelt_events
            WHERE known_at <= ? AND known_at >= ?
            ORDER BY date DESC
        """)
        with self._connect() as conn:
            df = pd.read_sql_query(
                query, conn, params=(as_of.isoformat(), cutoff.isoformat())
            )
        return df

    # ------------------------------------------------------------------
    # Signal and vote storage
    # ------------------------------------------------------------------

    def store_signal(self, run_id: str, signal: dict) -> None:
        query = self._q("""
            INSERT INTO agent_signals
                (run_id, agent_name, signal_type, as_of, confidence, payload,
                 model_used, prompt_hash, response_hash, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """)
        with self._connect() as conn:
            self._execute(conn, query, (
                run_id, signal["agent_name"], signal["signal_type"],
                signal["as_of"], signal.get("confidence"),
                json.dumps(signal.get("payload", {})),
                signal.get("model_used"), signal.get("prompt_hash"),
                signal.get("response_hash"), signal.get("latency_ms"),
            ))
            conn.commit()

    def store_council_vote(self, run_id: str, vote: dict, round_number: int) -> None:
        query = self._q("""
            INSERT INTO council_votes
                (run_id, agent_name, round_number, as_of, overall_conviction,
                 views, summary, model_used, prompt_hash, response_hash, latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """)
        with self._connect() as conn:
            self._execute(conn, query, (
                run_id, vote["agent_name"], round_number, vote["as_of"],
                vote.get("overall_conviction"), json.dumps(vote.get("views", [])),
                vote.get("summary"), vote.get("model_used"),
                vote.get("prompt_hash"), vote.get("response_hash"),
                vote.get("latency_ms"),
            ))
            conn.commit()

    def store_trade_orders(self, run_id: str, as_of: str, orders: list[dict]) -> None:
        query = self._q("""
            INSERT INTO trade_orders
                (run_id, as_of, instrument, direction, weight_delta, dollar_amount, cost)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """)
        with self._connect() as conn:
            for order in orders:
                self._execute(conn, query, (
                    run_id, as_of, order["instrument"], order["direction"],
                    order["weight_delta"], order["dollar_amount"], order["cost"],
                ))
            conn.commit()

    def store_portfolio_snapshot(
        self, run_id: str, as_of: str, nav: float,
        weights: dict[str, float], cash_weight: float, total_cost: float,
    ) -> None:
        query = self._q("""
            INSERT INTO portfolio_snapshots
                (run_id, as_of, nav, weights, cash_weight, total_cost_incurred)
            VALUES (?, ?, ?, ?, ?, ?)
        """)
        with self._connect() as conn:
            self._execute(conn, query, (
                run_id, as_of, nav, json.dumps(weights), cash_weight, total_cost,
            ))
            conn.commit()

    def store_feedback(self, run_id: str, report: dict) -> None:
        query = self._q("""
            INSERT INTO feedback_log
                (run_id, period_start, period_end, total_return,
                 sharpe_ratio, max_drawdown, agent_scores, feedback_notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """)
        with self._connect() as conn:
            self._execute(conn, query, (
                run_id, report["period_start"], report["period_end"],
                report.get("total_return"), report.get("sharpe_ratio"),
                report.get("max_drawdown"),
                json.dumps(report.get("agent_scores", {})),
                json.dumps(report.get("feedback_notes", {})),
            ))
            conn.commit()

    # ------------------------------------------------------------------
    # Data ingestion helpers
    # ------------------------------------------------------------------

    def insert_market_data(self, records: list[dict]) -> int:
        if self.backend == "postgres":
            query = """
                INSERT INTO market_data
                    (instrument, ticker, date, open, high, low, close,
                     adj_close, volume, known_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ticker, date) DO NOTHING
            """
        else:
            query = """
                INSERT OR IGNORE INTO market_data
                    (instrument, ticker, date, open, high, low, close,
                     adj_close, volume, known_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        inserted = 0
        with self._connect() as conn:
            for rec in records:
                try:
                    self._execute(conn, query, (
                        rec["instrument"], rec["ticker"], rec["date"],
                        rec.get("open"), rec.get("high"), rec.get("low"),
                        rec.get("close"), rec.get("adj_close"),
                        rec.get("volume"), rec["known_at"],
                    ))
                    inserted += 1
                except Exception:
                    pass
            conn.commit()
        return inserted

    def insert_fred_data(self, records: list[dict]) -> int:
        if self.backend == "postgres":
            query = """
                INSERT INTO fred_series (series_id, date, value, known_at, revision_number)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (series_id, date, revision_number) DO NOTHING
            """
        else:
            query = """
                INSERT OR IGNORE INTO fred_series
                    (series_id, date, value, known_at, revision_number)
                VALUES (?, ?, ?, ?, ?)
            """
        inserted = 0
        with self._connect() as conn:
            for rec in records:
                try:
                    self._execute(conn, query, (
                        rec["series_id"], rec["date"], rec["value"],
                        rec["known_at"], rec.get("revision_number", 0),
                    ))
                    inserted += 1
                except Exception:
                    pass
            conn.commit()
        return inserted

    def insert_articles(self, records: list[dict]) -> int:
        if self.backend == "postgres":
            query = """
                INSERT INTO articles
                    (source, title, content, url, published_at, known_at, content_hash)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (content_hash) DO NOTHING
            """
        else:
            query = """
                INSERT OR IGNORE INTO articles
                    (source, title, content, url, published_at, known_at, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """
        inserted = 0
        with self._connect() as conn:
            for rec in records:
                try:
                    self._execute(conn, query, (
                        rec["source"], rec["title"], rec.get("content"),
                        rec.get("url"), rec["published_at"],
                        rec["known_at"], rec["content_hash"],
                    ))
                    inserted += 1
                except Exception:
                    pass
            conn.commit()
        return inserted

    def insert_reddit_posts(self, records: list[dict]) -> int:
        if self.backend == "postgres":
            query = """
                INSERT INTO reddit_posts
                    (post_id, subreddit, title, body, score, num_comments, created_utc, known_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (post_id) DO NOTHING
            """
        else:
            query = """
                INSERT OR IGNORE INTO reddit_posts
                    (post_id, subreddit, title, body, score, num_comments, created_utc, known_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """
        inserted = 0
        with self._connect() as conn:
            for rec in records:
                try:
                    self._execute(conn, query, (
                        rec["post_id"], rec["subreddit"], rec["title"],
                        rec.get("body"), rec.get("score"),
                        rec.get("num_comments"), rec["created_utc"],
                        rec["known_at"],
                    ))
                    inserted += 1
                except Exception:
                    pass
            conn.commit()
        return inserted

    # ------------------------------------------------------------------
    # Query helpers for feedback/evaluation and dashboard
    # ------------------------------------------------------------------

    def get_portfolio_history(self, run_id: str | None = None) -> pd.DataFrame:
        """Get portfolio history. If run_id is None, get the latest run."""
        if run_id:
            query = self._q("""
                SELECT run_id, as_of, nav, weights, cash_weight, total_cost_incurred
                FROM portfolio_snapshots WHERE run_id = ? ORDER BY as_of
            """)
            params: tuple = (run_id,)
        else:
            query = """
                SELECT run_id, as_of, nav, weights, cash_weight, total_cost_incurred
                FROM portfolio_snapshots ORDER BY as_of DESC LIMIT 500
            """
            params = ()

        with self._connect() as conn:
            df = pd.read_sql_query(self._q(query) if params else query, conn,
                                   params=params if params else None)
        if not df.empty:
            df["as_of"] = pd.to_datetime(df["as_of"])
        return df

    def get_all_run_ids(self) -> list[str]:
        """Get all distinct run IDs."""
        query = "SELECT DISTINCT run_id FROM portfolio_snapshots ORDER BY run_id DESC"
        with self._connect() as conn:
            rows = self._fetchall_dicts(conn, query)
        return [r["run_id"] for r in rows]

    def get_council_votes_for_run(self, run_id: str) -> list[dict]:
        """Get all council votes for a run (for dashboard debate view)."""
        query = self._q("""
            SELECT agent_name, round_number, as_of, overall_conviction,
                   views, summary, model_used
            FROM council_votes WHERE run_id = ?
            ORDER BY as_of, round_number, agent_name
        """)
        with self._connect() as conn:
            return self._fetchall_dicts(conn, query, (run_id,))

    def get_trade_orders_for_run(self, run_id: str) -> pd.DataFrame:
        """Get all trade orders for a run."""
        query = self._q("""
            SELECT as_of, instrument, direction, weight_delta, dollar_amount, cost
            FROM trade_orders WHERE run_id = ? ORDER BY as_of
        """)
        with self._connect() as conn:
            return pd.read_sql_query(query, conn, params=(run_id,))

    def get_recent_feedback(self, agent_name: str, last_n: int = 10) -> list[dict]:
        """Get recent feedback scores for an agent."""
        query = self._q("""
            SELECT period_end, agent_scores, feedback_notes
            FROM feedback_log ORDER BY period_end DESC LIMIT ?
        """)
        with self._connect() as conn:
            rows = self._fetchall_dicts(conn, query, (last_n,))

        results = []
        for row in rows:
            scores = json.loads(row["agent_scores"]) if isinstance(row["agent_scores"], str) else row["agent_scores"]
            notes = json.loads(row["feedback_notes"]) if isinstance(row["feedback_notes"], str) else row["feedback_notes"]
            if agent_name in scores:
                results.append({
                    "period_end": row["period_end"],
                    "score": scores[agent_name],
                    "note": notes.get(agent_name, ""),
                })
        return results
