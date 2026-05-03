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
                                              Synthesizer (DeepSeek-V3)
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
| `DEEPSEEK_API_KEY` | Synthesizer (DeepSeek-V3) | Yes (for LLM agents) |
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

The workflow lives at `.github/workflows/weekly_run.yml` and has two modes:

#### Automatic (every weekday at 22:00 UTC)
Fires Monday–Friday after US market close. Runs all jobs in sequence:
1. **fetch-data** — pulls latest prices from yfinance and macro data from FRED
2. **run-baselines** — runs all deterministic baselines, uploads `ablation_results.json` as an artifact
3. **run-full-system** — runs the complete multi-agent council (GPT-4o + Claude + Gemini + DeepSeek), stores council votes and portfolio decisions in Supabase

Each daily run creates a new entry in the dashboard's "Select Run" dropdown, building up a history of decisions over time.

#### Manual trigger
Go to **Actions → Daily Backtest Run → Run workflow**. You get a mode dropdown:

| Option | What it runs | LLM API calls? | Cost |
|--------|-------------|----------------|------|
| `baselines_only` | All deterministic baselines in one shot | No | Free |
| `technical_momentum` | RSI/MACD/trend-scoring strategy only | No | Free |
| `sixty_forty` | 60% equities / 40% bonds benchmark only | No | Free |
| `equal_weight` | Equal weight across all 11 instruments only | No | Free |
| `full_system` | Complete multi-agent council — all 4 LLMs debate and produce a portfolio | Yes | ~$0.10–0.50 per run |

> **Tip:** Use `baselines_only` to build up run history cheaply. Use `full_system` when you want council debate data (agent reasoning, conviction scores, trade rationale) to show in the dashboard.

#### Required GitHub Actions secrets
Add these under **Settings → Secrets and variables → Actions**:

| Secret | Used by |
|--------|---------|
| `DATABASE_URL` | All jobs — Supabase connection string |
| `FRED_API_KEY` | fetch-data job |
| `OPENAI_API_KEY` | Full system — Macro Sentinel, Strategist, Evaluator |
| `ANTHROPIC_API_KEY` | Full system — Narrative Analyst, Contrarian |
| `GOOGLE_API_KEY` | Full system — Sentiment Scout (Gemini) |
| `DEEPSEEK_API_KEY` | Full system — Synthesizer (DeepSeek-V3) |
| `NEWSAPI_KEY` | Full system — news article fetcher (optional) |
| `REDDIT_CLIENT_ID` | Full system — Reddit sentiment (optional) |
| `REDDIT_CLIENT_SECRET` | Full system — Reddit sentiment (optional) |

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
