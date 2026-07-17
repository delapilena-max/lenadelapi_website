from __future__ import annotations

import sys
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from pipeline.presence import human_presence_prompt_plan_v1 as plan_module
from pipeline.prompting import lena_prompt_brain as prompt_brain
from tools import lena_presence_semantic_visual_review_v1 as semantic_review
from tools.lena_structured_visual_tool_v1 import (
    StructuredVisualImage,
    StructuredVisualToolError,
    call_anthropic_structured_visual_tool,
)
from tools.strategy import lena_human_presence_profile_v1 as lena_profile


def _compiled_plan() -> dict[str, object]:
    contract = lena_profile.build_lena_presence_contract()
    return plan_module.compile_human_presence_prompt_plan(contract, medium="still_image")


def _write_png(path: Path, color: str = "white") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (1, 1), color).save(path)
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valid_finding(plan: dict[str, object]) -> dict[str, object]:
    plan_values = semantic_review._still_image_plan_field_values(plan)
    return {
        "finding_code": "object_interaction_plan_contradiction",
        "category": "plan_contradiction",
        "plan_field_ref": "performance_actions.object_interaction",
        "plan_field_value": plan_values["performance_actions.object_interaction"],
        "observed_description": "The hand is not interacting with an object.",
        "confidence": "high",
        "image_index": 0,
        "advisory_only": False,
    }


def _monkeypatch_authority(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        semantic_review,
        "_load_model_authority",
        lambda: {
            "provider": semantic_review.SEMANTIC_PROVIDER_NAME,
            "approved_model": semantic_review.SEMANTIC_MODEL_NAME,
        },
    )


def _fake_semantic_call(payload: dict[str, object], captured: dict[str, object]):
    def _call(**kwargs: object) -> dict[str, object]:
        captured.update(kwargs)
        return payload

    return _call


def test_evaluate_hpe_semantic_still_image_presence_returns_aligned_result_without_path_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _compiled_plan()
    image_path = Path("C:/tmp/lena.png")
    captured: dict[str, object] = {}
    _monkeypatch_authority(monkeypatch)

    monkeypatch.setattr(
        semantic_review,
        "call_anthropic_structured_visual_tool",
        _fake_semantic_call(
            {
                "schema_version": semantic_review.SEMANTIC_RESPONSE_SCHEMA_VERSION,
                "findings": [],
            },
            captured,
        ),
    )

    result = semantic_review.evaluate_hpe_semantic_still_image_presence(
        plan=plan,
        image_path=image_path,
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
    assert captured["images"][0].role == "generated_candidate"
    assert str(image_path) not in captured["user_text"]
    assert semantic_review._request_binding_sha256(json.loads(captured["user_text"])) == result["semantic_result_provenance"]["request_binding_sha256"]


def test_evaluate_hpe_semantic_still_image_presence_returns_findings_present_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _compiled_plan()
    captured: dict[str, object] = {}
    _monkeypatch_authority(monkeypatch)

    monkeypatch.setattr(
        semantic_review,
        "call_anthropic_structured_visual_tool",
        _fake_semantic_call(
            {
                "schema_version": semantic_review.SEMANTIC_RESPONSE_SCHEMA_VERSION,
                "findings": [_valid_finding(plan)],
            },
            captured,
        ),
    )

    result = semantic_review.evaluate_hpe_semantic_still_image_presence(
        plan=plan,
        image_path=Path("C:/tmp/lena.png"),
        image_sha256="a" * 64,
        image_index=0,
        provider=semantic_review.SEMANTIC_PROVIDER_NAME,
        model=semantic_review.SEMANTIC_MODEL_NAME,
    )

    assert result["semantic_status"] == "findings_present"
    assert result["semantic_findings"][0]["finding_code"] == "object_interaction_plan_contradiction"
    assert semantic_review._request_binding_sha256(json.loads(captured["user_text"])) == result["semantic_result_provenance"]["request_binding_sha256"]


def test_evaluate_hpe_semantic_still_image_presence_binding_is_path_independent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _compiled_plan()
    _monkeypatch_authority(monkeypatch)
    captured: list[dict[str, object]] = []

    def fake_call(**kwargs: object) -> dict[str, object]:
        captured.append(kwargs)
        return {
            "schema_version": semantic_review.SEMANTIC_RESPONSE_SCHEMA_VERSION,
            "findings": [],
        }

    monkeypatch.setattr(semantic_review, "call_anthropic_structured_visual_tool", fake_call)

    image_a = tmp_path / "a" / "lena.png"
    image_b = tmp_path / "b" / "lena.png"
    sha_a = _write_png(image_a)
    sha_b = _write_png(image_b)

    result_a = semantic_review.evaluate_hpe_semantic_still_image_presence(
        plan=plan,
        image_path=image_a,
        image_sha256=sha_a,
        image_index=0,
        provider=semantic_review.SEMANTIC_PROVIDER_NAME,
        model=semantic_review.SEMANTIC_MODEL_NAME,
    )
    result_b = semantic_review.evaluate_hpe_semantic_still_image_presence(
        plan=plan,
        image_path=image_b,
        image_sha256=sha_b,
        image_index=0,
        provider=semantic_review.SEMANTIC_PROVIDER_NAME,
        model=semantic_review.SEMANTIC_MODEL_NAME,
    )

    assert result_a["semantic_result_provenance"]["request_binding_sha256"] == result_b["semantic_result_provenance"]["request_binding_sha256"]
    assert captured[0]["user_text"] == captured[1]["user_text"]
    assert str(image_a) not in captured[0]["user_text"]
    assert str(image_b) not in captured[1]["user_text"]


def test_evaluate_hpe_semantic_still_image_presence_binding_changes_with_image_sha(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _compiled_plan()
    _monkeypatch_authority(monkeypatch)
    captured: list[dict[str, object]] = []

    def fake_call(**kwargs: object) -> dict[str, object]:
        captured.append(kwargs)
        return {
            "schema_version": semantic_review.SEMANTIC_RESPONSE_SCHEMA_VERSION,
            "findings": [],
        }

    monkeypatch.setattr(semantic_review, "call_anthropic_structured_visual_tool", fake_call)

    image_path = tmp_path / "lena.png"
    sha_a = _write_png(image_path, color="white")
    result_a = semantic_review.evaluate_hpe_semantic_still_image_presence(
        plan=plan,
        image_path=image_path,
        image_sha256=sha_a,
        image_index=0,
        provider=semantic_review.SEMANTIC_PROVIDER_NAME,
        model=semantic_review.SEMANTIC_MODEL_NAME,
    )

    image_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"changed")
    sha_b = "b" * 64
    result_b = semantic_review.evaluate_hpe_semantic_still_image_presence(
        plan=plan,
        image_path=image_path,
        image_sha256=sha_b,
        image_index=0,
        provider=semantic_review.SEMANTIC_PROVIDER_NAME,
        model=semantic_review.SEMANTIC_MODEL_NAME,
    )

    assert result_a["semantic_result_provenance"]["request_binding_sha256"] != result_b["semantic_result_provenance"]["request_binding_sha256"]
    assert semantic_review._request_binding_sha256(json.loads(captured[0]["user_text"])) != semantic_review._request_binding_sha256(json.loads(captured[1]["user_text"]))


@pytest.mark.parametrize(
    "description",
    [
        "wrong person in the background",
        "Wrong person!",
        "composition looks off, maybe retry",
        "face quality seems bad; approval should be rejected",
    ],
)
def test_evaluate_hpe_semantic_still_image_presence_rejects_prohibited_observed_description(
    monkeypatch: pytest.MonkeyPatch,
    description: str,
) -> None:
    plan = _compiled_plan()
    _monkeypatch_authority(monkeypatch)

    monkeypatch.setattr(
        semantic_review,
        "call_anthropic_structured_visual_tool",
        lambda **kwargs: {
            "schema_version": semantic_review.SEMANTIC_RESPONSE_SCHEMA_VERSION,
            "findings": [{**_valid_finding(plan), "observed_description": description}],
        },
    )

    result = semantic_review.evaluate_hpe_semantic_still_image_presence(
        plan=plan,
        image_path=Path("C:/tmp/lena.png"),
        image_sha256="a" * 64,
        image_index=0,
        provider=semantic_review.SEMANTIC_PROVIDER_NAME,
        model=semantic_review.SEMANTIC_MODEL_NAME,
    )

    assert result["semantic_status"] == "error"
    assert result["semantic_error"]["error_code"] == "semantic_visual_review_invalid_payload"


def test_evaluate_hpe_semantic_still_image_presence_maps_rate_limit_to_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _compiled_plan()
    _monkeypatch_authority(monkeypatch)

    def fake_call(**_: object) -> object:
        raise StructuredVisualToolError("provider_rate_limit", "too many requests")

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
    assert result["semantic_error"]["error_code"] == "semantic_visual_review_rate_limit"


def test_structured_helper_maps_api_status_error(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    image_path = tmp_path / "bound.png"
    image_sha = _write_png(image_path)

    class FakeAPIError(Exception):
        pass

    class FakeAPIStatusError(Exception):
        def __init__(self, message: str, status_code: int = 500) -> None:
            super().__init__(message)
            self.status_code = status_code

    class FakeRateLimitError(Exception):
        pass

    class FakeOverloadedError(Exception):
        pass

    class FakeAPITimeoutError(Exception):
        pass

    class FakeAPIConnectionError(Exception):
        pass

    class FakeInternalServerError(Exception):
        pass

    class FakeConflictError(Exception):
        pass

    class FakeNotFoundError(Exception):
        pass

    class FakeRequestTooLargeError(Exception):
        pass

    class FakeUnprocessableEntityError(Exception):
        pass

    class FakeAPIResponseValidationError(Exception):
        pass

    class FakeAuthenticationError(Exception):
        pass

    class FakePermissionDeniedError(Exception):
        pass

    class FakeWorkloadIdentityError(Exception):
        pass

    class FakeBadRequestError(Exception):
        pass

    class FakeMessages:
        def create(self, **_: object) -> object:
            raise FakeAPIStatusError("server exploded", status_code=502)

    fake_module = SimpleNamespace(
        Anthropic=lambda **kwargs: SimpleNamespace(messages=FakeMessages()),
        APIError=FakeAPIError,
        APIStatusError=FakeAPIStatusError,
        RateLimitError=FakeRateLimitError,
        OverloadedError=FakeOverloadedError,
        APIConnectionError=FakeAPIConnectionError,
        InternalServerError=FakeInternalServerError,
        ConflictError=FakeConflictError,
        NotFoundError=FakeNotFoundError,
        RequestTooLargeError=FakeRequestTooLargeError,
        UnprocessableEntityError=FakeUnprocessableEntityError,
        APIResponseValidationError=FakeAPIResponseValidationError,
        AuthenticationError=FakeAuthenticationError,
        PermissionDeniedError=FakePermissionDeniedError,
        WorkloadIdentityError=FakeWorkloadIdentityError,
        BadRequestError=FakeBadRequestError,
        APITimeoutError=FakeAPITimeoutError,
    )
    monkeypatch.setitem(sys.modules, "anthropic", fake_module)

    with pytest.raises(StructuredVisualToolError) as exc_info:
        call_anthropic_structured_visual_tool(
            images=[StructuredVisualImage(path=image_path, sha256=image_sha, role="generated_candidate")],
            system_prompt="Return structured observations only.",
            user_text="{}",
            tool_name="submit_visual_observations",
            tool_schema={
                "type": "object",
                "properties": {"schema_version": {"type": "string"}, "findings": {"type": "array"}},
                "required": ["schema_version", "findings"],
                "additionalProperties": False,
            },
            provider=semantic_review.SEMANTIC_PROVIDER_NAME,
            model=semantic_review.SEMANTIC_MODEL_NAME,
            timeout_seconds=5.0,
            max_tokens=32,
        )

    assert exc_info.value.code == "provider_status_error"


@pytest.mark.parametrize(
    ("field_path", "mutator"),
    [
        ("viewer_relationship.awareness", lambda contract: contract["viewer_relationship"].__setitem__("awareness", "half_aware_glancing")),
        ("gaze_arc.start_focus", lambda contract: contract["gaze_arc"].__setitem__("start_focus", "already_on_camera")),
        ("expression_arc.peak_state", lambda contract: contract["expression_arc"].__setitem__("peak_state", "warm_smile")),
        ("performance_actions.object_interaction", lambda contract: contract["performance_actions"].__setitem__("object_interaction", "drink_or_cup")),
        ("movement_dynamics.weight_transfer", lambda contract: contract["movement_dynamics"].__setitem__("weight_transfer", "turn_with_hip_rotation")),
        ("sensual_presence.tier", lambda contract: contract["sensual_presence"].__setitem__("tier", "overt_sensual_presence")),
        ("body_presentation.framing_intent", lambda contract: contract["body_presentation"].__setitem__("framing_intent", "face_priority")),
        ("failure_indicators", lambda contract: contract.__setitem__("failure_indicators", ["dead_or_unfocused_eyes", "mannequin_pose"])),
    ],
)
def test_active_higgsfield_prompt_builder_tracks_presence_axes_and_ignores_failure_indicators(field_path: str, mutator) -> None:
    contract = lena_profile.build_lena_presence_contract()
    baseline_plan = plan_module.compile_human_presence_prompt_plan(contract, medium="still_image")
    baseline_package = prompt_brain.generate_higgsfield_prompt_package(
        "2026-07-17",
        "semantic-prompt-slot",
        "photo",
        presence_contract=contract,
        presence_plan=baseline_plan,
    )

    mutated_contract = json.loads(json.dumps(contract))
    mutator(mutated_contract)
    mutated_plan = plan_module.compile_human_presence_prompt_plan(mutated_contract, medium="still_image")
    mutated_package = prompt_brain.generate_higgsfield_prompt_package(
        "2026-07-17",
        "semantic-prompt-slot",
        "photo",
        presence_contract=mutated_contract,
        presence_plan=mutated_plan,
    )

    if field_path == "failure_indicators":
        assert mutated_package["image_prompt"] == baseline_package["image_prompt"]
    else:
        assert mutated_package["image_prompt"] != baseline_package["image_prompt"]
    assert "presence-failure avoidance" not in baseline_package["image_prompt"]
    assert "presence-failure avoidance" not in mutated_package["image_prompt"]
