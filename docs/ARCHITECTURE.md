# quant-trader 系统架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           OpenClaw Agent                                │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        MCP Server (server.py)                           │
│  ┌──────────────────────┐  ┌──────────────────────┐                  │
│  │  strategy_review     │  │  strategy_iterate    │                  │
│  │  (单次评审)          │  │  (自动迭代)          │                  │
│  └──────────────────────┘  └──────────────────────┘                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    DecisionGraph (decision_graph.py)                    │
│                                                                         │
│   ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐          │
│   │ Spec PM │───▶│ Backtest │───▶│ Bull    │◀──▶│ Bear    │          │
│   │         │    │Operator  │    │Analyst  │    │Reviewer │          │
│   └─────────┘    └─────────┘    └─────────┘    └─────────┘          │
│         │            │              │              │                    │
│         │            │              │              │                    │
│         │            ▼              │              │                    │
│         │     ┌─────────┐           │              │                    │
│         │     │Backtest │           │              │                    │
│         │     │ Result  │───────────┼──────────────┘                    │
│         │     └─────────┘           ▼                                   │
│         │            │         ┌─────────┐                             │
│         │            └────────▶│ Risk    │                             │
│         │                      │ Gate    │                             │
│         │                      └─────────┘                             │
│         │                          │                                   │
│         │                          ▼                                   │
│         │                      ReviewOutput                            │
│         │                          │                                   │
│         └────────────────────────▶│ PM                                │
│                                    │                                    │
│                                    ▼                                    │
│                               PMDecision                                │
└─────────────────────────────────────────────────────────────────────────┘
       │                                   │
       ▼                                   ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                        外部依赖                                          │
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │                     DataProvider (可插拔)                         │   │
│  │  ┌──────────────────┐  ┌──────────────────┐                    │   │
│  │  │ TwelveDataProvider│  │YFinanceProvider │                    │   │
│  │  │ (默认, 有备)      │  │ (fallback)      │                    │   │
│  │  └──────────────────┘  └──────────────────┘                    │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                              │                                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                    │
│  │  MiniMax   │  │  policy    │  │  MCP       │                    │
│  │  LLM       │  │  (配置)    │  │  Server    │                    │
│  └─────────────┘  └─────────────┘  └─────────────┘                    │
└─────────────────────────────────────────────────────────────────────────┘
│  │  (数据)     │  │  LLM       │  │  (配置)    │                    │
│  └─────────────┘  └─────────────┘  └─────────────┘                    │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 数据流：BacktestResult → DecisionGraph

```
BacktestEngine.run()
       │
       ▼
BacktestResult
{
  cagr: float,
  max_drawdown: float,
  sharpe: float,
  annual_turnover: float,
  data_years: float,
  assumptions: list[str],
  param_sensitivity: float | None,  ← P0 待自动计算
  is_first_live: bool
}
       │
       ▼ (传入 backtest_params)
DecisionGraph.run_full_flow()
       │
       ├──▶ BacktestOperator.execute() → BacktestData
       │
       ├──▶ BullAnalyst (LLM) → bull_points
       │
       ├──▶ BearReviewer (LLM) → bear_points
       │
       ├──▶ Debate (2轮)
       │
       ├──▶ RiskGate.execute() → ReviewOutput
       │
       └──▶ PortfolioManager (LLM) → PMDecision
```

---

## LLM 节点说明

当前使用 **MiniMax M2.5** 模型：

| 节点 | Prompt | 输出 |
|------|--------|------|
| Bull Analyst | 看多论点模板 | `{"bull_points": [...], "strengths": [...]}` |
| Bear Reviewer | 看空论点模板 | `{"bear_points": [...], "weaknesses": [...]}` |
| PM | prompts/pm.md | `PMDecision` JSON |

**可扩展**：未来可接入其他 LLM（OpenAI, Claude, 本地模型）

---

## 已知限制 / 坑

| # | 问题 | 状态 | 说明 |
|---|------|------|------|
| 1 | yfinance 限流 | ⚠️ | 高频请求会被限流，建议加缓存或换数据源 |
| 2 | param_sensitivity 手填 | 🔴 P0 | Risk Gate 黄线判断依赖此字段，需自动计算 |
| 3 | executeSell PnL 计算 | ✅ 已修复 | 早期版本仓位方向有 bug，已修复 |

---

## 模块说明

### 1. server.py (MCP Server)

```python
# 可用 Tools
@mcp.tool()
def strategy_review(cagr, max_drawdown, sharpe, ...)  # Risk Gate 单次检查

@mcp.tool()  
def strategy_review_full(user_input, backtest_params)  # 完整流程

@mcp.tool()
def strategy_iterate(user_input, backtest_params)     # 自动迭代

@mcp.tool()
def get_policy()  # 查看当前风控配置
```

### 2. DecisionGraph (6节点流程)

| 节点 | 类 | 输入 | 输出 |
|------|-----|------|------|
| ① Spec PM | `SpecPM` | user_input | StrategySpec |
| ② Backtest | `BacktestOperator` | spec | BacktestData |
| ③ Bull | `BullAnalyst` | BacktestData | bull_points |
| ④ Bear | `BearReviewer` | BacktestData + Bull | bear_points |
| ⑤ Risk Gate | `RiskGate` | BacktestData | ReviewOutput |
| ⑥ PM | `PortfolioManager` | 全部上下文 | PMDecision |

### 3. BacktestEngine

```python
engine = BacktestEngine()
result = engine.run(
    ticker="SPY",
    strategy=DualMAStrategy(fast=20, slow=50),
    start_date="2020-01-01",
    end_date="2025-01-01",
)
# → BacktestResult
```

### 4. Risk Gate (reviewer.py)

硬规则检查，返回 GO/NO_GO/REVISE：

```python
risk_gate_review(backtest_result) → ReviewOutput
```

### 5. LLM Client (llm.py)

MiniMax API 封装：

```python
client = MiniMaxClient(api_key="...")
client.chat_json(user_prompt) → dict
```

---

## 数据流

```
1. 用户输入: "做一个动量策略"
              │
              ▼
2. SpecPM 解析 → {name, description, target_cagr, ...}
              │
              ▼
3. BacktestEngine 回测 → {cagr: 0.15, max_drawdown: 0.12, ...}
              │
              ▼
4. Bull Analyst (LLM) → {bull_points: [...], strengths: [...]}
              │
              ▼
5. Bear Reviewer (LLM) → {bear_points: [...], weaknesses: [...]}
              │
              ▼
6. 辩论 (2轮) → DebateResult
              │
              ▼
7. Risk Gate → {verdict: REVISE, hard_gates: [], yellow_flags: [...]}
              │
              ▼
8. PM (LLM) → {verdict: GO, utility_score: 7.5, next_experiments: [...]}
```

---

## 配置文件

### policy.yaml

```yaml
hard_gates:        # 硬红线
  max_drawdown: 0.20
  min_data_years: 3
  required_assumptions: [slippage, commission, tax, dividend_withholding]

yellow_flags:      # 黄线警告
  max_drawdown_warning_range: [0.15, 0.20]
  suspiciously_high_cagr: 0.40

weights:           # 效用分权重
  cagr: 0.35
  max_dd: 0.35
  sharpe: 0.20
  turnover: 0.10

limits:            # 流程限制
  max_debate_rounds: 2
  max_iterations: 3

trading_costs:     # 交易成本
  slippage_bps: 5
  commission_rate: 0.001
```

---

## 扩展点

1. **新增策略** → 在 `backtest_engine.py` 添加 Strategy 子类
2. **新增数据源** → 修改 `BacktestEngine.load_data()`
3. **新增 LLM** → 修改 `llm.py` 支持其他 API
4. **新增风控规则** → 修改 `reviewer.py` 和 `policy.yaml`
