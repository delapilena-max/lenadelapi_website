from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import lena_standing_autonomy_policy_v1 as standing_autonomy  # noqa: E402


def _report() -> dict[str, Any]:
    policy_result = standing_autonomy.validate_policy_artifact(
        standing_autonomy.default_policy_path()
    )
    policy = policy_result["artifact"]
    summary = standing_autonomy.summarize_controlled_qa_mode(policy)
    controlled = policy.get("controlled_photo_autonomy")
    return {
        "ok": (
            summary["configured_autonomous_qa_mode"]
            == standing_autonomy.AUTONOMOUS_QA_MODE
            and summary["autonomous_external_visual_provider_required"] is False
            and summary["external_visual_diagnostics_enabled"] is False
            and summary["human_review_required_for_autonomous_operation"] is False
            and not summary["missing_required_local_safeguards"]
        ),
        "report_type": "lena_autonomous_qa_mode_validation",
        "policy_path": str(policy_result["path"]),
        "policy_sha256": policy_result["sha256"],
        "controlled_photo_autonomy_enabled": bool(
            isinstance(controlled, dict) and controlled.get("enabled") is True
        ),
        "configured_autonomous_qa_mode": summary["configured_autonomous_qa_mode"],
        "autonomous_external_visual_provider_required": summary[
            "autonomous_external_visual_provider_required"
        ],
        "external_visual_diagnostics_enabled": summary[
            "external_visual_diagnostics_enabled"
        ],
        "external_visual_diagnostic_authorization_required": summary[
            "external_visual_diagnostic_authorization_required"
        ],
        "human_review_mode": summary["human_review_mode"],
        "human_review_required_for_autonomous_operation": summary[
            "human_review_required_for_autonomous_operation"
        ],
        "deterministic_local_checks_present": summary[
            "deterministic_local_checks_present"
        ],
        "missing_required_local_safeguards": summary[
            "missing_required_local_safeguards"
        ],
    }


def main() -> int:
    try:
        report = _report()
    except standing_autonomy.StandingAutonomyPolicyError as exc:
        report = {
            "ok": False,
            "report_type": "lena_autonomous_qa_mode_validation",
            "error_code": exc.code,
            "error_detail": exc.detail,
        }
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
