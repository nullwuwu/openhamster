# GobyShrimp 实盘准入标准

## 目标
这份文档定义 GobyShrimp 从 `paper` 进入 `live` 之前必须满足的最低条件。

目的不是“尽快上实盘”，而是避免把一个只在短期看起来可用的系统，过早推向真实资金。

## 核心原则
- 实盘赚钱是最终目标
- 模拟盘只是实盘前的验证层，不是实盘替代品
- paper 晋级不等于 live 准入
- live 准入必须保留人工确认
- 任何一条硬门槛不满足，都不能上实盘

## 当前阶段定义
- `v1`：研究、治理、模拟盘、审计闭环成立
- `v2`：积累长期稳定性证据，形成实盘准入依据
- `v3`：在小资金、强风控、可回滚前提下进入受控实盘

当前仓库状态属于：
- `v1` 基本完成
- 正在向 `v2` 过渡

## 实盘准入总原则
只有在以下 5 类条件全部满足时，系统才具备 live 候选资格：
1. 策略质量条件
2. 模拟盘运营条件
3. 运行稳定性条件
4. 审计与可解释性条件
5. 人工审批条件

任何单项不满足：
- 不进入 live
- 保持在 `paper`
- 或退回 `candidate / review_required`

## 1. 策略质量条件

### 必须满足
- 候选策略已经连续通过足够长的样本外验证窗口
- 在近期观察窗口内，策略不只是“可比较”，而是稳定达到“可替换”或接近可替换
- 相对于当前 active / baseline，质量优势不是一次性噪声
- 策略不依赖明显缺失的历史数据窗口或异常数据点

### 建议准入口径
- 连续观察期：不少于 `20` 个交易日
- `stable_streak` 达到预设门槛
- `replaceable_ratio` 达到预设门槛
- `trend` 不为恶化
- 最近 `30` 天内不存在明显的质量塌陷

### 不允许的情况
- 只凭 1 到 3 次优异表现就上实盘
- 仅因为当前没有更好的 active 就放宽 live 准入
- 质量报告依赖 mock 候选或历史脏数据

## 2. 模拟盘运营条件

### 必须满足
- 策略已经在 paper 中稳定运行足够天数
- 持仓、订单、NAV、执行解释都能持续生成
- 模拟盘期间未频繁触发暂停或回滚
- 订单填充率、回撤、事件频率达到最低运营验收标准

### 建议准入口径
- `live_days` 不少于 `20`
- `operational_acceptance.status = accepted`
- `pause_events_30d` 低于阈值
- `rollback_events_30d = 0`
- `incident_free_days` 达到门槛
- `operational_score` 达到门槛

### 不允许的情况
- 仍处于 `provisional`
- 最近 30 天发生过回滚
- 运行中经常出现没有解释的平值 NAV 或缺失执行事件

## 3. 运行稳定性条件

### 必须满足
- scheduler 和 pipeline 可以连续运行
- runtime heartbeat 稳定
- 宏观链长期健康，降级和 fallback 在可接受范围内
- 数据源 freshness 和可靠性满足 live 要求

### 建议准入口径
- 最近 `30` 天 `consecutive_failures` 无持续升高趋势
- 最近 `30` 天无长时间 `stalled`
- `macro.health_score_30d` 达到门槛
- `degraded_count_30d` / `fallback_count_30d` 不超过上限
- 当前 active provider 不是长期运行在 fallback 上

### 不允许的情况
- 依赖频繁 fallback 才能保持运行
- runtime 状态经常卡在某个 stage
- 数据 freshness 经常超时

## 4. 审计与可解释性条件

### 必须满足
- 从 universe selection 到 strategy proposal，再到 risk decision 和 paper execution，整条链路都可追踪
- 当前 active 策略的每次状态变化都能回答“为什么发生”
- 净值变化或不变化，都能解释
- 当前 proposal、decision、execution 不含关键语义缺口

### 检查清单
- 有完整 `run_id / decision_id` 串联
- 有 universe selection 历史
- 有 blocked reasons、ETA、resume conditions
- 有 latest execution explanation
- 有 provider 状态与宏观状态语义

### 不允许的情况
- 当前 active 的因果链断裂
- 无法说明某次晋级、暂停、回滚的原因
- 依赖隐式人工记忆而不是系统内证据

## 5. 人工审批条件

### 必须满足
- live 启动必须保留人工确认
- 人工审批前需要检查：
  - 策略质量摘要
  - 最近 30 天模拟盘运营摘要
  - 宏观与 provider 健康摘要
  - 当前市场画像是否与策略风格一致

### 推荐审批格式
- 审批结论：
  - `approve_live_candidate`
  - `reject_live_candidate`
  - `keep_in_paper`
- 审批记录必须写入审计链

### 不允许的情况
- 自动把 `paper` 升成 `live`
- 没有人工结论就进入真实资金

## 建议的 live 启动顺序
1. 只允许单策略、单标的、小资金试运行
2. 启动时保留严格的止损和回滚规则
3. live 初期不做多策略并行
4. 先验证执行链与风控链，再追求收益扩张

## 当前还不满足的点
按当前仓库状态，以下几点仍然不足以支持实盘：
- 长周期质量样本还不够厚
- 模拟盘长期运营样本仍在积累
- provider 健康历史仍是 `v1`
- 当前默认运行底座仍是 SQLite
- 当前没有真正的 broker execution 层

## 结论
当前 GobyShrimp 的定位应当是：
- 值得持续运行的 `paper-first` 策略工厂

而不是：
- 已准备好自动实盘的交易系统

进入 live 的正确标准不是“感觉差不多了”，而是：
- 长期质量可信
- 模拟盘运营稳定
- 运行底座可靠
- 审计链完整
- 人工审批通过
