from __future__ import annotations

from pathlib import Path

import pytest

from pipeline.presence import human_presence_prompt_plan_v1 as plan_module
from tools import lena_presence_semantic_visual_review_v1 as semantic_review
from tools.lena_structured_visual_tool_v1 import StructuredVisualToolError
from tools.strategy import lena_human_presence_profile_v1 as lena_profile


def _compiled_plan() -> dict[str, object]:
    contract = lena_profile.build_lena_presence_contract()
    return plan_module.compile_human_presence_prompt_plan(contract, medium="still_image")


def test_evaluate_hpe_semantic_still_image_presence_returns_aligned_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _compiled_plan()
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        semantic_review,
        "_load_model_authority",
        lambda: {
            "provider": semantic_review.SEMANTIC_PROVIDER_NAME,
            "approved_model": semantic_review.SEMANTIC_MODEL_NAME,
        },
    )

    def fake_call(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return {
            "schema_version": semantic_review.SEMANTIC_RESPONSE_SCHEMA_VERSION,
            "findings": [],
        }

    monkeypatch.setattr(semantic_review, "call_anthropic_structured_visual_tool", fake_call)

    result = semantic_review.evaluate_hpe_semantic_still_image_presence(
        plan=plan,
        image_path=Path("C:/tmp/lena.png"),
        image_sha256="a" * 64,
        image_index=0,
        provider=semantic_review.SEMANTIC_PROVIDER_NAME,
        model=semantic_review.SEMANTIC_MODEL_NAME,
        timeout_seconds=12.5,
    )

    assert result["semantic_status"] == "aligned"
    assert result["semantic_findings"] == []
    assert result["semantic_error"] is None
    assert result["semantic_result_provenance"]["provider"] == semantic_review.SEMANTIC_PROVIDER_NAME
    assert result["semantic_result_provenance"]["model"] == semantic_review.SEMANTIC_MODEL_NAME
    assert len(result["semantic_result_provenance"]["request_binding_sha256"]) == 64
    assert captured["tool_name"] == semantic_review.REQUEST_TOOL_NAME
    assert captured["provider"] == semantic_review.SEMANTIC_PROVIDER_NAME
    assert captured["model"] == semantic_review.SEMANTIC_MODEL_NAME
    assert captured["timeout_seconds"] == 12.5
    assert captured["max_tokens"] == semantic_review.REQUEST_MAX_TOKENS


def test_evaluate_hpe_semantic_still_image_presence_maps_timeout_to_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _compiled_plan()

    monkeypatch.setattr(
        semantic_review,
        "_load_model_authority",
        lambda: {
            "provider": semantic_review.SEMANTIC_PROVIDER_NAME,
            "approved_model": semantic_review.SEMANTIC_MODEL_NAME,
        },
    )

    def fake_call(**_: object) -> object:
        raise StructuredVisualToolError("provider_timeout", "timed out")

    monkeypatch.setattr(semantic_review, "call_anthropic_structured_visual_tool", fake_call)

    result = semantic_review.evaluate_hpe_semantic_still_image_presence(
        plan=plan,
        image_path=Path("C:/tmp/lena.png"),
        image_sha256="a" * 64,
        image_index=0,
        provider=semantic_review.SEMANTIC_PROVIDER_NAME,
        model=semantic_review.SEMANTIC_MODEL_NAME,
    )

    assert result["semantic_status"] == "error"
    assert result["semantic_error"]["error_code"] == "semantic_visual_review_timeout"
    assert "timed out" in result["semantic_error"]["error_message"]
