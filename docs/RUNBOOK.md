# GobyShrimp 运行手册

## 本地启动
```bash
pip install -e .[dev]
alembic upgrade head
gobyshrimp-api
npm install --prefix apps/web
npm run dev --prefix apps/web
```

默认入口：
- 前端：`http://127.0.0.1:5173`
- 后端：`http://127.0.0.1:8000`

## Mac mini 长期运行
- 生产模式不建议长期跑 `vite dev`
- 当前推荐方案：
  1. `bash scripts/start_local_daemon.sh`
  2. 由 FastAPI 直接托管 `apps/web/dist`
  3. `launchd` 负责自动拉起与重启
- 完整步骤见：
  - `docs/MAC_MINI_DEPLOYMENT.md`

## 本地密钥
推荐把密钥放在 `.env.local`：
- `MINIMAX_API_KEY`
- `FRED_API_KEY`

不要把密钥写进受版本控制的 YAML。

## Runtime Provider 切换
- dashboard 只切 `minimax / mock`
- 切换写入 runtime override
- 切换不会录入密钥
- 如果切到 `minimax` 但没有 `MINIMAX_API_KEY`，后端会拒绝切换
- provider 切换会触发一次新的 pipeline sync，并把 `last_trigger=runtime_provider_switch` 写入运行状态

## 持续运行状态
- `/api/v1/command` 现在会返回 `runtime_status`
- 关键字段：
  - `current_state = idle | running | degraded | stalled | failed`
  - `last_run_at`
  - `last_success_at`
  - `last_failure_at`
  - `consecutive_failures`
  - `expected_next_run_at`
  - `last_trigger`
- 当前 dashboard 已直接展示这些字段，用于判断系统是不是还在按预期持续运行
- 后端现在会在 lifespan 内启动真实周期调度：
  - `startup` 时立即跑一次
  - 之后按 `events.expected_sync_interval_minutes` 周期继续跑
  - 当前本地开发默认值在 `config/local.yaml` 中是 `5` 分钟

## 手动触发研究
- API:
  - `POST /api/v1/runtime/sync`
- dashboard:
  - `Run Now`
- 语义：
  - 如果当前 pipeline 已在运行，后端返回 `409`
  - 否则立即触发一次新的研究与治理同步

## 候选策略 ETA
- dashboard 现在会展示治理 ETA，而不是只显示阶段名
- 关键字段：
  - `governance_report.lifecycle.eta_kind`
  - `governance_report.lifecycle.estimated_next_eligible_at`
- 当前 ETA 语义：
  - `next_sync_window`：最早下一次研究周期可重新评审或晋级
  - `cooldown_window`：必须先等冷却结束
  - `quality_revalidation`：当前没有确定时间，要等质量改善
  - `review_pending`：当前要等暂停/回滚后的复核完成

## 宏观通道状态
- 当前只保留 `macro` 单通道
- provider 链：`FRED -> World Bank -> 最近可用上下文`
- 当 `FRED` 不可用时：
  - 系统会先尝试 `World Bank`
  - 如果第二真实源也不可用，再复用最近一次可用宏观上下文
  - 宏观通道状态会变成 `degraded`
  - command center 会显示降级信息
  - command center 会显示 `active_provider / provider_chain / reliability_score / reliability_tier`
  - 审计台会记录 `macro_provider_degraded` 和 `macro_provider_fallback_applied`
  - 新策略晋级会被治理规则阻断

## LLM / 宏观故障语义
- `ready`：可正常使用
- `mock`：手动切到样例模式
- `missing_key`：缺少密钥
- `auth_error`：鉴权失败
- `rate_limited`：限流或额度问题
- `network_error`：网络异常
- `provider_error`：上游返回异常
- `parse_error`：结构化输出解析失败
- `degraded`：宏观通道降级
- `primary_live`：主真实源正常
- `secondary_live`：第二真实源接管
- `last_known_context`：复用最近可用宏观上下文
- `provider_failed`：真实 provider 失败且未复用到最近可用上下文

## 研究链主流程
1. `sync_event_stream`
2. `sync_daily_event_digests`
3. `MarketAnalystAgent`
4. `StrategyAgent`
5. `ResearchDebateAgent`
6. `RiskManager LLM soft-score`
7. `deterministic evidence merge`
8. `RiskDecision`
9. `Candidate / Active materialization`

## 风控治理 v1.5
- 候选晋级必须满足：
  - 底线门禁通过
  - `final_score >= promote_threshold`
  - 冷却期结束
  - 相对当前活跃策略达到最小优势
  - 宏观通道未降级
- 活跃策略会根据模拟盘净值回撤触发：
  - `pause_active`
  - `rollback_to_previous_stable`

## 运营验收
- active strategy 当前会持续生成 `operational_acceptance`
- 关键字段：
  - `status = accepted | provisional | review_required`
  - `live_days`
  - `fill_rate`
  - `drawdown`
  - `failed_checks`
  - `pause_events_30d`
  - `rollback_events_30d`
  - `incident_free_days`
  - `operational_score`
- 当前默认验收门槛来自 `governance`：
  - `acceptance_min_days`
  - `acceptance_min_fill_rate`
  - `acceptance_max_drawdown`

## 运行验收报告
- API:
  - `GET /api/v1/ops/acceptance-report?window_days=30`
- 本地脚本:
  - `python scripts/generate_acceptance_report.py`
  - `python scripts/generate_acceptance_report.py --window-days 30 --format json`
- 报告当前固定输出四部分：
  - `quality`
  - `operations`
  - `macro`
  - `governance`
- 当前会给出：
  - `status = healthy | watch | attention`
  - `key_findings`
  - `next_actions`

## 长期质量统计
- `quality_report.track_record` 当前会提供：
  - `recent_total / recent_comparable / recent_replaceable`
  - `comparable_ratio / replaceable_ratio`
  - `stable_streak`
  - `trend`
  - `recent_30d_total / recent_30d_comparable`

## 常见排障
- command center 显示样例模式：
  - 检查 `MINIMAX_API_KEY`
  - 检查 runtime provider 是否仍是 `mock`
- command center 显示宏观通道降级：
  - 检查 `FRED_API_KEY`
  - 检查 `WORLD_BANK` 网络可达性
  - 检查外网可达性
  - 看 command center 的 `provider_chain / reliability_tier`
- 运行验收报告显示 `attention`：
  - 检查 `operations.status`
  - 检查 `macro.status`
  - 检查 `next_actions`
- 页面能打开但没有新提案：
  - 检查 `/api/v1/risk/decisions`
  - 检查 `/api/v1/audit/events`
  - 看是否命中了冷却期或晋级阻断原因
