# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added - Agent Trading System (Phase 1-4)

#### Phase 0: 稳定性保障
- **DataSourceManager** (`data/source_manager.py`)
  - 数据源自动故障切换 (akshare → yfinance → stooq)
  - `fetch_latest_price()` 获取最新价格
- **OrderGuard** (`order_guard.py`)
  - 重复下单防护
  - 单日交易次数限制
  - 冷却时间控制
- **Reconciler** (`reconciler.py`)
  - 持仓对账机制

#### Phase 1: 基础能力
- **AgentTrader** (`agent_interface.py`)
  - 统一交易接口
  - `get_positions()` / `get_account()` / `get_price()`
  - `buy()` / `sell()` 带风控
  - `send_report()` Telegram 汇报
  - RiskConfig 从 policy.yaml 读取

#### Phase 2: 分析能力
- **SignalAnalyzer** (`signal_analyzer.py`)
  - MA5/MA20 移动平均
  - RSI 超买超卖
  - MACD 金叉死叉 (histogram 变号)
  - 多信号综合判断

#### Phase 3: 智能化
- **MarketRegime** (`market_regime.py`)
  - 多指标投票判断 (above_ma20/60, ma_aligned, trend_strength)
  - Regime 枚举: TRENDING_UP / TRENDING_DOWN / RANGING
- **StrategySelector** (`strategy_selector.py`)
  - 根据市场环境 + 波动率选择策略
  - 高波动时调整权重
- **PositionSizer** (`position_sizer.py`)
  - 仓位计算 (置信度 * 最大仓位)
  - cash 上限 + 5% buffer
  - 一手成本兜底

#### Phase 4: 风控
- **RiskManager** (`risk_manager_new.py`)
  - 7大风控规则:
    1. 单日亏损熔断 (≥3%)
    2. 单股仓位上限 (≥15%)
    3. 总仓位上限 (≥80%)
    4. 现金不足
    5. 固定止损 (-8%)
    6. 固定止盈 (+15%)
    7. 移动止损 (从高点回撤 5%)

### Added
- **New Strategies**
  - RSI Strategy - RSI 超卖超买 + 中线交叉
  - MACD Strategy - MACD 金叉死叉 + 零轴交叉
- **Parameter Optimization**
  - MultiStrategyOptimizer - 支持多策略的网格搜索
  - STRATEGY_PARAMS 配置 - 统一管理策略参数范围
- **Enhanced Risk Management**
  - EnhancedRiskManager - 增强版风控
    - 追踪止损 (Trailing Stop)
    - 总仓位限制
    - 每日交易次数限制
    - 单日亏损限制
    - 现金储备管理
    - 波动率风控 (ATR)
  - Position 类 - 持仓信息管理
  - RiskState 类 - 风控状态跟踪
- **Walk-Forward** - 支持多策略 (ma_cross/rsi/macd)
- **Tests**
  - RSI 策略测试 (8 test cases)
  - MACD 策略测试 (11 test cases)
- **Dry Run**
  - `scripts/dry_run.py` - 观察信号不实际下单
  - `--auto-select` 自动选标的
- **Symbol Selection**
  - `SymbolSelector` - 基于流动性、波动性、趋势自动筛选
  - `DynamicSymbolManager` - 动态再平衡
- **Reconciler**
  - 持仓对账器 - 比对系统与券商持仓
  - `AutoReconciler` - 自动对账调度

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
