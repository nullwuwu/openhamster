# AGENTS.md

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
- Default assumption: the user wants the agent to complete the task end-to-end and keep advancing the current stage goal, not stop at analysis or wait for the next micro-instruction.
- Start each task by checking `git status`, then read the relevant code, docs, runtime status, and recent failures before making changes.
- Choose the next step from `docs/PROJECT_CONTEXT.md`, `docs/IMPLEMENTATION_STATUS.md`, `docs/DECISIONS.md`, current runtime health, visible blockers, and test gaps.
- Within the same theme, continue through implementation, verification, root-cause fixes, and the next obvious gap until the stage goal is meaningfully closed.
- Do not stop for minor uncertainty when the answer can be derived from the repository, existing patterns, local verification, or current runtime evidence.

## Long-Running Default
- Treat this repository as a long-running local system, not a sequence of isolated edits.
- At the start of a new thread or work round, perform the minimum operational sweep:
  `git status`
  service liveness
  `launchctl` or daemon status
  `/healthz`
  `/api/v1/command` runtime status
  recent logs and visible blockers
- Prioritize keeping the local runtime healthy before adding unrelated features.
- Default focus order is:
  1. Keep the local long-running baseline stable
  2. Fix blockers in research, paper, audit, and readiness loops
  3. Improve observability and remove misleading runtime states
  4. Extend product capability after the runtime is trustworthy
- If service health, scheduler rotation, runtime status semantics, fallback contamination, or key dashboard flows are degraded, fix those first.

## When To Ask
- Ask only when the task would overwrite or delete user work, needs unavailable external credentials or production access, or has multiple materially different product directions with no safe default.
- Do not ask for information that can be discovered from files, configs, tests, commands, or established repo patterns.
- Do not ask for step-by-step confirmation inside the same theme when there is a clear highest-value next action.

## Autonomy Boundaries
- Default autonomy mode is continuous advancement, not one isolated patch at a time.
- It is valid to chain together: detect issue, diagnose root cause, patch, verify, and continue to the next directly related gap.
- Stop and report when:
  the current stage goal is reached
  the next step would switch to a new theme or subsystem
  a real blocker requires user input
  external credentials, production access, or irreversible operations are required
- Do not expand indefinitely across unrelated themes. Finish the current theme, summarize outcomes, then surface the next best target.

## Verification Default
- Every completed task should include task-relevant validation before close-out.
- Prefer the smallest meaningful verification that proves the change works.
- If validation cannot run, say why in the final summary and in the commit message context.
- Final summaries should state the stage goal, what was completed, whether runtime health improved, and the next highest-value follow-up.

## Git Workflow
- After a complete task is implemented and validated, automatically create one non-interactive commit.
- Commit granularity is one complete user task, not one commit per tiny patch.
- Use a short task-oriented commit message such as `feat: ...`, `fix: ...`, `docs: ...`, `refactor: ...`, or `test: ...`.
- Do not amend prior commits unless explicitly requested.
- Do not auto-push, auto-rebase, or run destructive git commands.
- If unrelated local changes exist, read and avoid them; do not overwrite them unless the user explicitly asks.
