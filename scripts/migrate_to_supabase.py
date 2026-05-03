"""Migrate local SQLite data to Supabase via REST API."""
import sqlite3
import sys
import time
from pathlib import Path

import requests

PROJECT_URL = "https://ulacnwfjprvhiofurofw.supabase.co"
ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVsYWNud2ZqcHJ2aGlvZnVyb2Z3Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzc4MTUzMjMsImV4cCI6MjA5MzM5MTMyM30.bharUf6SjD7F8uW_sKllkj7zCWnFCQjdrw7CPo5lXko"

HEADERS = {
    "apikey": ANON_KEY,
    "Authorization": f"Bearer {ANON_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "db" / "trading.db"
BATCH_SIZE = 500


def post_batch(table: str, rows: list[dict]) -> None:
    url = f"{PROJECT_URL}/rest/v1/{table}"
    resp = requests.post(url, json=rows, headers=HEADERS, timeout=60)
    if resp.status_code not in (200, 201):
        print(f"  ERROR {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)


def migrate_table(conn, table: str, columns: list[str], query: str) -> None:
    cur = conn.cursor()
    cur.execute(query)
    rows_raw = cur.fetchall()
    rows = [dict(zip(columns, r)) for r in rows_raw]

    # Replace None with None (already handled by json), strip SQLite-only fields
    total = len(rows)
    print(f"{table}: {total} rows", flush=True)

    for i in range(0, total, BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        post_batch(table, batch)
        pct = min(i + BATCH_SIZE, total)
        print(f"  {pct}/{total}", flush=True)
        time.sleep(0.1)  # be polite to the API

    print(f"  done.", flush=True)


def main():
    conn = sqlite3.connect(DB_PATH)

    migrate_table(
        conn, "market_data",
        ["instrument", "ticker", "date", "open", "high", "low", "close", "adj_close", "volume", "known_at"],
        "SELECT instrument, ticker, date, open, high, low, close, adj_close, volume, known_at FROM market_data ORDER BY date",
    )

    migrate_table(
        conn, "trade_orders",
        ["run_id", "as_of", "instrument", "direction", "weight_delta", "dollar_amount", "cost"],
        "SELECT run_id, as_of, instrument, direction, weight_delta, dollar_amount, cost FROM trade_orders",
    )

    migrate_table(
        conn, "portfolio_snapshots",
        ["run_id", "as_of", "nav", "weights", "cash_weight", "total_cost_incurred"],
        "SELECT run_id, as_of, nav, weights, cash_weight, total_cost_incurred FROM portfolio_snapshots",
    )

    conn.close()
    print("\nMigration complete.")


if __name__ == "__main__":
    main()
