#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from typing import Any

from goby_shrimp.api.db import SessionLocal, init_database
from goby_shrimp.api.services import build_acceptance_report


def _render_markdown(report: dict[str, Any]) -> str:
    quality = dict(report.get("quality", {}))
    operations = dict(report.get("operations", {}))
    macro = dict(report.get("macro", {}))
    governance = dict(report.get("governance", {}))
    track_record = dict(quality.get("track_record", {}))
    oos = dict(quality.get("oos_validation", {}))
    pool = dict(quality.get("pool_comparison", {}))

    lines = [
        "# GobyShrimp Acceptance Report",
        "",
        f"- Generated at: `{report.get('generated_at')}`",
        f"- Window days: `{report.get('window_days')}`",
        f"- Status: `{report.get('status')}`",
        f"- Strategy: `{report.get('strategy_title') or 'N/A'}`",
        "",
        "## Key Findings",
    ]
    findings = list(report.get("key_findings", []))
    if findings:
        lines.extend([f"- `{item}`" for item in findings])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Next Actions",
        ]
    )
    actions = list(report.get("next_actions", []))
    if actions:
        lines.extend([f"- `{item}`" for item in actions])
    else:
        lines.append("- None")

    lines.extend(
        [
            "",
            "## Quality",
            f"- Quality band: `{quality.get('quality_band')}`",
            f"- Track trend: `{track_record.get('trend')}`",
            f"- Stable streak: `{track_record.get('stable_streak')}`",
            f"- Recent comparable ratio: `{track_record.get('comparable_ratio')}`",
            f"- Recent replaceable ratio: `{track_record.get('replaceable_ratio')}`",
            f"- 30d comparable: `{track_record.get('recent_30d_comparable')}` / `{track_record.get('recent_30d_total')}`",
            f"- OOS pass rate: `{oos.get('walkforward_pass_rate')}`",
            f"- OOS windows: `{oos.get('passed_windows')}` / `{oos.get('total_windows')}`",
            f"- Relative to active: `{pool.get('relative_to_active')}`",
            "",
            "## Operations",
            f"- Acceptance status: `{operations.get('status')}`",
            f"- Live days: `{operations.get('live_days')}`",
            f"- Fill rate: `{operations.get('fill_rate')}`",
            f"- Drawdown: `{operations.get('drawdown')}`",
            f"- Incident-free days: `{operations.get('incident_free_days')}`",
            f"- Operational score: `{operations.get('operational_score')}`",
            f"- Pause events (30d): `{operations.get('pause_events_30d')}`",
            f"- Rollback events (30d): `{operations.get('rollback_events_30d')}`",
            "",
            "## Macro",
            f"- Provider: `{macro.get('active_provider') or macro.get('provider')}`",
            f"- Provider chain: `{', '.join(macro.get('provider_chain', []))}`",
            f"- Reliability score: `{macro.get('reliability_score')}`",
            f"- Reliability tier: `{macro.get('reliability_tier')}`",
            f"- Freshness: `{macro.get('freshness_hours')}` hours (`{macro.get('freshness_tier')}`)",
            f"- 30d health score: `{macro.get('health_score_30d')}`",
            f"- Degraded/fallback/recovery (30d): `{macro.get('degraded_count_30d')}` / `{macro.get('fallback_count_30d')}` / `{macro.get('recovery_count_30d')}`",
            "",
            "## Governance",
            f"- Phase: `{governance.get('phase')}`",
            f"- Next step: `{governance.get('next_step')}`",
            f"- Safety actions (30d): `{governance.get('safety_actions_30d')}`",
            f"- Fallback events (30d): `{governance.get('fallback_events_30d')}`",
            f"- Macro degraded (30d): `{governance.get('macro_degraded_30d')}`",
            "",
            "## Resume Conditions",
        ]
    )
    conditions = list(governance.get("resume_conditions", []))
    if conditions:
        lines.extend([f"- `{item}`" for item in conditions])
    else:
        lines.append("- None")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a GobyShrimp acceptance report.")
    parser.add_argument("--window-days", type=int, default=30, help="Rolling report window in days.")
    parser.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format.",
    )
    args = parser.parse_args()

    init_database()
    with SessionLocal() as db:
        report = build_acceptance_report(db, window_days=args.window_days)

    if args.format == "json":
        print(json.dumps(report, ensure_ascii=False, default=str, indent=2))
    else:
        print(_render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
