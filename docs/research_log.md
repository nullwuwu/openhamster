# Research Log

## [2026-03-06] 港股 2800.HK 数据源验证 (新增 AKShare & Stooq)

### AKShare 验证结果

**状态**: ✅ 可用

| 指标 | 值 |
|------|-----|
| 数据行数 | 736 行 |
| 日期范围 | 2023-03-07 ~ 2026-03-05 |
| 缺失值 | 0 行 |
| 数据源 | 东方财富 (eastmoney.com) |

**接口**: `ak.stock_hk_hist(symbol="02800", period="daily", ...)`

**优点**:
- 数据完整，无缺失值
- 免费，无需 API Key
- 返回丰富字段 (开盘/收盘/最高/最低/成交额/振幅/涨跌幅/涨跌额/换手率)

**缺点**:
- 依赖国内数据源 (东方财富)，海外访问可能不稳定
- 需要代理才能稳定访问

---

### Stooq 验证结果

**状态**: ✅ 可用

| 指标 | 值 |
|------|-----|
| 数据行数 | 735 行 |
| 日期范围 | ~2023-03 ~ 2026-03-05 |
| 缺失值 | 0 行 |

**接口**: `pandas_datareader.DataReader("2800.HK", "stooq", ...)`

**优点**:
- 数据完整，无缺失值
- 无需 API Key
- 国际数据源，海外访问稳定

**缺点**:
- 返回字段较少 (Open/High/Low/Close/Volume)

---

### 完整数据源对比

| 数据源 | 可用性 | 行数 | 数据完整性 | 备注 |
|--------|--------|------|------------|------|
| Yahoo Finance API | ❌ 被限流 | - | - | 429 Too Many Requests |
| Twelve Data (免费) | ❌ 不支持港股 | - | - | 需要 Pro 计划 |
| **AKShare** | ✅ 可用 | 736 | ✅ 100% | 推荐主力 |
| **Stooq** | ✅ 可用 | 735 | ✅ 100% | 备用首选 |

---

### 推荐方案

**主力数据源: AKShare**
- 数据更完整 (736 行 vs 735 行)
- 提供更多字段 (成交额/涨跌幅等)
- 国内数据源，数据质量较好

**备用数据源: Stooq**
- 国际访问稳定
- 字段简洁，适合基础策略回测

**下一步**:
- 实现 AKShareProvider 类
- 集成到 DataProvider 抽象层

### YFinanceProvider 验证结果

**状态**: ⚠️ YFinance Python 包被限流，无法直接使用

- yfinance Python 包在当前环境无法下载数据
- 错误: `YFRateLimitError('Too Many Requests. Rate limited')`
- 尝试 AAPL 等美股同样失败

**解决方案**: 使用 Yahoo Finance 直接 API 调用

通过直接 HTTP 请求 `query1.finance.yahoo.com/v8/finance/chart/2800.HK` 成功获取数据：

| 指标 | 值 |
|------|-----|
| 数据行数 | 735 行 |
| 日期范围 | 2023-03-07 ~ 2026-03-05 |
| 缺失值 | 仅 1 行 (约 0.14%) |
| 最大单日跌幅 | -13.4% (异常跳空) |
| 最大单日涨幅 | +6.05% |

**数据质量评估**:
- ✅ 数据完整性: 良好 (735/约756交易日 ≈ 97%)
- ⚠️ 存在 1 行 OHLCV 全为 NaN (需过滤)
- ⚠️ 存在单日 -13.4% 跳空，需检查是否为数据异常或真实行情

### TwelveDataProvider 验证结果

**状态**: ❌ 未配置 API Key

- 环境变量 `TWELVE_DATA_API_KEY` 未设置
- 需要从 https://twelvedata.com/ 注册获取免费 API Key
- 免费版: 每月 500 次 API 调用 (足够用于日线数据)

### 结论与建议

1. **YFinance 可用**: 通过直接 API 调用绕过了 Python 包的限流问题
2. **建议更新 YFinanceProvider**: 改用直接 HTTP 请求而非 yfinance 包
3. **Twelve Data 作为备用**: 待配置 API Key 后可作为备选数据源
4. **下一步**: 
   - 修改 YFinanceProvider 使用直接 API
   - 测试 Twelve Data Provider (需用户提供 API Key)

---

## [2026-03-05] Regime Filter 研究结论

### 结论

- **SPY**：DualMA + Regime Filter (ADX/MA斜率) 有效
  - 无 Filter: test_sharpe = -0.22, degradation = -39%
  - 有 Filter: test_sharpe = +0.16, degradation = +34%
  - 改进幅度: +0.38 ✅

- **QQQ**：Regime Filter 无效，参数不敏感（adx 5~25 全为负）
  - 原因：QQQ 为脉冲式拉升，不符合 MA斜率趋势定义
  - 结论：QQQ 暂不使用 Regime Filter

### 适用边界

DualMA + Regime Filter 适用于有"慢趋势"特征的标的（如 SPY），不适用于科技股脉冲行情（如 QQQ）。

### 下一步

针对 QQQ 设计均值回归策略，与 SPY DualMA 组合，实现策略互补。
