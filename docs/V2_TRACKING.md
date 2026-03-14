# V2 Tracking

## 目标
这份文档定义 GobyShrimp 进入 `v2` 后，未来 `2-4` 周应该持续跟踪什么，而不是继续盲目扩功能。

`v2` 的核心不是再做更多页面，而是：
- 持续运行
- 积累证据
- 用证据决定是否接近 live readiness

## 当前阶段判断
当前状态：
- `v1` 基本完成
- `v2` 已开始，但还在证据积累早期

因此当前所有跟踪都要回答两个问题：
1. 系统是否在稳定地产出可信证据
2. 这些证据是否在持续变好，而不是偶然好一次

## 未来 2-4 周的核心跟踪面

### 1. Provider Cohort
目标：看 `provider` 迁移是否真的改善了研究质量，而不是只是换了一个模型名字。

重点指标：
- `real_proposal_count`
- `avg_final_score`
- `promotion_rate`
- `fallback_rate`
- `promoted_symbol_distribution`

观察问题：
- 新 provider 的 proposal 是否更稳定
- 新 provider 的 fallback contamination 是否下降
- 新 provider 的晋级率是否改善
- provider 切换后的 readiness 变化是否可解释

## 2. Paper 运营
目标：看 active strategy 是否在 paper 中稳定运行，而不是偶尔有一条订单。

重点指标：
- `live_days`
- `operational_acceptance.status`
- `operational_score`
- `pause_events_30d`
- `rollback_events_30d`
- `incident_free_days`
- 最近执行解释是否持续合理

观察问题：
- paper 是否持续有执行语义，而不是只初始化后不动
- 非交易日、非交易时段逻辑是否稳定
- NAV / orders / positions 是否继续可解释

## 3. Live Readiness
目标：看系统离真实资金是否在缩短距离，而不是停留在“看起来完整”。

重点指标：
- `score`
- `status`
- `blockers`
- `next_actions`
- `dimensions`
- `linked_changes`

观察问题：
- readiness 是否有持续改善趋势
- 最近新增的 blocker 是市场原因、provider 原因，还是运营原因
- 阻断项是否在逐步减少

## 4. Runtime 稳定性
目标：证明本地 Mac mini 长期运行方案是可靠的。

重点指标：
- `process_uptime_seconds`
- `current_state`
- `current_stage`
- `consecutive_failures`
- `last_success_at`
- `startup_mode`
- `local_logs_available`

观察问题：
- launchd 管理下是否还能稳定重启
- runtime 是否频繁卡在单个 stage
- 日志链路是否稳定可查

## 5. Universe Selection
目标：看 HK 全市场自动选股是否稳定，而不是一天一个票、没有一致性。

重点指标：
- `selected_symbol`
- `selection_reason`
- `top_factors`
- `candidate_count`
- benchmark gap
- universe selection audit history

观察问题：
- 自动选股是否过度抖动
- 当前 affordability 过滤是否足够现实
- 相对于 `2800.HK` 基准，选出的标的是否真的更优

## 每周最少要回答的 6 个问题
1. 当前 provider cohort 是在变好还是变差？
2. 最近一周 paper 是否稳定运行，没有异常 pause / rollback？
3. readiness score 是在改善、持平还是恶化？
4. 当前最大的 blocker 是质量、运营、runtime 还是 explainability？
5. 自动选股是否稳定，还是切换过于频繁？
6. 当前证据是否支持继续停留在 paper，而不是讨论 live？

## 当前不追求的东西
在这个跟踪窗口里，明确不把以下内容作为优先目标：
- 新增更多页面
- 进入 broker live execution
- 引入第二市场
- 引入更复杂的 agent 团队

## 达到什么状态，才算 V2 有实质进展
满足以下情况，才算 `v2` 不是纸面推进：
- provider cohort 至少积累出一段可解释的历史趋势
- paper 至少有持续运营样本，而不只是初始化快照
- readiness 变化能被 universe / provider / macro / governance 证据解释
- runtime 在 Mac mini 上持续运行，没有明显脆弱点

## 下一步动作
当前最合理的动作顺序：
1. 保持系统长期运行
2. 每周查看一次 provider cohort / paper / readiness / runtime
3. 如果趋势不稳，再针对性调治理阈值和 UI 表达
4. 不在样本还薄时讨论 live execution
