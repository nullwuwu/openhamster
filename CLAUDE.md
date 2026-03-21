# CLAUDE.md

This repository is `OpenHamster`, an auditable strategy factory.

## Current Product Shape
- Backend API: `src/openhamster/api`
- Frontend dashboard: `apps/web`
- LLM entrypoint: `src/openhamster/llm_gateway.py`
- Event pipeline: `src/openhamster/events`
- Runtime storage: `var/db`, `var/logs`, `var/cache`

## What Is In Scope
- Agent command dashboard
- Strategy proposals, risk decisions, audit records
- Event stream and daily event digest
- Backtest and experiment runs exposed through `/api/v1`
- Runtime LLM provider switching between `minimax` and `mock`

## What Is Not In Scope
- Old MCP server flow
- Old orchestrator / scheduler trading flow
- Old policy.yaml execution path
- Notification factory based legacy runtime

Those paths have been removed and should not be reintroduced.

## Run Commands
```bash
pip install -e .[dev]
alembic upgrade head
openhamster-api
npm install --prefix apps/web
npm run dev --prefix apps/web
```

## Config Rules
- Repository defaults: `config/base.yaml`
- Local non-secret overrides: `config/local.yaml`
- Secrets: `.env.local`
- Runtime switches: database-backed runtime overrides

See:
- `docs/configuration.md`
- `docs/CONFIG_BOUNDARIES.md`

## Guardrails
- Do not add new legacy compatibility layers
- Do not add secrets to tracked config files
- Prefer deleting stale product paths over preserving dead branches

## Execution Default
- Default assumption: the user wants the agent to complete the task end-to-end, not stop at analysis or wait for the next instruction.
- Start each task by checking `git status`, then read the relevant code and docs before making changes.
- Continue through implementation, verification, and result summary unless blocked by a real high-risk constraint.
- Do not stop for minor uncertainty when the answer can be derived from the repository, existing patterns, or local verification.

## When To Ask
- Ask only when the task would overwrite or delete user work, needs unavailable external credentials or production access, or has multiple materially different product directions with no safe default.
- Do not ask for information that can be discovered from files, configs, tests, commands, or established repo patterns.

## Verification Default
- Every completed task should include task-relevant validation before close-out.
- Prefer the smallest meaningful verification that proves the change works.
- If validation cannot run, say why in the final summary and in the commit message context.

## Git Workflow
- After a complete task is implemented and validated, automatically create one non-interactive commit.
- Commit granularity is one complete user task, not one commit per tiny patch.
- Use a short task-oriented commit message such as `feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`, or `test: ...`.
- Do not amend prior commits unless explicitly requested.
- Do not auto-push, auto-rebase, or run destructive git commands.
- If unrelated local changes exist, read and avoid them; do not overwrite them unless the user explicitly asks.
