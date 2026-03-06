# 技术决策记录

> 记录重大技术决策和原因，供未来参考

---

## 1. 为什么选择 Python 而非 Node.js/TypeScript

**决策**: 从 Node.js/TypeScript 迁移到 Python

**原因**:
- 量化生态碾压级优势：pandas, numpy, backtrader, zipline, quantconnect
- 现有 TS 代码量极少，沉没成本几乎为零
- MCP 官方 Python SDK 成熟可用
- Python 在金融行业的广泛使用意味着更多可复用资源

**时间**: 2026-03-05

---

## 2. 为什么选择 yfinance 而非 Twelve Data

**决策**: 使用 yfinance 作为数据源

**原因**:
- **免费** — yfinance 完全免费，适合研究和开发阶段
- **易用** — 简单的 API，集成方便
- **足够** — 回测阶段数据需求可以满足

**已知限制**:
- 存在请求限流问题（YFRateLimitError）
- 不适合高频调用

**后续计划**: 
- 实盘阶段切换到 Twelve Data 或 Alpha Vantage
- 添加数据缓存层减少重复请求

**时间**: 2026-03-05

---

## 3. 为什么放弃高频单策略

**决策**: 不做高频日内交易策略

**原因**:
- **摩擦成本结构性问题**: 高频策略的利润被交易成本侵蚀严重
  - 滑点: 5 bps
  - 佣金: 0.1%
  -买卖价差: 即使流动性好的标的也有成本
- **技术门槛**: 需要低延迟基础设施
- **容量有限**: 资金规模受限于市场流动性
- **监管风险**: 高频交易面临日益严格的监管

**结论**: 聚焦于低频趋势跟踪策略，更可持续

**时间**: 2026-03-05

---

## 4. 为什么选择 MiniMax 作为 LLM 供应商

**决策**: 集成 MiniMax M2.5

**原因**:
- **中文支持好**: 量化策略评审用中文更自然
- **成本**: 免费额度足够研究和开发使用
- **响应速度**: 可接受
- **OpenAI/Claude**: 因地制宜可选

**可扩展性**:
- LLM 客户端设计为可插拔
- 未来可轻松切换到其他供应商

**时间**: 2026-03-05

---

## 5. 为什么 Risk Gate 采用硬规则而非 LLM 判断

**决策**: Risk Gate 使用确定性硬规则

**原因**:
- **可解释性**: 硬规则结果明确可解释
- **可靠性**: 不受 LLM 幻觉影响
- **速度**: 计算即时，无需 API 调用
- **一致性**: 相同输入必然相同输出

**设计**:
- 硬规则 (Hard Gates): 一票否决 (NO_GO)
- 黄线 (Yellow Flags): 警告，可叠加
- 效用分 (Utility Score): 辅助决策

**时间**: 2026-03-05

---

## 6. 为什么限制辩论轮次为 2 轮

**决策**: `max_debate_rounds = 2`

**原因**:
- 防止死循环
- 避免过度辩论导致效率下降
- 2 轮足够暴露核心矛盾

**配置位置**: `config/policy.yaml`

**时间**: 2026-03-05

---

## 7. 为什么限制迭代次数为 3 次

**决策**: `max_iterations = 3`

**原因**:
- 防止无限迭代
- 3 次足够进行参数调整
- 超过则说明策略需要重新设计

**触发条件**: 达到上限时 `STOP_AND_NOTIFY_HUMAN`

**时间**: 2026-03-05

---

## 8. 为什么参数敏感性是 P0

**决策**: 参数敏感性自动计算优先级最高

**原因**:
- Risk Gate 黄线判断依赖此字段
- `param_sensitivity > 0.5` 触发黄线警告
- 未经敏感性验证的策略可能是过拟合

**后续实现**:
- 多参数网格搜索
- 计算不同参数下的收益方差
- 稳定性分析

**时间**: 2026-03-05

---

## 9. 为什么要求 4 个假设必须声明

**决策**: 回测必须声明 slippage, commission, tax, dividend_withholding

**原因**:
- 防止忽略真实交易成本
- 提高回测结果可信度
- 强制风控意识

**配置位置**: `config/policy.yaml` → `hard_gates.required_assumptions`

**时间**: 2026-03-05

## 9. 为什么引入 DataProvider 抽象层

**决策**: 创建 DataProvider 抽象层，实现可插拔的数据源

**背景**:
- yfinance 存在严重的请求限流问题 (YFRateLimitError)
- 直接调用 yfinance 导致回测流程不稳定

**原因**:
1. **解耦数据源与回测引擎** — BacktestEngine 不关心数据从哪里来
2. **可插拔设计** — 轻松切换到其他数据源 (Twelve Data, Alpha Vantage, etc.)
3. **自动降级** — 主数据源失败时自动 fallback 到备用源
4. **方便测试** — Mock DataProvider 可用于单元测试

**实现**:
```python
from quant_trader.data import DataProvider, TwelveDataProvider, YFinanceProvider

# 默认: TwelveData → 失败则 YFinance
engine = BacktestEngine()

# 自定义数据源
provider = TwelveDataProvider(api_key="xxx")
engine = BacktestEngine(data_provider=provider)
```

**当前实现**:
- **主数据源**: TwelveDataProvider (免费额度充足)
- **备用数据源**: YFinanceProvider (限流但可用)

**时间**: 2026-03-05

---

## 10. 为什么选择 AKShare + Stooq 作为港股数据源

**决策**: 使用 AKShare 为主数据源，Stooq 为备用

**原因**:
1. **AKShare 优势**:
   - 数据完整 (736行 vs 735行)
   - 提供丰富字段 (成交额/涨跌幅/换手率等)
   - 免费，无需 API Key
   - 国内数据源，数据质量较好

2. **Stooq 备用**:
   - 国际访问稳定
   - 字段简洁，适合基础回测

3. **原 yfinance 问题**:
   - Python 包被限流 (YFRateLimitError)
   - 解决方案：改用直接 HTTP API 调用

**已知限制**:
- AKShare 依赖国内数据源 (东方财富)，海外访问可能不稳定

**时间**: 2026-03-06

---

## 11. 为什么实现 Paper Broker 模拟交易

**决策**: 在实盘对接前先实现模拟交易层

**原因**:
1. **安全**: 实盘前充分验证策略
2. **隔离**: 模拟账户与实盘账户分离
3. **可追溯**: 完整的交易记录和绩效分析
4. **平滑过渡**: 模拟结果可直接对接实盘

**实现**:
```python
from quant_trader.paper import PaperBroker, PaperAccount

account = PaperAccount(initial_capital=1000000)
broker = PaperBroker(account)
# 模拟买入
broker.buy("2800.HK", quantity=1000, price=25.0)
```

**时间**: 2026-03-06

---

*按决策日期排序，持续更新...*
