# 策略知识层

## 这是什么
第一版 `strategy knowledge layer（策略知识层）` 是 OpenHamster 在 `baseline（基线策略）`、`market profile（市场画像）` 和 `governance（治理规则）` 之上新增的一层结构化策略常识。

它不是：
- 外部文章仓库
- 策略百科
- 可执行策略集合

它当前的职责是：
- 解释一条策略属于哪类方法
- 判断一条新 proposal（策略提案）是不是只是轻微换皮
- 判断这条提案是否踩中某类方法的常见失效模式
- 给 `research debate（研究辩论）`、`risk gate（风险门禁）`、`audit（审计）` 提供共同语言

## 第一版知识来源
第一版知识目录不依赖用户人工整理，也不接外部资料。

当前来源固定为：
1. 现有 `baseline（基线策略）` 的反向抽象
2. 现有 `market profile（市场画像）` 中已经隐含的市场适配知识
3. 现有 `governance rules（治理规则）` 中已经隐含的失效模式与参数约束

默认来源标记：
- `source_type = builtin`
- `source_refs = ["repo_baseline", "market_profile", "governance_rules"]`

## 当前包含的知识家族
第一版只包含 5 个知识家族：

- `trend_following（趋势跟随）`
- `mean_reversion（均值回归）`
- `breakout（突破）`
- `momentum_filter（动量过滤）`
- `volatility_filter（波动率过滤）`

每个知识家族都必须能映射到当前至少一个 baseline。

## 当前 baseline 映射
- `ma_cross（均线交叉）` -> `trend_following（趋势跟随）`
- `macd` -> `trend_following（趋势跟随）` + `momentum_filter（动量过滤）`
- `rsi` -> `mean_reversion（均值回归）` + `momentum_filter（动量过滤）`
- `mean_reversion（均值回归基线）` -> `mean_reversion（均值回归）`
- `channel_breakout（通道突破）` -> `breakout（突破）` + `volatility_filter（波动率过滤）`

`novel_composite（新组合）` 不作为知识家族。  
它必须显式声明自己借鉴了哪些 `knowledge_families（知识家族）`，否则不会被接受为有效 proposal。

## 知识条目字段
第一版知识条目字段固定为：

- `knowledge_id`
- `family_key`
- `label_zh`
- `summary_zh`
- `core_logic_zh`
- `supported_markets`
- `preferred_market_conditions`
- `discouraged_market_conditions`
- `common_indicators`
- `common_failure_modes`
- `parameter_priors`
- `risk_flags`
- `related_baselines`
- `novelty_expectation`
- `source_type`
- `source_refs`

这些字段的目标不是展示复杂术语，而是让系统能稳定地回答：
- 这条策略基于哪类方法
- 这类方法什么时候适合
- 什么时候容易失效
- 什么算合理变体，什么算只是换皮

## 当前如何参与生成与治理
### 生成前
`strategy_agent（策略生成）` 现在会先读：
- `strategy_knowledge（策略知识）`
- `knowledge_preferences（偏好知识家族）`
- `knowledge_discouraged（不鼓励知识家族）`
- `baseline_family_map（基线到知识家族映射）`

### 生成时
proposal 现在需要显式带出：
- `knowledge_families_used（使用了哪些知识家族）`
- `baseline_delta_summary（相对基线做了什么变化）`
- `novelty_claim（新颖性主张）`

### 研究和风控时
`research_debate（研究辩论）` 和 `risk gate（风险门禁）` 会检查：
- 当前方法是否适配当前市场
- 是否踩中常见失效模式
- 是否只是低新颖性的轻微参数改写
- 参数是否明显超出常见合理范围

当前知识层相关阻断语义：
- `knowledge_family_mismatch（知识家族不匹配）`
- `knowledge_failure_mode_risk（命中常见失效模式风险）`
- `knowledge_low_novelty（新颖性过低）`
- `knowledge_param_outlier（参数异常）`

默认规则：
- `knowledge_low_novelty（新颖性过低）` 不一定直接 `reject（拒绝）`
- 但它不能被视为强 challenger（挑战者）
- 如果同时回测也弱，就会进入 `reject（拒绝）` 或快速归档

## 当前如何进入证据与审计
当前这些字段已经进入：
- `evidence_pack（证据包）`
- `quality_report（质量报告）`
- `/research`
- `/research/:proposalId`
- `/audit`
- `/command` 的摘要视图

当前关键字段包括：
- `knowledge_families_used`
- `knowledge_fit_assessment`
- `knowledge_risk_flags`
- `knowledge_failure_mode_hits`
- `baseline_delta_summary`
- `novelty_assessment`

当前新增审计事件：
- `strategy_knowledge_applied（策略知识已应用）`
- `strategy_novelty_reviewed（策略新颖性已评审）`

## 当前明确不做
第一版明确不做：
- 外部网页原文直接进入 prompt
- 外部文章直接变 baseline
- 未审核知识直接参与门禁
- 单独新增一个“知识中心”重页面

当前知识层是现有研究、治理、审计页面的一部分，不新增新的主导航。

## 第二阶段留口
第二阶段可以做“外部资料 -> 候选知识条目 -> 审核 -> 内部知识模型”的流程。

但在那之前，知识输入必须继续满足：
- 来源可解释
- 结构可审计
- 不直接把外部文本变成策略

## 当前实现文件
- 核心目录：
  - [`../src/openhamster/strategy/knowledge.py`](../src/openhamster/strategy/knowledge.py)
- baseline 映射：
  - [`../src/openhamster/strategy/plugins.py`](../src/openhamster/strategy/plugins.py)
  - [`../src/openhamster/strategy/factory.py`](../src/openhamster/strategy/factory.py)
- 生成与治理接入：
  - [`../src/openhamster/prompts/strategy_agent.py`](../src/openhamster/prompts/strategy_agent.py)
  - [`../src/openhamster/prompts/research_debate.py`](../src/openhamster/prompts/research_debate.py)
  - [`../src/openhamster/prompts/risk_manager_llm.py`](../src/openhamster/prompts/risk_manager_llm.py)
  - [`../src/openhamster/api/services.py`](../src/openhamster/api/services.py)
