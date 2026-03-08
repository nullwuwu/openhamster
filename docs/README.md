# quant-trader 项目总结

## 一、项目定位

**MCP Server** — 为 OpenClaw 提供量化投研能力的自动化系统。

从策略想法 → 回测 → 评审 → 决策，全流程自动化。

---

## 二、核心架构

```
用户输入 (策略想法)
    ↓
┌─────────────────────────────────────────────────────┐
│  DecisionGraph (6节点决策流程)                      │
├─────────────────────────────────────────────────────┤
│  ① Spec PM      → 结构化用户输入                    │
│  ② Backtest     → 回测引擎执行                      │
│  ③ Bull Analyst → LLM 看多论点                      │
│  ④ Bear Reviewer → LLM 看空论点 + 辩论             │
│  ⑤ Risk Gate    → 硬规则检查                        │
│  ⑥ PM          → LLM 综合决策                      │
└─────────────────────────────────────────────────────┘
    ↓
输出: PMDecision (GO/NO_GO/REVISE + 实验建议)
```

---

## 三、核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| **BacktestEngine** | `backtest_engine.py` | 数据获取、回测执行、指标计算 |
| **DecisionGraph** | `decision_graph.py` | 6节点流程编排、LLM调用 |
| **Risk Gate** | `reviewer.py` | 硬规则一票否决 |
| **LLM Client** | `llm.py` | MiniMax API 调用 |

---

## 四、风控策略 (policy.yaml)

### 硬红线 (Hard Gates)
- MaxDD ≤ 20%
- 数据 ≥ 3年
- 必须考虑: slippage, commission, tax, dividend_withholding

### 黄线 (Yellow Flags)
- MaxDD 在 [15%, 20%] 区间 → 警告
- CAGR > 40% → 疑似过拟合
- 参数敏感性 > 50% → 警告
- 首次实盘 → 必须人工确认

### 权重配置
```yaml
cagr: 0.35    # 收益
max_dd: 0.35   # 回撤
sharpe: 0.20   # 夏普
turnover: 0.10 # 换手率
```

### 限制
- 辩论最多 2 轮
- 迭代最多 3 次
- 超限 → STOP_AND_NOTIFY_HUMAN

---

## 五、关键数据模型

```python
BacktestResult:
  - cagr, max_drawdown, sharpe
  - annual_turnover, data_years
  - assumptions, param_sensitivity, is_first_live

PMDecision:
  - verdict: GO | NO_GO | REVISE
  - utility_score
  - weights, weight_adjust_reason
  - reasoning
  - risk_warnings
  - next_experiments (≤2)
  - requires_human_approve
```

---

## 六、LLM 流程 (MiniMax)

1. **Bull Analyst** → 看多论点 (JSON)
2. **Bear Reviewer** → 看空论点 (JSON)
3. **Debate** → 2轮反驳
4. **Risk Gate** → 硬规则判定
5. **PM** → 综合决策 (JSON)

---

## 七、当前状态

| 组件 | 状态 |
|------|------|
| BacktestEngine | ✅ 支持 Dual MA, Mean Reversion, Channel Breakout + DataProvider 抽象层 |
| DecisionGraph | ✅ 6节点流程 + LLM 接入 |
| Risk Gate | ✅ 硬规则 + 效用分 |
| MCP Server | ✅ strategy_review, strategy_iterate |
| 数据源 | ✅ yfinance, akshare, stooq, twelve_data |
| Broker | ✅ longbridge, futu, paper trading |
| 单测 | ✅ 20+ 测试覆盖核心模块 |

---

## 九、可改进点

1. ~~数据源~~ — ✅ 已实现 AKShare, Stooq, TwelveData
2. ~~更多策略~~ — ✅ 已实现 Dual MA, Mean Reversion, Channel Breakout
3. ~~模拟交易~~ — ✅ 已实现 Paper Broker
4. **参数敏感性** — 尚未实现自动计算 (P0)
5. **实盘对接** — LongBridge/Futu 已实现，待配置

---

## 十、快速开始

### 安装依赖

```bash
# 推荐使用 uv（更快）
pip install uv
uv pip install -e ".[dev]"
```

### 环境变量配置

```bash
# MiniMax LLM (必需)
export MINIMAX_API_KEY="your-minimax-key"

# Twelve Data (可选，数据源)
# 免费 tier: 每分钟 8 次请求
export TWELVE_DATA_API_KEY="your-twelve-data-key"
```

### 配置文件设置

```bash
# 复制示例配置
cp config/policy.example.yaml config/policy.yaml
cp config/paper_trading.example.yaml config/paper_trading.yaml

# 编辑实际配置（包含敏感信息）
vim config/policy.yaml
```

**注意**: `config/*.yaml` 已被 `.gitignore` 忽略，示例配置会被跟踪。

### 运行测试

```bash
pytest tests/ -v
```

### 启动 MCP Server

```bash
python -m quant_trader.server
```

### 使用示例

```python
from quant_trader.backtest_engine import run_dual_ma_backtest
from quant_trader.decision_graph import DecisionGraph

# 1. 回测
result = run_dual_ma_backtest(
    ticker="SPY",
    fast_period=20,
    short_period=50,
    start_date="2020-01-01",
)

# 2. 决策
g = DecisionGraph(api_key="your-minimax-key")
decision = g.run("Dual MA 策略", backtest_params={
    "cagr": result.cagr,
    "max_drawdown": result.max_drawdown,
    "sharpe": result.sharpe,
    ...
})
```

---

**一句话总结**：一个自动化量化策略评审系统，通过 LLM 驱动的 Bull/Bear 辩论 + 硬规则风控，输出 GO/NO_GO/REVISE 决策。

---

## 附录：Agent Trading System (Phase 1-4)

> 2026-03 新增：智能交易 Agent 模块

### 模块架构

```
┌─────────────────────────────────────────────────────────────┐
│                    quant-trader Agent                        │
├─────────────────────────────────────────────────────────────┤
│  Phase 0: 稳定性                                            │
│    • DataSourceManager - 数据源自动故障切换                   │
│    • OrderGuard - 重复下单防护                               │
│    • Reconciler - 持仓对账                                   │
├─────────────────────────────────────────────────────────────┤
│  Phase 1: 基础能力                                          │
│    • AgentTrader - 统一交易接口                              │
├─────────────────────────────────────────────────────────────┤
│  Phase 2: 分析能力                                          │
│    • SignalAnalyzer - 技术指标 + 信号生成                    │
├─────────────────────────────────────────────────────────────┤
│  Phase 3: 智能化                                            │
│    • MarketRegime - 市场环境判断 (多指标投票)                 │
│    • StrategySelector - 根据环境选择策略                      │
│    • PositionSizer - 仓位计算                               │
├─────────────────────────────────────────────────────────────┤
│  Phase 4: 风控                                              │
│    • RiskManager - 7大风控规则                               │
└─────────────────────────────────────────────────────────────┘
```

### 7大风控规则

| 规则 | 触发条件 | 动作 |
|------|----------|------|
| 单日亏损熔断 | ≥3% | REJECT |
| 单股仓位上限 | ≥35% | REDUCE |
| 总仓位上限 | ≥80% | REDUCE |
| 现金不足 | >95% 现金 | REDUCE |
| 固定止损 | -8% | FORCE_SELL |
| 固定止盈 | +15% | FORCE_SELL |
| 移动止损 | 从高点回撤 5% | FORCE_SELL |

### 参数调优 (2800.HK 回测 2023-01-01~2026-01-01)

**参数范围**: max_single_position_ratio (单股仓位上限)

| 仓位上限 | 总收益 | MaxDD | Sharpe |
|----------|--------|-------|--------|
| 15% | 4.66% | -2.54% | 86.20 |
| 25% | 7.79% | -4.21% | 86.63 |
| **35%** | **10.91%** | **-5.86%** | **87.02** |
| 50% | 15.57% | -8.29% | 87.43 |
| 无上限 | 24.94% | -12.99% | 88.52 |
| 无风控 | 23.08% | -18.37% | 48.45 |

**结论**:
- 推荐默认值: **35%** (MaxDD -5.86%, Sharpe 87.02)
- Sharpe 是无风控的 **1.8x**
- MaxDD 从 -18.37% 降至 -5.86%，降低 68%

### 快速开始

```python
from quant_trader.agent_interface import get_agent_trader
from quant_trader.signal_analyzer import get_signal_analyzer
from quant_trader.market_regime import get_market_regime
from quant_trader.strategy_selector import get_strategy_selector
from quant_trader.position_sizer import get_position_sizer
from quant_trader.risk_manager_new import get_risk_manager, RiskAction

# 初始化
trader = get_agent_trader()

# 分析流程
ohlcv = trader.get_ohlcv('2800.HK', days=90)
regime = get_market_regime().analyze(ohlcv)
signal = get_signal_analyzer().analyze('2800.HK', ohlcv)

# 策略 + 仓位
strategies = get_strategy_selector().select(regime.regime, regime.indicators['volatility'])
position = get_position_sizer().calculate(
    ticker='2800.HK',
    price=trader.get_price('2800.HK'),
    total_assets=account['total_assets'],
    cash=account['cash'],
    signal_confidence=signal.confidence,
    market_regime=regime.regime,
)

# 风控检查
risk = get_risk_manager()
check = risk.pre_trade_check(ticker, position.shares, price, total_assets, cash, positions)
```
