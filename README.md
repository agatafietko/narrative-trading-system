# Narrative-to-Portfolio Multi-Agent Trading System

A multi-agent system that derives trading signals from textual narratives and converts them into portfolio decisions across a macro/cross-asset universe.

## Architecture

```
START
  |
  +---> Macro Sentinel (GPT-4o) --------+
  +---> Market Technician (deterministic)+---> Signal Aggregator
  +---> Narrative Analyst (Claude) ------+          |
  +---> Sentiment Scout (Gemini) --------+          v
                                              Strategist (GPT-4o)
                                                    |
                                                    v
                                              Contrarian (Claude)
                                                    |
                                                    v
                                              Synthesizer (Llama 70B)
                                                /       \
                                      (low conviction)  (consensus)
                                           |                |
                                           v                v
                                      (loop back,     Portfolio Constructor
                                       max 2 rounds)       |
                                                            v
                                                      Order Manager
                                                            |
                                                            v
                                                    Backtest Evaluator (GPT-4o)
                                                            |
                                                           END
```

## Investment Universe

S&P 500 (SPY), Nasdaq 100 (QQQ), Russell 2000 (IWM), US 10Y (TLT), US 2Y (SHY), Gold (GLD), Oil WTI (USO), DXY (UUP), VIX (VIXY), MSCI EM (EEM), Bitcoin (BTC-USD)

## Setup

```bash
# 1. Clone and install
pip install -e ".[dev,notebooks]"

# 2. Configure API keys
cp .env.example .env
# Edit .env with your API keys

# 3. Fetch historical data
python scripts/fetch_historical_data.py --start 2020-01-01

# 4. Run baselines
python scripts/run_backtest.py --strategy sixty_forty
python scripts/run_backtest.py --strategy technical_momentum

# 5. Run full multi-agent backtest
python scripts/run_ablation.py --variants full,minimal,no_narrative

# 6. Run ablation experiments
python scripts/run_ablation.py
```

## Required API Keys

| Key | Agent(s) | Required? |
|-----|----------|-----------|
| `OPENAI_API_KEY` | Macro Sentinel, Strategist, Evaluator | Yes (for LLM agents) |
| `ANTHROPIC_API_KEY` | Narrative Analyst, Contrarian | Yes (for LLM agents) |
| `GOOGLE_API_KEY` | Sentiment Scout | Yes (for LLM agents) |
| `TOGETHER_API_KEY` | Synthesizer (Llama 70B) | Yes (for LLM agents) |
| `FRED_API_KEY` | FRED data fetcher | Yes (free at fred.stlouisfed.org) |
| `NEWSAPI_KEY` | News fetcher | Optional (RSS feeds work without it) |
| `REDDIT_CLIENT_ID` | Reddit fetcher | Optional |
| `REDDIT_CLIENT_SECRET` | Reddit fetcher | Optional |

## Backtest Parameters

- Initial capital: $1,000,000
- Transaction costs: 30 bps round-trip + 5 bps slippage for illiquid instruments
- Rebalance frequency: Weekly (Friday close)
- Evaluation period: 2021-01-01 to 2024-12-31

## Ablation Matrix

| Experiment | What changes | Measures |
|-----------|-------------|----------|
| Full system | — | Headline result |
| No narrative | Remove Narrative Analyst | Value of news data |
| No sentiment | Remove Sentiment Scout | Value of social data |
| Single agent | Strategist only, no council | Value of multi-agent debate |
| No feedback | Disable Backtest Evaluator | Value of feedback loop |
| Homogeneous models | All agents use GPT-4o | Value of model diversity |

## Live Dashboard

The system includes a Streamlit dashboard for visualizing results.

```bash
# Run locally
streamlit run app.py
```

### Deploy to Streamlit Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io) and connect your repo
3. Set the main file path to `app.py`
4. Add your `DATABASE_URL` in Streamlit Cloud **Secrets** (Settings > Secrets):
   ```toml
   DATABASE_URL = "postgresql://postgres:PASSWORD@db.PROJECT.supabase.co:5432/postgres"
   ```

### Supabase Setup (Production Database)

1. Create a free project at [supabase.com](https://supabase.com)
2. Go to Project Settings > Database > Connection string (URI)
3. Run the Postgres migration:
   ```bash
   psql "$DATABASE_URL" -f src/data/migrations/init_db_pg.sql
   ```
4. Set `DATABASE_URL` in your `.env`, GitHub Actions secrets, and Streamlit Cloud secrets

### GitHub Actions (Scheduled Runs)

The repo includes a GitHub Actions workflow (`.github/workflows/weekly_run.yml`) that runs every Friday at 22:00 UTC (after US market close). Add these secrets to your GitHub repo (Settings > Secrets > Actions):

- `DATABASE_URL` — Supabase Postgres connection string
- `FRED_API_KEY` — FRED API key
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`, `TOGETHER_API_KEY` — LLM API keys (for full multi-agent runs)
- `NEWSAPI_KEY`, `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` — Optional data source keys

You can also trigger a run manually from the Actions tab.

## Project Structure

```
config/           — YAML configuration files
src/agents/       — All agent implementations
src/graph/        — LangGraph workflow definition
src/data/         — Data fetchers and processors
src/portfolio/    — Constraints, risk, cost model
src/backtest/     — Engine, metrics, baselines, attribution
src/prompts/      — Externalized prompt templates
src/state/        — State schema and data store
scripts/          — Entry point scripts
tests/            — Test suite
notebooks/        — Analysis notebooks
app.py            — Streamlit dashboard
.github/workflows — GitHub Actions CI/CD
```
