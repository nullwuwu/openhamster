# Contributing to OpenHamster

Thanks for contributing. Keep changes aligned with the current product boundary: an auditable strategy factory, not a legacy trading runtime.

## Before You Start

- Read [README.md](README.md) and [docs/README.md](docs/README.md).
- Check `AGENTS.md` for repository guardrails.
- Do not reintroduce removed legacy paths such as old MCP server flow or old orchestrator scheduling.

## Local Setup

```bash
pip install -e .[dev]
alembic upgrade head
npm install --prefix apps/web
```

Backend:

```bash
openhamster-api
```

Frontend:

```bash
npm run dev --prefix apps/web
```

## Change Rules

- Prefer deleting stale paths over preserving dead branches.
- Keep secrets out of tracked config files.
- Put non-secret local overrides in `config/local.yaml`.
- Put secrets in `.env.local`.
- Keep runtime behavior changes auditable.

## Pull Requests

- Make PRs narrow and reviewable.
- Explain user-facing behavior changes and migration impact.
- Include tests when behavior changes.
- Mention any gaps if the current frontend or local environment prevents full verification.

## Areas That Need Extra Care

- `src/openhamster/api`
- `src/openhamster/llm_gateway.py`
- `src/openhamster/events`
- database migrations under `alembic`
- runtime storage behavior under `var/`
