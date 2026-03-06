# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**quant-trader** is a quantitative trading system with two main modes:

1. **MCP Server** - Provides LLM-driven strategy review via `strategy_review` and `strategy_iterate` tools
2. **Automated Trading** - Daily automated execution via scheduler (daemon mode) for Hong Kong stocks (2800.HK, 0700.HK, 9988.HK)

## Running Commands

### Install Dependencies
```bash
# Requires Python 3.10+
pip install uv
uv venv --python 3.12 .venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

### Code Quality
```bash
# Lint
ruff check src/

# Type check
mypy src/

# Format
ruff format src/
```

### Run Tests
```bash
pytest tests/ -v
# Single test
pytest tests/test_reviewer.py -v
# Skip slow tests
pytest tests/ -m "not slow"
```

### Run the System

**Immediate execution (paper trading):**
```bash
python main.py --run-now
```

**Daemon mode (scheduled daily):**
```bash
python main.py --daemon
```

**MCP Server mode:**
```bash
python -m quant_trader.server
```

### Environment Variables
```bash
export MINIMAX_API_KEY="your-minimax-key"    # Required for LLM
export TWELVE_DATA_API_KEY="your-key"        # Optional, data source
```

### Configuration Files
```bash
# Copy example configs
cp config/policy.example.yaml config/policy.yaml

# Edit with your settings (contains sensitive data, gitignored)
vim config/policy.yaml
```

## Architecture

The system has three interconnected components:

```
┌─────────────────────────────────────────────────────┐
│  MCP Server (server.py)                            │
│  - strategy_review: single risk check              │
│  - strategy_iterate: auto-iterate strategy         │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│  DecisionGraph (decision_graph.py)                 │
│  6-node flow: SpecPM → Backtest → Bull → Bear →    │
│              RiskGate → PM → PMDecision            │
└─────────────────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│  Orchestrator + Scheduler                          │
│  - scheduler.py: APScheduler daily trigger        │
│  - orchestrator.py: coordinates broker, data, risk │
└─────────────────────────────────────────────────────┘
```

### Key Modules

| Module | File | Purpose |
|--------|------|---------|
| BacktestEngine | `backtest/backtest_engine.py` | Data fetching, backtest execution, metrics |
| DecisionGraph | `decision_graph.py` | 6-node LLM decision flow |
| Risk Gate | `risk/reviewer.py` | Hard rule checks (GO/NO_GO/REVISE) |
| LLM Client | `llm.py` | MiniMax API wrapper |
| Orchestrator | `orchestrator.py` | Daily trading coordination |
| Scheduler | `scheduler.py` | APScheduler for daily execution |
| Broker | `broker/` | Longbridge, paper trading support |
| Data | `data/` | Data providers (yfinance, stooq, akshare) |

### Data Flow (Daily Trading)

```
Scheduler (16:00 HKT) → Orchestrator → DataProvider (fetch)
    → Strategy (generate signal)
    → Risk Gate (check limits)
    → Broker (execute)
    → Storage (persist state)
    → Notifier (send report)
```

### Data Flow (MCP Strategy Review)

```
User Input → SpecPM → BacktestEngine → Bull Analyst (LLM)
    → Bear Reviewer (LLM) → Debate (2 rounds)
    → Risk Gate → PM (LLM) → PMDecision
```

## Configuration

All config is in `config/policy.yaml`:

- **hard_gates**: MaxDD ≤ 20%, min 3 years data
- **yellow_flags**: DD warning [15-20]%, suspiciously high CAGR > 40%
- **weights**: cagr=0.35, max_dd=0.35, sharpe=0.20, turnover=0.10
- **scheduler**: run_time="15:30", timezone="Asia/Hong_Kong"
- **portfolio**: symbols ["2800.HK", "0700.HK", "9988.HK"]
- **broker**: mode (readonly/dry_run/live)

## Strategies

Located in `src/quant_trader/strategy/`:
- `ma_cross_strategy.py` - MA crossover (Dual MA)
- `mean_reversion.py` - Mean reversion strategy
- `channel_breakout.py` - Channel breakout strategy
- `regime.py` - Market regime filter (trending/ranging)

## Known Issues

1. **yfinance rate limiting** - Use direct HTTP API or alternative sources (akshare, stooq)
2. **param_sensitivity** - Not auto-calculated; required for Risk Gate yellow line judgment
3. **First live deployment** - Requires human approval (yellow flag)

## Data Sources (data/)

| Provider | Markets | Notes |
|----------|---------|-------|
| YFinanceProvider | US/HK | Direct HTTP, bypasses rate limits |
| TwelveDataProvider | Global | Requires API Key |
| AkShareProvider | HK/CN | Primary for HK stocks |
| StooqProvider | Global | Backup source |

## Brokers (broker/)

| Broker | Mode | Notes |
|--------|------|-------|
| LongBridgeBroker | Live | HK stocks |
| FutuBroker | Live | HK stocks |
| PaperBroker | Sim | Paper trading |
