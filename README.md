# GobyShrimp

[中文说明](README.zh-CN.md)

> An auditable HK strategy factory for market-aware LLM research, deterministic governance, and local paper trading.

## Overview

GobyShrimp is not a generic trading bot. It is a controlled research-and-paper-trading system designed to answer operational questions before any real-capital path exists.

Current scope:
- HK-only market scope
- dynamic HK universe selection
- MiniMax as the default live LLM provider
- macro-only context pipeline
- local paper ledger with audit trail

## Why GobyShrimp

Most agent trading demos optimize for novelty. GobyShrimp optimizes for control.

It is built to answer:
- What symbol is being researched right now, and why?
- What strategy was proposed, by which provider, under which prompt contract?
- Why was a proposal rejected, kept as candidate, or promoted to paper?
- If paper NAV is flat, was that because price did not move, no rebalance was needed, or execution stalled?
- Is the macro pipeline healthy, degraded, or running on last known context?

## What It Does Today

### 1. HK universe selection

The system no longer runs on one hardcoded instrument. It uses `dynamic_hk` universe selection:
1. load HK spot candidates
2. filter for valid symbols and minimum turnover
3. rank by liquidity, momentum, stability, and price quality
4. enrich top candidates with multi-day factors
5. penalize missing history windows
6. select the top-ranked symbol as the research target

### 2. Market-aware snapshot

GobyShrimp builds a `market_snapshot` with:
- HK market profile
- selected symbol and universe rationale
- macro digest
- regime and volatility context
- preferred and discouraged strategy tags

### 3. MiniMax live strategy generation

All LLM calls go through a single `LLM Gateway`.
Current runtime providers:
- `minimax`
- `mock`

Prompt contracts live under `src/goby_shrimp/prompts`:
- `market_analyst`
- `strategy_agent`
- `research_debate`
- `risk_manager_llm`

The model produces structured strategy proposals, not arbitrary executable code.

### 4. Deterministic governance

A proposal must clear:
- hard risk gates
- score thresholds
- challenger delta rules
- cooldown rules
- macro lane health requirements
- paper acceptance rules

Governance outputs include:
- `phase`
- `next_step`
- `resume_conditions`
- promotion ETA
- blocked reasons

### 5. Local paper ledger

When a proposal is promoted to paper, GobyShrimp:
- initializes NAV
- boots the first paper trade with live market price
- records orders, positions, and NAV locally
- keeps evaluating the active strategy on each runtime cycle

Important boundary:
- prices come from live market data providers
- orders, positions, and NAV are simulated locally
- this is not broker execution

## Architecture

```mermaid
flowchart TD
    A["HK Universe Selection"] --> B["Market Snapshot"]
    M["Macro Chain\nFRED -> World Bank -> Last Known Context"] --> B
    B --> C["StrategyAgent\nMiniMax via LLM Gateway"]
    C --> D["ResearchDebateAgent"]
    D --> E["Risk Governance"]
    E -->|"keep_candidate"| F["Candidate Pool"]
    E -->|"promote_to_paper"| G["Active Strategy"]
    G --> H["Paper Execution Cycle"]
    H --> I["Orders / Positions / NAV"]
    E --> J["Audit Trail"]
    F --> J
    G --> J
    H --> J
```

## Dashboard Views

### `/command`
- runtime heartbeat and pipeline stage
- active strategy and latest execution result
- current HK universe selection and factor breakdown
- macro lane health
- candidate pool distribution
- baseline strategy catalog

### `/candidates`
- candidate ranking
- governance phase
- cooldown state
- promotion eligibility
- pool comparison

### `/research`
- market understanding
- universe rationale
- baseline fit
- strategy DSL
- debate
- evidence pack
- quality report
- blockers

### `/paper`
- NAV curve
- positions
- orders
- active strategy
- operational acceptance
- price freshness
- rebalance explanation

### `/audit`
- decision timeline
- universe selection history
- macro degradation / recovery
- provider fallback events
- governance cause chain

## Runtime Status

The command center exposes:
- `current_state`
- `current_stage`
- `stage_started_at`
- `stage_durations_ms`
- `last_run_at`
- `last_success_at`
- `last_failure_at`
- `consecutive_failures`
- `expected_next_run_at`
- `last_trigger`

Current stage coverage:
- event sync
- digest sync
- market snapshot build
- market analyst
- strategy generation
- decision materialization
- paper execution

## Market and Data Scope

### Current scope
- HK-only
- market-aware
- dynamic universe selection

### Price data routing
- `tencent`
- `akshare`
- `yfinance`
- `stooq`

### Macro routing
- `FRED`
- `World Bank`
- `last known context`

### Intentionally excluded
- news and announcement pipelines
- broker execution
- multi-market live trading
- automatic production trading

## Quick Start

### Backend
```bash
pip install -e .[dev]
alembic upgrade head
gobyshrimp-api
```

### Frontend
```bash
npm install --prefix apps/web
npm run dev --prefix apps/web
```

Default local endpoints:
- Frontend: `http://127.0.0.1:5173`
- Backend: `http://127.0.0.1:8000`

## Configuration

Configuration precedence:

```text
defaults < config/base.yaml < config/local.yaml < .env < .env.local < environment variables
```

Recommended secrets in `.env.local`:
- `MINIMAX_API_KEY`
- `FRED_API_KEY`

Useful runtime overrides:
- `LLM_PROVIDER=minimax`
- `LLM_MODEL=MiniMax-M2.5`
- `LLM_TEMPERATURE=0.3`
- `DATABASE_URL=sqlite:///var/db/gobyshrimp.db`

Reference files:
- `config/base.yaml`
- `config/local.yaml`
- `.env.example`
- `docs/configuration.md`

## Manual Operations

### Trigger research immediately
- API: `POST /api/v1/runtime/sync`
- Dashboard: `Run Now`

### Runtime LLM status
- API: `GET /api/v1/runtime/llm`

### Acceptance report
- API: `GET /api/v1/ops/acceptance-report?window_days=30`
- Script:
  - `python scripts/generate_acceptance_report.py`
  - `python scripts/generate_acceptance_report.py --window-days 30 --format json`

## Validation Baseline

- `pytest tests -q` -> `122 passed, 8 skipped`
- `npm run build --prefix apps/web` -> passed

## Release Status

Current implementation status:
- engineering refactor: `92%`
- product readiness: `98%`
- auditable strategy factory target: `94%`

Already true:
- HK-only market-aware research path is active
- MiniMax live path is integrated
- runtime scheduler is real
- paper ledger records orders, positions, and NAV
- governance, ETA, and audit trail are visible

Still needs time:
- longer live operating history
- thicker long-horizon quality statistics
- more mature provider health history

## Project Layout

```text
apps/web/                 Vue dashboard
config/                   tracked system config
src/goby_shrimp/api/      FastAPI app, DTOs, services
src/goby_shrimp/data/     market data providers and universe logic
src/goby_shrimp/events/   macro provider chain
src/goby_shrimp/prompts/  agent prompt contracts
src/goby_shrimp/risk/     risk models and review helpers
src/goby_shrimp/runtime/  scheduler and runtime control
src/goby_shrimp/strategy/ strategy registry and plugins
var/db/                   local business DB + runtime state DB
```

## Documentation
- `docs/ARCHITECTURE.md`
- `docs/PROJECT_OVERVIEW.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/DECISIONS.md`
- `docs/configuration.md`
- `docs/RUNBOOK.md`
- `docs/RELEASE_CHECKLIST.md`
- `docs/releases/v0.1.0.md`

## Known Limits
- SQLite is still the delivery default, not the final operating database
- paper execution is simulated, not broker-connected
- macro context intentionally excludes news and announcements
- long-horizon validation still depends on accumulating more live history

## Roadmap

### Near term
- accumulate longer operating history
- improve long-horizon quality statistics
- harden provider health history and recovery semantics
- tighten paper execution explanations and audit drill-down

### Later
- PostgreSQL migration when operating load justifies it
- richer market-aware strategy catalog
- stronger runtime operations history and reporting
