from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "pipeline" / "influencer_nodes" / "lena" / "autonomy_ladder_v1.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _level(levels: list[dict], number: int) -> dict:
    return next(level for level in levels if level["level"] == number)


def test_ladder_contract_parses_and_defines_six_levels() -> None:
    payload = _read_json(CONTRACT)

    assert payload["version"] == "v1.0.0"
    assert payload["schema_version"] == "lena_autonomy_ladder_v1"
    assert payload["node_name"] == "Lena"
    assert payload["node_role"] == "Node 1 of the autonomous media engine"
    assert payload["publish_freeze"]["active"] is True
    assert "publish paths remain frozen" in payload["publish_freeze"]["scope"]
    assert len(payload["levels"]) == 6
    assert [level["level"] for level in payload["levels"]] == [0, 1, 2, 3, 4, 5]


def test_ladder_contract_forbids_auto_approval_and_implicit_escalation() -> None:
    payload = _read_json(CONTRACT)

    assert payload["autonomy_rules"]["auto_approval_forbidden"] is True
    assert payload["autonomy_rules"]["implicit_escalation_forbidden"] is True
    assert payload["autonomy_rules"]["generation_approval_does_not_imply_posting_approval"] is True
    for level in payload["levels"]:
        assert "auto-approval" in set(level["forbidden_actions"])
        assert "implicit escalation" in set(level["forbidden_actions"])


def test_levels_zero_and_one_forbid_live_provider_and_queue_mutation() -> None:
    payload = _read_json(CONTRACT)

    for number in (0, 1):
        level = _level(payload["levels"], number)
        forbidden = set(level["forbidden_actions"])
        assert {
            "provider calls",
            "posting",
            "approval consumption",
            "claims",
            "receipts",
            "queue mutation",
            "auto-approval",
        } <= forbidden
        assert "publish packets" in forbidden


def test_levels_below_three_forbid_any_publish_action() -> None:
    payload = _read_json(CONTRACT)

    for number in (0, 1, 2):
        level = _level(payload["levels"], number)
        forbidden = set(level["forbidden_actions"])
        assert "posting" in forbidden or "publishing" in forbidden


def test_level_two_requires_explicit_approval_claim_receipt_qa_and_bounded_retry() -> None:
    payload = _read_json(CONTRACT)
    level = _level(payload["levels"], 2)

    assert level["enabled"] is True
    assert level["status"] == "active"
    assert level["approval_requirements"]["human_generation_approval_required"] is True
    assert level["approval_requirements"]["human_retry_approval_required"] is True
    assert level["approval_requirements"]["separate_posting_approval_required"] is True
    assert level["approval_requirements"]["per_slot_approval_required"] is True

    assert {
        "generation approval",
        "generation claim",
        "execution receipt",
        "QA disposition",
        "retry handoff",
        "retry approval when retrying",
    } <= set(level["required_artifacts"])
    assert {"publishing", "queue promotion", "auto-approval", "implicit escalation"} <= set(level["forbidden_actions"])


def test_levels_three_four_and_five_keep_posting_controlled_or_disabled() -> None:
    payload = _read_json(CONTRACT)
    level3 = _level(payload["levels"], 3)
    level4 = _level(payload["levels"], 4)
    level5 = _level(payload["levels"], 5)

    assert level3["future_placeholder"] is False
    assert level3["disabled_by_publish_freeze"] is True
    assert level3["disabled_reason"] == "publish_freeze_active"
    assert "human-approved posting preparation" in level3["allowed_actions"]
    assert "connector dispatch after explicit human approval" in level3["allowed_actions"]
    assert "autonomous posting" in set(level3["forbidden_actions"])
    assert level3["enabled"] is False
    assert level3["status"] == "frozen_real_mode"
    assert level3["required_artifacts"] == [
        "publish packet",
        "approved queue item",
        "connector payload",
        "post log or closure report",
        "manual publish approval",
    ]
    assert level3["approval_requirements"] == {
        "human_posting_approval_required": True,
        "per_item_or_batch_approval_required": True,
        "separate_from_generation_approval": True,
    }
    assert level3["failure_handling"][-1] == "never infer posting approval from generation approval"

    for level in (level4, level5):
        assert level["enabled"] is False
        assert level["status"] == "future_only"
        assert "future_placeholder" not in level
        assert "auto-approval" in set(level["forbidden_actions"])
        assert "implicit escalation" in set(level["forbidden_actions"])


def test_ladder_contract_does_not_reference_dirty_workspace_paths() -> None:
    serialized = json.dumps(_read_json(CONTRACT), sort_keys=True)
    assert "C:\\projects\\ai\\content_bot" not in serialized
    assert "C:/projects/ai/content_bot" not in serialized
    assert "content_bot_pr_clean" not in serialized
