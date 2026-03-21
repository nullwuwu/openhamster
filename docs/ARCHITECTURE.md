# OpenHamster 架构

## 系统定位
OpenHamster 不是固定策略回测器，而是一个可审计的策略工厂。系统目标是让 LLM 参与市场感知与策略生成，同时把放行、执行、回滚与证据链固定为可追溯流程。

## Agent 团队
- `MarketAnalystAgent`
  - 输入：价格量能、技术指标、宏观日摘要、宏观事件流预览
  - 输出：`MarketSnapshot`
- `StrategyAgent`
  - 输入：`MarketSnapshot`、历史策略基线、候选池经验
  - 输出：`StrategyProposal`
  - 约束：只能输出 `StrategyDSL`，不能输出任意 Python 代码
- `ResearchDebateAgent`
  - 输入：策略提案与市场画像
  - 输出：`DebateReport`
- `RiskManagerAgent`
  - 输入：证据包、底线校验、LLM 软评分上下文
  - 输出：`reject / keep_candidate / promote_to_paper / pause_active / rollback_to_previous_stable`
- `ExecutionAgent`
  - 输入：已批准的风险决策
  - 输出：回测、walk-forward、模拟盘切换与订单执行结果
  - 约束：不使用 LLM，不拥有放行权
- `AuditService`
  - 输入：所有状态跃迁事件
  - 输出：`AuditRecord`
  - 约束：只记录，不做交易判断

## 运行链路
`proposal -> backtest -> walk-forward -> debate -> risk review -> promote`

后台周期调度已独立为运行模块：
- `src/openhamster/runtime/scheduler.py`
- `app.py` 只负责在 lifespan 中启动和停止调度器

系统也支持手动触发一次完整研究同步：
- `POST /api/v1/runtime/sync`

系统采用 `单活跃策略 + 候选池` 模式：
- 任一时刻只能有一个活跃模拟盘策略
- 新提案先进入候选池
- 只有通过底线、综合分和冷却期约束后，候选策略才能挑战当前活跃策略
- `governance_report.lifecycle` 现在会同时给出治理 ETA：
  - `eta_kind`
  - `estimated_next_eligible_at`

## 放行逻辑
### 3 条不可覆盖底线
- 数据完整性：默认要求至少 3 年可用日线样本
- 最大回撤：任一核心结果 `MaxDD > 15%` 直接拒绝
- 执行安全：仅允许 `long-only`、`no leverage`、`日级调仓`、现有执行层可表达规则

### 综合评分
- `deterministic evidence score = 70%`
- `llm judgment score = 30%`
- `final_score >= 75` 才允许进入模拟盘

### 宏观输入位置
- 辅助上下文层：进入 `MarketSnapshot`，帮助 LLM 感知市场
- 软评分层：进入 `llm judgment score`
- 不进入不可覆盖底线

## 数据模型
### 核心研究对象
- `StrategyProposal`
- `DebateReport`
- `EvidencePack`
- `RiskDecision`
- `CandidateStrategy`
- `ActiveStrategy`

## 策略插件
- 内置基线策略由 `src/openhamster/strategy/plugins.py` 统一声明
- `StrategyRegistry` 从插件目录构建，不再在工厂文件内硬编码注册清单
- `StrategyAgent` prompt 也直接读取同一份插件名列表，避免 prompt 与执行层漂移

### 宏观事件双轨
- `EventStream`
  - 原始事件级记录
  - 字段包括 `event_id`、`event_type`、`symbol_scope`、`published_at`、`source`、`title`、`body_ref`、`tags[]`、`importance`、`sentiment_hint`
- `DailyEventDigest`
  - 日级结构化摘要
  - 字段包括 `trade_date`、`market_scope`、`symbol_scope`、`macro_summary`、`event_scores`

## Dashboard IA
- `/command`
- `/candidates`
- `/research`
- `/paper`
- `/audit`

## 审计要求
所有关键状态跃迁都必须带：
- `run_id`
- `decision_id`
- `strategy_dsl_hash`
- `market_snapshot_hash`
- `event_digest_hash`
- `code_version`
- `config_version`
