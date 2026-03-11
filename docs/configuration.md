# Configuration Guide

This project uses layered settings.

## Load Order

1. Built-in defaults from `AppSettings`
2. `config/base.yaml`
3. `config/local.yaml`
4. Environment variables

## Key Environment Variables

- `DATABASE_URL` -> `storage.database_url`
- `APP_TIMEZONE` -> `timezone`
- `MINIMAX_API_KEY` -> `integrations.minimax_api_key`
- `TWELVE_DATA_API_KEY` -> `integrations.twelve_data_api_key`
- `TUSHARE_TOKEN` -> `integrations.tushare_token`
- `ALPHAVANTAGE_API_KEY` -> `integrations.alphavantage_api_key`
- `ITICK_TOKEN` -> `integrations.itick_token`

## Tushare Scope (Current Phase)

Tushare integration stays as-is in this phase; enhancement items (provider health checks and real-token integration tests) are intentionally deferred.

## Source & Purpose Annotation Rule

Every config section in `config/base.yaml` and `config/local.yaml` must include:

- `[Source 来源]`
- `[Purpose 用途]`

This rule keeps parameter provenance explicit for audits and handovers.
