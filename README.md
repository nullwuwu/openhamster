# GobyShrimp

GobyShrimp is an auditable strategy factory for quantitative research and paper trading. The system is being reshaped around a small agent team: `MarketAnalystAgent`, `StrategyAgent`, `ResearchDebateAgent`, `RiskManagerAgent`, a deterministic `ExecutionAgent`, and an `AuditService` that records every state transition.

## Current shape
- Backend package: `src/goby_shrimp`
- Frontend dashboard: `apps/web`
- Runtime artifacts: `var/db`, `var/logs`, `var/cache`
- Database layer: SQLAlchemy 2.0 + Alembic, defaulting to SQLite through `DATABASE_URL`
- Event layer: macro inputs stored as `EventStream` plus `DailyEventDigest`

## Dashboard routes
- `/command`: command center with active strategy, market snapshot, risk decision, and event digest
- `/candidates`: candidate ladder and promotion context
- `/research`: proposal detail, debate report, evidence pack, and strategy DSL
- `/paper`: paper trading NAV, positions, orders, and current approved strategy
- `/audit`: risk decisions, audit ledger, daily digests, and event drill-down

## Operational report
- API: `GET /api/v1/ops/acceptance-report?window_days=30`
- Local script:
  - `python scripts/generate_acceptance_report.py`
  - `python scripts/generate_acceptance_report.py --window-days 30 --format json`

The acceptance report summarizes:
- quality track record
- operational acceptance
- macro pipeline health
- governance phase, next step, and resume conditions

## Runtime status
The command center now exposes pipeline heartbeat fields so the dashboard can show whether the system is still running as expected:
- `current_state`
- `last_run_at`
- `last_success_at`
- `last_failure_at`
- `consecutive_failures`
- `expected_next_run_at`
- `last_trigger`

The dashboard also exposes governance ETA fields so you can see when a candidate may be eligible to challenge the active strategy:
- `eta_kind`
- `estimated_next_eligible_at`

Supported ETA modes:
- `next_sync_window`
- `cooldown_window`
- `quality_revalidation`
- `review_pending`

The periodic scheduler is now a dedicated runtime module instead of inline app glue:
- `src/goby_shrimp/runtime/scheduler.py`

You can also trigger research manually:
- API: `POST /api/v1/runtime/sync`
- Dashboard: `Run Now`

## Quick start
```bash
pip install -e .[dev]
alembic upgrade head
gobyshrimp-api
npm install --prefix apps/web
npm run dev --prefix apps/web
```

## Configuration
Configuration is loaded in a fixed precedence order:
`defaults < config/base.yaml < config/local.yaml < .env < .env.local < environment variables`

Source tracking remains available through `goby_shrimp.config.get_setting_source`.
For local secrets, copy [`.env.example`](/Users/a1/.openclaw/workspace/projects/quant-trader/.env.example) to `.env.local`.
The active repository config files are documented in [`config/README.md`](/Users/a1/.openclaw/workspace/projects/quant-trader/config/README.md).

## Event input status
This iteration now runs a macro-only event pipeline:
- `FRED -> World Bank -> last known context` for the macro lane

The macro lane feeds `EventStream`, `DailyEventDigest`, `MarketSnapshot`, and the LLM soft-score context. If upstream providers fail, GobyShrimp keeps running, surfaces macro reliability state in the command center, and can reuse the last known macro context as a controlled fallback.

## LLM integration
MiniMax is now the default real LLM provider in configuration, behind the `LLM Gateway`.

Required env var:
- `MINIMAX_API_KEY`

Useful overrides:
- `LLM_PROVIDER=minimax`
- `LLM_MODEL=MiniMax-M2.5`
- `LLM_TEMPERATURE=0.3`
- `FRED_API_KEY=...`

The dashboard can switch the runtime provider between `minimax` and `mock`. If the key is missing or the provider call fails, GobyShrimp records the fallback and drops to `mock`.

## Agent prompting
Prompt contracts now live under [`src/goby_shrimp/prompts`](/Users/a1/.openclaw/workspace/projects/quant-trader/src/goby_shrimp/prompts):
- `market_analyst`
- `strategy_agent`
- `research_debate`
- `risk_manager_llm`

Each prompt module owns its `system_prompt`, payload builder, schema hint, and `prompt_version`. Business code no longer hardcodes prompt text in the API service layer.

## Strategy plugins
Built-in baseline strategies are now declared as plugins under [`src/goby_shrimp/strategy/plugins.py`](/Users/a1/.openclaw/workspace/projects/quant-trader/src/goby_shrimp/strategy/plugins.py). The registry and prompt layer both read from the same plugin catalog, so adding a new baseline no longer requires editing the factory and prompt contract separately.

## Database migration path
SQLite stays as the default delivery path for speed. PostgreSQL migration remains straightforward because the project already uses:
- `DATABASE_URL`
- SQLAlchemy ORM
- Alembic schema management

A future export/import path can be built on top of `scripts/sqlite_to_postgres.py`.

## Documentation
- `docs/ARCHITECTURE.md`
- `docs/PROJECT_OVERVIEW.md`
- `docs/IMPLEMENTATION_STATUS.md`
- `docs/DECISIONS.md`
- `docs/configuration.md`
- `docs/RUNBOOK.md`

## Current validation baseline
- `pytest tests -q` -> `122 passed, 8 skipped`
- `npm run build --prefix apps/web` -> passed
