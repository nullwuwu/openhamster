# Mac mini 长期运行方案

## 目标
- 让 OpenHamster 在一台长期在线的 Mac mini 上稳定运行
- 只守护一个后端进程
- 前端使用生产构建后的静态文件，由 FastAPI 直接托管

## 当前部署形态
- OpenHamster API: `http://127.0.0.1:8000`
- Dashboard: 由同一个 FastAPI 进程直接托管
- 前端构建目录: `apps/web/dist`
- 调度器: 内嵌在 FastAPI lifespan 中，自动启动

## 首次部署
```bash
cd <repo-root>
python -m venv .venv
. .venv/bin/activate
pip install -e .[dev]
alembic upgrade head
bash scripts/build_frontend.sh
```

## 手动启动
```bash
cd <repo-root>
bash scripts/run_api.sh
```

启动后：
- Dashboard: `http://127.0.0.1:8000/`
- API: `http://127.0.0.1:8000/api/v1`
- 健康检查: `http://127.0.0.1:8000/healthz`

## launchd 守护
一键启动/重启：
```bash
cd <repo-root>
bash scripts/start_local_daemon.sh
```

这个脚本会：
- 重新构建前端
- 同步一份可由 `launchd` 访问的 runtime bundle 到 `~/.openhamster/local-runtime/current`
- 把数据库、缓存、日志保存在 `~/.openhamster/local-runtime/state`
- 重新渲染 `launchd` 配置
- 覆盖安装到 `~/Library/LaunchAgents`
- 重启 `com.openhamster.api`
- 做健康检查

如果服务已经在运行，它会重启到新代码；如果代码有更新，也会在同一次执行里完成重构建和重启。

手动分步方式：
1. 渲染本地 plist：
```bash
cd <repo-root>
bash scripts/render_launchd_plist.sh
```

2. 安装到用户级 LaunchAgents：
```bash
mkdir -p ~/Library/LaunchAgents
cp var/launchd/com.openhamster.api.plist ~/Library/LaunchAgents/com.openhamster.api.plist
launchctl unload ~/Library/LaunchAgents/com.openhamster.api.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.openhamster.api.plist
```

3. 常用命令：
```bash
launchctl kickstart -k gui/$(id -u)/com.openhamster.api
launchctl unload ~/Library/LaunchAgents/com.openhamster.api.plist
launchctl print gui/$(id -u)/com.openhamster.api
```

## 日志位置
- `~/.openhamster/local-runtime/state/logs/openhamster-api.out.log`
- `~/.openhamster/local-runtime/state/logs/openhamster-api.err.log`

推荐同时观察：
```bash
tail -f ~/.openhamster/local-runtime/state/logs/openhamster-api.out.log ~/.openhamster/local-runtime/state/logs/openhamster-api.err.log
```

## 更新流程
```bash
cd <repo-root>
git pull
. .venv/bin/activate
pip install -e .[dev]
alembic upgrade head
bash scripts/build_frontend.sh
launchctl kickstart -k gui/$(id -u)/com.openhamster.api
```

## 发布前本地检查
```bash
pytest tests -q
npm run build --prefix apps/web
npm run test:e2e --prefix apps/web -- --reporter=line
```

## 运行建议
- Mac mini 进入“永不自动睡眠”模式
- 不要长期跑 `vite dev`
- 把 `.env.local` 作为唯一密钥入口
- 保持 `~/.openhamster/local-runtime/state` 在本机磁盘上

## 当前边界
- 当前运行底座仍是 SQLite + runtime state SQLite
- 适合单机、低并发、长期 paper 运行
- 不适合现在就当作公网多用户服务
