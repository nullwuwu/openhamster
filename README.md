# quant-trader

Frontend + backend quantitative research workspace.

## Stack

- Backend: FastAPI + SQLAlchemy 2 + Alembic
- Frontend: Vue 3 + Vite + shadcn-vue + Tailwind + Pinia + TanStack Query + ECharts
- Database: SQLite by default (`DATABASE_URL`), PostgreSQL-ready schema

## Repository Layout

- `src/quant_trader`: backend domain and API modules
- `apps/web`: dashboard frontend
- `config/base.yaml` + `config/local.yaml`: layered config files
- `var/`: runtime outputs (`db`, `logs`, `cache`)
- `.github/workflows/ci.yml`: Python + Node CI

## Run Backend

```bash
pip install -e ".[dev]"
quant-trader-api
```

Backend API base URL: `http://127.0.0.1:8000/api/v1`

## Run Frontend

```bash
cd apps/web
npm install
npm run dev
```

Frontend URL: `http://127.0.0.1:5173`

## API v1

- `GET /api/v1/overview`
- `GET /api/v1/strategies`
- `POST /api/v1/backtests/runs`
- `GET /api/v1/backtests/runs`
- `GET /api/v1/backtests/runs/{run_id}`
- `POST /api/v1/experiments/optimizer-runs`
- `POST /api/v1/experiments/walkforward-runs`
- `GET /api/v1/paper/nav`
- `GET /api/v1/paper/orders`
- `GET /api/v1/paper/positions`

## Config System

- Priority: defaults < `config/base.yaml` < `config/local.yaml` < env vars
- Source tracing is available via `quant_trader.config.get_setting_source`
- Detailed field docs: `docs/configuration.md`

## Migrations

```bash
alembic upgrade head
```

SQLite to PostgreSQL migration entrypoint:

```bash
python scripts/sqlite_to_postgres.py --source var/db/quant_trader.db --target postgresql+psycopg://user:pass@host/db
```
