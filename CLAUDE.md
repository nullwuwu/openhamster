# CLAUDE.md

This repository is `OpenHamster`, an auditable strategy factory.

## Current Product Shape
- Backend API: `src/openhamster/api`
- Frontend dashboard: `apps/web`
- LLM entrypoint: `src/openhamster/llm_gateway.py`
- Event pipeline: `src/openhamster/events`
- Runtime storage: `var/db`, `var/logs`, `var/cache`

## What Is In Scope
- Agent command dashboard
- Strategy proposals, risk decisions, audit records
- Event stream and daily event digest
- Backtest and experiment runs exposed through `/api/v1`
- Runtime LLM provider switching between `minimax` and `mock`

## What Is Not In Scope
- Old MCP server flow
- Old orchestrator / scheduler trading flow
- Old policy.yaml execution path
- Notification factory based legacy runtime

Those paths have been removed and should not be reintroduced.

## Run Commands
```bash
pip install -e .[dev]
alembic upgrade head
openhamster-api
npm install --prefix apps/web
npm run dev --prefix apps/web
```

## Config Rules
- Repository defaults: `config/base.yaml`
- Local non-secret overrides: `config/local.yaml`
- Secrets: `.env.local`
- Runtime switches: database-backed runtime overrides

See:
- `docs/configuration.md`
- `docs/CONFIG_BOUNDARIES.md`

## Guardrails
- Do not add new legacy compatibility layers
- Do not add secrets to tracked config files
- Prefer deleting stale product paths over preserving dead branches
