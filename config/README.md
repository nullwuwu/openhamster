# Config Directory

当前仍在使用的仓库配置文件只有：

- [`base.yaml`](/Users/a1/.openclaw/workspace/projects/quant-trader/config/base.yaml)
  - 仓库级默认配置
- [`local.yaml`](/Users/a1/.openclaw/workspace/projects/quant-trader/config/local.yaml)
  - 本地开发覆盖配置，仅保留与 `base.yaml` 不同的非敏感项

不应放在 `config/` 里的内容：

- API key / token / password
  - 这些应进入 `.env.local`
- 运行时切换项
  - 这些应进入 runtime override
- 某次策略提案、风险决策、审计记录
  - 这些属于数据库中的运行对象，不是配置
