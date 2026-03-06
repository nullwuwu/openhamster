# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

## [0.1.0] - 2026-03-07

### Added
- **MCP Server** - Strategy review tools via `strategy_review` and `strategy_iterate`
- **DecisionGraph** - 6-node LLM-driven decision flow (SpecPM → Backtest → Bull → Bear → RiskGate → PM)
- **BacktestEngine** - Backtesting with multiple data sources
- **Strategies**
  - Dual MA (DualMA 50/150)
  - Mean Reversion
  - Channel Breakout
  - Regime Filter (trending/ranging detection)
- **Data Providers**
  - YFinanceProvider (direct HTTP API)
  - AkShareProvider (HK/CN stocks)
  - StooqProvider (global)
  - TwelveDataProvider (optional)
- **Brokers**
  - LongBridgeBroker (live trading)
  - FutuBroker (live trading)
  - PaperBroker (simulation)
- **Risk Management**
  - Risk Gate with hard rules (MaxDD, data years)
  - Yellow flag warnings
  - Utility score calculation
- **Walk-Forward Validation** - Parameter robustness testing

### Changed
- Reorganized project structure (moved strategies to `strategy/`, backtest to `backtest/`, risk to `risk/`)
- Upgraded to Python 3.10+ (supports `float | None` syntax)
- Replaced pandas-datareader with direct HTTP APIs (Python 3.12 compatibility)

### Fixed
- Stooq provider now uses direct HTTP API instead of deprecated pandas-datareader

### Removed
- Duplicate walk_forward.py (kept in backtest/)

---

## Project Philosophy

**Goal**: Build an automated quantitative trading system with LLM-driven strategy review and risk management.

**Core Principles**:
1. Risk-first - MaxDD limits are hard gates
2. Evidence-based - All strategies require walk-forward validation
3. Automated - Daily execution with minimal human intervention
4. Transparent - Daily reports with clear metrics
