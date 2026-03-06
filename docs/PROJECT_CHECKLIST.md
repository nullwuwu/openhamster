# 量化项目必备内容清单

> 一个专业、可复现的量化交易项目应该包含的内容

---

## 一、核心代码

### 1.1 回测系统
- [ ] **数据获取** — 多种数据源支持 (yfinance, Alpha Vantage, Bloomberg, etc.)
- [ ] **策略基类** — 统一的策略接口
- [ ] **回测引擎** — 信号生成、仓位计算、收益计算
- [ ] **交易成本模型** — 滑点、佣金、印花税、流动性冲击
- [ ] **保证金/杠杆** — 支持做空、杠杆、期货

### 1.2 策略库
- [ ] **趋势跟踪** — Dual MA, Triple MA, ATR Breakout
- [ ] **均值回归** — Bollinger Bands, RSI, Z-Score
- [ ] **统计套利** — Pairs Trading, Index Arbitrage
- [ ] **机器学习** — ML-based signals (optional)

### 1.3 风险管理
- [ ] **仓位管理** — Kelly Criterion, Fixed Fractional, Vol-based
- [ ] **止损机制** — 固定止损、移动止损、时间止损
- [ ] **分散化** — 资产配置、相关性管理

---

## 二、因子与数据

### 2.1 数据管理
- [ ] **数据清洗** — 缺失值、异常值处理
- [ ] **数据对齐** — 多资产时间序列对齐
- [ ] **特征工程** — 技术因子、基本面因子、另类因子
- [ ] **数据缓存** — 本地存储、增量更新

### 2.2 因子库
| 类别 | 因子示例 |
|------|----------|
| 趋势 | MA(5/10/20/50/200), EMA, MACD, ATR |
| 动量 | ROC, RSI, CCI, Williams %R |
| 波动率 | StdDev, ATR, Bollinger Width |
| 成交量 | OBV, VWAP, ADX |
| 价值 | P/E, P/B, Dividend Yield |
| 质量 | ROE, Debt/Equity, Gross Margin |

---

## 三、评估与验证

### 3.1 核心指标
- [ ] **收益指标** — CAGR, Total Return, Monthly Return
- [ ] **风险指标** — Max Drawdown, Volatility, VaR, CVaR
- [ ] **风险调整** — Sharpe Ratio, Sortino Ratio, Calmar Ratio
- [ ] **交易指标** — Win Rate, Profit Factor, Avg Trade, Exposure

### 3.2 过拟合检测
- [ ] **样本外测试** — Walk-Forward, Cross-Validation
- [ ] **参数敏感性** — 参数稳定性分析
- [ ] **蒙特卡洛** — 随机化样本区间
- [ ] **时间外科** — 去除特定时间段

### 3.3 压力测试
- [ ] **历史情景** — 2008, 2020, 2022
- [ ] **极端行情** — 黑天鹅模拟
- [ ] **流动性测试** — 大规模成交滑点

---

## 四、工程化

### 4.1 代码质量
- [ ] **类型标注** — Python type hints
- [ ] **单测覆盖** — pytest, coverage > 80%
- [ ] **文档** — docstring, README
- [ ] **Linting** — ruff, black

### 4.2 配置管理
- [ ] **策略参数** — YAML/JSON 配置
- [ ] **环境配置** — dev/staging/prod
- [ ] **密钥管理** — .env, secrets manager

### 4.3 版本控制
- [ ] **Git** — 提交规范、branch 策略
- [ ] **数据版本** — 数据集版本控制
- [ ] **模型版本** — 策略参数快照

---

## 五、部署与监控

### 5.1 交易执行
- [ ] **API 对接** — Broker API (Interactive Brokers, Alpaca, etc.)
- [ ] **订单管理** — 市价/限价/止损单
- [ ] **执行监控** — 成交反馈、异常告警

### 5.2 监控系统
- [ ] **实时 Dashboard** — 收益、仓位、风险
- [ ] **日志系统** — 交易记录、错误追踪
- [ ] **告警机制** — Telegram, Slack, Email
- [ ] **性能监控** — 延迟、吞吐量

### 5.3 自动化
- [ ] **定时任务** — 数据更新、策略再训练
- [ ] **CI/CD** — 自动测试、部署
- [ ] **容器化** — Docker, Kubernetes

---

## 六、合规与风控

### 6.1 合规
- [ ] **交易限制** — 持仓限制、交易时段
- [ ] **审计日志** — 完整操作记录
- [ ] **风控规则** — 熔断机制

### 6.2 资金管理
- [ ] **账户隔离** — 实盘/模拟分离
- [ ] **限额控制** — 单日/单笔限额
- [ ] **回撤监控** — 自动减仓/停仓

---

## 七、文档清单

| 文档 | 说明 |
|------|------|
| `README.md` | 项目概述、快速开始 |
| `ARCHITECTURE.md` | 系统架构、技术选型 |
| `API.md` | 接口文档 |
| `STRATEGY.md` | 策略说明 |
| `BACKTEST.md` | 回测结果分析 |
| `DEPLOY.md` | 部署指南 |
| `CHANGELOG.md` | 版本变更记录 |

---

## 八、项目结构示例

```
quant-project/
├── config/
│   ├── strategies.yaml
│   ├── risk.yaml
│   └── brokers.yaml
├── data/
│   ├── raw/
│   ├── processed/
│   └── cache/
├── src/
│   ├── strategies/
│   ├── factors/
│   ├── backtest/
│   ├── risk/
│   └── execution/
├── tests/
│   ├── unit/
│   └── integration/
├── docs/
│   ├── README.md
│   ├── ARCHITECTURE.md
│   └── API.md
├── scripts/
│   ├── backtest.py
│   ├── generate_signals.py
│   └── deploy.py
├── notebooks/
│   └── analysis/
├── pyproject.toml
└── Dockerfile
```

---

## 九、当前项目差距（按优先级）

| 必备内容 | 优先级 | 当前状态 |
|----------|--------|----------|
| 参数敏感性自动计算 | 🔴 **P0** | Risk Gate 黄线判断依赖此字段 |
| 多数据源 | ✅ 已完成 | yfinance, akshare, stooq, twelve_data |
| 更多策略 | ✅ 已完成 | DualMA, MeanReversion, ChannelBreakout, RegimeFilter |
| 过拟合检测 | ✅ 已完成 | walk_forward.py 已实现 |
| 交易执行 | ✅ 已完成 | longbridge, futu, paper broker |
| 因子库 | 🟢 P2 | 暂无 |
| 压力测试 | 🟢 P2 | 暂无 |
| 监控系统 | 🟢 P2 | 暂无 |

> **P0 = 必须立即处理** — 影响 Risk Gate 黄线判断

---

*持续更新中...*
