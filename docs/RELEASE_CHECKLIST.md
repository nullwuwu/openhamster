# OpenHamster 发布前检查清单

当前适用目标：`v0.2.0`

## 1. 产品边界确认
- 仓库首页和文档明确写出当前边界：
  - HK-only
  - dynamic HK universe selection
  - MiniMax live LLM path
  - macro-only context pipeline
  - local paper ledger, not broker execution
- README、`PROJECT_OVERVIEW.md`、`IMPLEMENTATION_STATUS.md` 叙事一致
- 不把未完成项写成“已支持”

## 2. 运行配置确认
- `.env.local` 已配置并且不入库：
  - `MINIMAX_API_KEY`
  - `FRED_API_KEY`
- `config/base.yaml` 与当前主线一致：
  - `universe.mode = dynamic_hk`
  - HK market profile 默认启用
- runtime provider 默认不是被旧测试污染成 `mock`

## 3. 后端基线
- `alembic upgrade head` 可成功执行
- 后端可正常启动：
  - `openhamster-api`
- 关键 API 可用：
  - `GET /api/v1/command`
  - `GET /api/v1/runtime/llm`
  - `POST /api/v1/runtime/sync`
  - `GET /api/v1/ops/acceptance-report`

## 4. 前端基线
- 前端可正常启动：
  - `npm run dev --prefix apps/web`
- 构建通过：
  - `npm run build --prefix apps/web`
- 首页能直接看到：
  - runtime heartbeat
  - current pipeline stage
  - universe selection
  - active strategy
  - latest paper execution explanation

## 5. 回归验证
- 全量回归：
  - `pytest tests -q`
- 当前基线目标：
  - `122 passed, 8 skipped` 或更高
- 构建基线：
  - `npm run build --prefix apps/web` passed

## 6. live 行为确认
- 当前 LLM provider 为：
  - `minimax`
- 当前 LLM 状态为：
  - `ready`
- 当前 HK universe selection 已返回真实候选
- 当前 paper ledger 至少已存在：
  - `orders`
  - `positions`
  - `daily_nav`
- 当前 `/paper` 页面能够解释：
  - 为什么调仓
  - 为什么未调仓
  - 为什么净值不变

## 7. 文案与发布页
- `README.md` 已按 GitHub 发布页风格整理
- 项目名、描述、边界、路线图清晰
- Dashboard 不残留明显错误市场叙事
- 文案不再混用旧名和旧执行链路

## 8. GitHub 发布动作
- 仓库名与定位一致
- GitHub Description 已更新
- 选择发布 tag：
  - 建议 `v0.2.0`
- Release Notes 使用 `docs/releases/v0.2.0.md`

## 9. 已知限制需在发布时明确
- SQLite 仍是当前默认交付路径，不是最终运行底座
- paper execution 是本地模拟，不是券商下单
- 宏观链仍是窄输入面，不含新闻和公告
- 长周期质量统计需要继续积累运行样本
