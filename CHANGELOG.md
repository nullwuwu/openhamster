# Changelog

All notable changes to OpenHamster are documented here.

## [0.2.0] - 2026-03-21

### Changed
- Renamed the project, package, CLI, deployment label, and public-facing product surfaces from `gobyshrimp` to `openhamster`.
- Updated the canonical public repository to `nullwuwu/openhamster` and aligned GitHub Pages links to `https://nullwuwu.github.io/openhamster/`.
- Reworked the public README and static Pages landing site around the OpenHamster brand and hamster-wheel narrative.

### Added
- Added a static GitHub Pages landing site under `site/` for product-style public presentation.
- Added standard open-source repository files:
  - `LICENSE`
  - `CONTRIBUTING.md`
  - `SECURITY.md`
  - `CODE_OF_CONDUCT.md`
  - issue and pull request templates

### Fixed
- Removed machine-specific absolute paths from public documentation.
- Removed local-only Playwright browser executable configuration from the frontend test setup.
- Updated release and deployment docs to match the current package, CLI, and launchd names.

### Removed
- Removed stale public release narrative that still described deleted MCP, broker, Telegram, and `policy.yaml` flows as active product history.

## [0.1.0] - 2026-03-07

### Added
- Established the current HK-only research-and-paper-trading baseline.
- Added the auditable dashboard and API surface for research, candidates, paper, audit, and runtime views.
- Added deterministic governance, local paper ledger support, and market-aware strategy generation through the unified LLM gateway.

### Constraints
- Paper execution is simulated locally and does not connect to broker execution.
- Automatic live trading is explicitly out of scope.
