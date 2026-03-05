# Research Log

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
