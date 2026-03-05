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
| BacktestEngine | ✅ 支持 Dual MA, DataProvider 抽象层 (TwelveData + YFinance fallback) |
| DecisionGraph | ✅ 6节点流程 + LLM 接入 |
| Risk Gate | ✅ 硬规则 + 效用分 |
| MCP Server | ✅ strategy_review, strategy_iterate |
| 单测 | ✅ 7个测试全绿 |

---

## 九、可改进点

1. ~~数据源~~ — ✅ 已接入 DataProvider 抽象层
2. **更多策略** — Momentum, Mean Reversion
3. **参数敏感性** — 尚未实现自动计算 (P0)
4. **实盘对接** — 暂无

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
