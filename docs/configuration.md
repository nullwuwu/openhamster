# 配置说明

## 覆盖顺序
配置覆盖顺序固定为：
`默认值 < config/base.yaml < config/local.yaml < .env < .env.local < 环境变量`

## 配置入口
统一配置入口为：`goby_shrimp.config.settings.AppSettings`

## 边界规则
配置边界单独收敛在：
- [`CONFIG_BOUNDARIES.md`](/Users/a1/.openclaw/workspace/projects/quant-trader/docs/CONFIG_BOUNDARIES.md)

`config/` 目录当前只保留主线配置文件，见：
- [`config/README.md`](/Users/a1/.openclaw/workspace/projects/quant-trader/config/README.md)

## 关键配置块
- `storage`
  - 数据库、日志、运行产物路径
- `data_source`
  - 价格和量能数据源
- `events`
  - 宏观 provider
- `llm`
  - LLM provider、model、temperature、output token 上限
- `strategy`
  - 基线策略与默认参数
- `hard_gates`
  - 风险经理不可覆盖底线
- `governance`
  - 晋级、冷却、暂停、回滚阈值
- `weights`
  - 确定性证据评分权重
- `integrations`
  - 当前启用的数据源与 LLM 凭据，由环境变量注入

## 来源追踪
可以使用以下接口查看字段最终来源：
- `goby_shrimp.config.get_settings_source_map()`
- `goby_shrimp.config.get_setting_source("storage.database_url")`

来源值目前可能是：
- `default`
- `base`
- `local`
- `env_file`
- `env`

## 本地密钥推荐方式
- 复制 [`.env.example`](/Users/a1/.openclaw/workspace/projects/quant-trader/.env.example) 为 `.env.local`
- 在 `.env.local` 中配置：
  - `MINIMAX_API_KEY=...`
  - `FRED_API_KEY=...`
- `.env` 和 `.env.local` 已被 `.gitignore` 忽略，不会入库

## 当前默认值
- `storage.database_url = sqlite:///var/db/goby_shrimp.db`
- `storage.log_path = var/logs/goby_shrimp.log`
- `hard_gates.max_drawdown = 0.15`
- `governance.promote_threshold = 75.0`
- `governance.cooldown_days = 5`
- `governance.acceptance_min_days = 7`
- `governance.acceptance_min_fill_rate = 0.60`
- `governance.acceptance_max_drawdown = 0.08`
- `events.macro_provider = fred`
- `integrations.fred_api_key` 用于 `FRED` 宏观 provider
- `llm.provider = minimax`
- `llm.model = MiniMax-M2.7`
- dashboard 可通过运行时配置在 `minimax / mock` 间切换 provider
- 宏观通道当前 provider 链为 `FRED -> World Bank -> 最近可用上下文`
- 宏观通道降级会阻断新的策略晋级，但不会让系统启动失败
- command center 会回显：
  - `active_provider`
  - `provider_chain`
  - `reliability_score`
  - `reliability_tier`
  - `freshness_hours`
  - `freshness_tier`
  - `health_score_30d`
  - `degraded_count_30d / fallback_count_30d / recovery_count_30d`
  - `runtime_status.current_state / last_run_at / last_success_at / last_failure_at / consecutive_failures / expected_next_run_at`
- `events.expected_sync_interval_minutes`
  - 用于计算 pipeline heartbeat 的 `expected_next_run_at`
  - 同时也是后台周期性研究调度的实际间隔
  - `base.yaml` 默认值：`60`
  - `local.yaml` 当前本地开发值：`5`
- 运行验收报告 API 会聚合：
  - `quality`
  - `operations`
  - `macro`
  - `governance`

## Prompt 契约
Prompt 文本和结构化输出提示已从业务代码拆出，当前集中在：
- [`src/goby_shrimp/prompts/market_analyst.py`](/Users/a1/.openclaw/workspace/projects/quant-trader/src/goby_shrimp/prompts/market_analyst.py)
- [`src/goby_shrimp/prompts/strategy_agent.py`](/Users/a1/.openclaw/workspace/projects/quant-trader/src/goby_shrimp/prompts/strategy_agent.py)
- [`src/goby_shrimp/prompts/research_debate.py`](/Users/a1/.openclaw/workspace/projects/quant-trader/src/goby_shrimp/prompts/research_debate.py)
- [`src/goby_shrimp/prompts/risk_manager_llm.py`](/Users/a1/.openclaw/workspace/projects/quant-trader/src/goby_shrimp/prompts/risk_manager_llm.py)

## Tushare 状态
Tushare 仍按现有 token 注入方式保留在统一 settings 中，本轮不扩展健康检查或真实 token 集成测试。

## 前端性能
- 前端当前已使用 Vite `manualChunks` 做首轮拆包
- 主要 vendor chunk 已拆为：
  - `vendor-vue`
  - `vendor-query`
  - `vendor-echarts`
  - `vendor`
