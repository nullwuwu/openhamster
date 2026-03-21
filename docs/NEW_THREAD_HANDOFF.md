# 新线程接力说明

适用场景：
- 在新的 Codex 线程里继续推进 `OpenHamster`
- 希望快速恢复项目背景、长期规则与当前优先级

## 建议在新线程开头直接贴的内容
```text
这是 OpenHamster 项目。
请先阅读：
1. docs/PROJECT_CONTEXT.md
2. docs/PROJECT_OVERVIEW.md
3. docs/DECISIONS.md
4. docs/IMPLEMENTATION_STATUS.md

长期规则：
1. 优先中文回答，必要英文术语后面配中文解释
2. 当前阶段是 v2 证据层推进，不是自动实盘
3. 运行基线是 Mac mini + launchd + 本地 FastAPI
4. dashboard 定位是评审看板，不是强操作控制台
5. 最终目标是未来受控实盘赚钱

开始前先检查：
- git status
- 当前长期运行服务状态
- 最近文档基线
```

## 新线程应该优先知道的事实
- 项目名：`OpenHamster`
- 当前市场：`HK-only（仅港股）`
- 当前路线：`dynamic_hk（动态选股） + MiniMax + backtest admission（回测准入） + paper trading（模拟盘） + live readiness（实盘就绪度）`
- 当前长期运行基线：`Mac mini + launchd + 本地 FastAPI + 浏览器 dashboard`
- 当前不做：自动实盘、重型桌面壳、云端分布式部署

## 新线程开始后的最低检查项
1. `git status`
2. `launchctl list | grep openhamster`
3. `curl http://127.0.0.1:8000/healthz`
4. 打开最新的：
   - `docs/PROJECT_CONTEXT.md`
   - `docs/IMPLEMENTATION_STATUS.md`

## 推荐阅读顺序
1. `PROJECT_CONTEXT.md`
2. `PROJECT_OVERVIEW.md`
3. `DECISIONS.md`
4. `IMPLEMENTATION_STATUS.md`
5. 如任务相关，再看：
   - `RUNBOOK.md`
   - `MAC_MINI_DEPLOYMENT.md`
   - `LIVE_READINESS.md`
   - `V2_TRACKING.md`

## 什么时候需要额外补充口头上下文
以下情况建议在新线程再补一两句说明：
- 当前有未提交代码改动
- 当前长期运行服务正在执行关键 sync（同步）
- 这次任务和某个页面的临时观感取舍强相关
- 你希望保持某条新的长期固定规则，但还没写进文档

## 原则
新线程不应依赖旧会话记忆来“猜”项目方向。
应以：
- 代码
- 文档
- 运行状态
- 测试基线

作为真实上下文来源。
