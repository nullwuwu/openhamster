# E2E Scenarios

1. Start backend API with `quant-trader-api`.
2. Start frontend with `npm run dev --prefix apps/web`.
3. Open `/backtests`, queue a backtest run, wait until status changes from queued/running.
4. Open `/overview` and verify latest run + equity curve render.
5. Open `/trading` and verify nav/orders/positions panels render.
