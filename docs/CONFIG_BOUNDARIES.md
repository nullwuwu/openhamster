# 配置边界

## 目标
GobyShrimp 的配置必须回答 4 个不同问题：

1. 这台机器能不能连外部服务
2. 系统默认应该怎么运行
3. 当前运行时要不要临时切换行为
4. 某次研究/风控/执行到底产出了什么对象

如果这 4 类内容混在一起，结果就是：
- 密钥泄露风险上升
- dashboard 切换变成假开关
- 历史结果不可复现
- 无法判断某个值到底该在哪里改

## 四层规则

### 1. `.env` / `.env.local`
用途：机器级敏感信息和外部凭据。

适合放：
- `MINIMAX_API_KEY`
- `FRED_API_KEY`
- `TUSHARE_TOKEN`
- 未来数据库密码、SMTP 密码

不适合放：
- 策略参数
- 风控阈值
- dashboard 开关
- 当前活跃策略

判断标准：
- 这个值是否敏感
- 这个值是否因机器或账号不同而不同

### 2. `config/base.yaml` / `config/local.yaml`
用途：稳定的系统默认行为。

适合放：
- 默认数据源
- 默认 LLM model
- 风控底线默认值
- 调度时间
- 存储路径
- 执行边界
- 事件 provider 默认选择

不适合放：
- 密钥
- 高频切换的临时操作项
- 某次运行的研究结果

判断标准：
- 这个值是否应被纳入版本控制
- 这个值是否影响系统默认行为
- 这个值是否需要代码评审和变更记录

### 3. runtime overrides
用途：运行中的系统级操作开关。

当前适合放：
- `llm.provider = minimax | mock`

后续可以放：
- 某些 agent 的启停
- 某些非安全性的降级模式

不适合放：
- 密钥
- `max_drawdown` 这类硬红线
- 需要代码评审的长期行为

判断标准：
- 切换后是否应该立刻作用于新任务
- 切换后是否不要求改仓库文件
- 切换后是否仍然能通过审计记录追踪

### 4. 数据对象，不是配置
用途：记录系统产出的事实和决策。

包括：
- `StrategyProposal`
- `RiskDecision`
- `AuditRecord`
- `EventRecord`
- `DailyEventDigest`

这些内容不应该进入 `.env` 或 YAML，因为它们不是“默认值”，而是“运行结果”。

## 决策规则

### 应放进 `.env.local`
- API key
- token
- password
- account-specific secret

### 应放进 YAML
- 默认 provider
- 默认 model
- 风控阈值
- 调度策略
- 路径与持久化位置
- 默认事件源

### 应放进 runtime
- dashboard 需要切换且应立刻生效的系统开关
- 可以通过审计追踪的运行时模式切换

### 不应作为配置存在
- 某次策略提案的参数
- 某次决策的评分
- 某天的事件摘要
- 当前候选池内容

## 删除冗余配置的规则
以下情况应优先删除，而不是继续保留：

1. 与 `base.yaml` 完全相同，只是重复出现在 `local.yaml`
2. 当前没有任何运行路径读取
3. 仅为历史兼容保留，但已不再属于当前产品目标
4. 明显属于“数据对象”却被误放在配置里

## 当前结论

### 应保留在 `.env.local`
- `MINIMAX_API_KEY`
- `FRED_API_KEY`
- 其他供应商密钥

### 应保留在 YAML
- `llm.model`
- `events.*_provider`
- `hard_gates.*`
- `execution_rules.*`
- `storage.*`

### 应保留在 runtime
- `llm.provider`

### 已开始收敛
- `config/local.yaml` 中与 `base.yaml` 完全重复的项已删除
- dashboard 不再承担密钥管理职责
- LLM provider 切换已收敛为 runtime override
- 当前无人读取的配置项已删除：`events.enabled`、`events.digest_window_days`、`events.stream_limit`、`weights.adjust_range`、`limits.on_max_reached`
- 旧 `policy*.yaml`、`paper_trading*.yaml`、MCP/Orchestrator 相关旧链路文件已从仓库主路径删除
- 旧 `broker/storage/reconciler` 模块、对应测试，以及 OpenAI/Longbridge 兼容配置已从主线删除
