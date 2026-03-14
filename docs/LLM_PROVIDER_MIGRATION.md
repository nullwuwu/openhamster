# LLM Provider Migration Principles

## 目标
在未来从 `MiniMax` 迁移到其他 LLM provider 时，保证三件事：
- 历史证据不丢
- 新旧 provider 可对照
- 切换风险可控

这份文档定义的是 **迁移治理规则**，不是单次切换操作手册。

## 适用范围
适用于 GobyShrimp 中所有直接影响研究结论或治理结论的 LLM 阶段：
- `market_analyst`
- `strategy_agent`
- `research_debate`
- `risk_manager_llm`

## 核心原则

### 1. 历史记录绝不覆写
以下对象一旦落库，只能追加解释，不允许因为 provider 迁移而覆写：
- `StrategyProposal`
- `RiskDecision`
- `AuditRecord`

原因：
- 历史 proposal 是当时的研究事实
- 历史 decision 是当时的治理事实
- 历史 audit 是当时的系统行为事实

## 2. Provider 元数据必须保留为分析字段
以下字段不是纯展示字段，必须继续保留：
- `source_kind`
- `provider_status`
- `provider_model`
- `provider_message`

原因：
- 后续需要区分“哪条策略是谁产出的”
- 切 provider 后，质量变化必须能归因
- `mock fallback` 必须能被识别，而不是混入真实 cohort

## 3. Provider 切换必须写审计事件
切换 provider 不应只是 runtime 配置变化，必须形成明确审计分界。

当前采用的事件语义：
- `llm_provider_switched`
- `provider_cohort_started`
- `provider_comparison_window_closed`

这三个事件共同定义：
- 旧 provider 的窗口何时结束
- 新 provider 的窗口何时开始
- readiness 历史和候选质量变化应从哪里开始解释

## 4. 新旧 Provider 只做并行对照，不直接改写活跃策略结论
迁移期内允许：
- 新 provider 生成 proposal
- 新 provider 在 candidate pool 中参与比较
- 在 paper 阶段逐步积累证据

迁移期内不允许：
- 因为“换了模型”就自动覆盖当前 active strategy 的结论
- 把 provider 切换视为质量已提升的证据

正确做法是：
- 让新 provider 在对照窗口里积累 proposal 质量、晋级率、fallback 率和 paper 分布
- 再决定是否收紧或放松治理阈值

## 5. `mock fallback` 必须严格隔离
`mock` proposal 仍然允许存在，但必须满足：
- 不伪装成真实 provider 结果
- 在 provider 对照摘要里单独计入 fallback contamination
- 不与真实 provider 的 proposal 质量口径混算

原因：
- fallback 的存在说明链路可靠性不足
- 如果把 fallback 和真实 provider 混在一起，质量对照会失真

## 6. Readiness 评估必须识别 provider 迁移
`live_readiness` 不能把“provider 切换导致的行为变化”误判成“市场变化”。

因此 readiness 证据层必须保留：
- 当前 provider cohort
- 上一 provider cohort
- 最近 proposal 质量差异
- 晋级率差异
- fallback 率差异

这部分目前是 **只读证据**，不是自动实盘开关。

## Provider Cohort 的定义
一个 provider cohort 指：
- 从某次 `provider_cohort_started` 开始
- 到下一次 provider cohort 开始之前
- 这段时间内由当前 runtime provider 主导产生的 proposal 窗口

对一个 cohort，当前关注的对照指标包括：
- `real_proposal_count`
- `avg_final_score`
- `promotion_rate`
- `fallback_rate`
- `promoted_symbol_distribution`

## 当前实现状态
当前已经落地：
- provider 切换写审计事件
- `command` 和 `audit` 展示 provider cohort 摘要
- readiness 证据层带 provider comparison
- 首页弱化 provider 展示，provider 证据保留在 `runtime / audit / research detail`

当前尚未落地：
- 双 provider 并行 shadow run
- 自动 provider A/B 对照实验
- provider 级别阈值自适应

## 推荐迁移流程
1. 切换 runtime provider，并记录 cohort 分界点
2. 保持一段对照窗口，只看只读证据，不改实盘判断口径
3. 对比：
   - proposal 质量
   - 晋级率
   - fallback 率
   - paper 中的策略分布
4. 若对照结果稳定，再决定是否把新 provider 作为默认主 provider
5. 切换完成后，仍保留旧 provider 的历史 cohort 供审计和回溯

## 不做的事
当前阶段明确不做：
- 因 provider 迁移自动进实盘
- 删除旧 provider 的 proposal 历史
- 将 provider 字段从数据库或审计中移除

## 验收要求
未来所有 provider 迁移实现，至少必须满足：
- provider 切换不会改写历史 proposal / decision
- fallback proposal 不会混入真实 provider 对照统计
- audit 能明确看出 provider 分界点
- readiness 趋势在 provider 切换前后可解释
