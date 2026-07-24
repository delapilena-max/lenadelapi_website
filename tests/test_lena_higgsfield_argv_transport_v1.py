"""Windows argv-transport regression tests.

Root cause proven in production by job e7310322 (2026-07-24): the Higgsfield
CLI on PATH is `higgsfield.CMD`, a batch shim that forwards arguments with
`%*`. Batch `%*` expansion truncates a multiline argument at its first
newline and drops every argument positioned after it. A 3514-char prompt
containing 7 newlines reached the provider as exactly 695 chars -- the SHA of
the prompt cut at its first newline -- and --soul-id / --aspect_ratio /
--quality never reached the job, so the Lena Soul was never attached.

These tests are offline: they spawn a local argv-capture probe, never the
provider, and never spend credits.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

import pipeline.higgsfield_lena_api_executor as executor

SOUL_ID = "79119c27-64fc-47f8-9ff3-c174d12932aa"

MULTILINE_PROMPT = (
    "[Subject]: Lena (Magdalena Delapi) first section with real length.\n"
    "[Subject Presence]: second section.\n"
    "[Action]: third section.\n"
    "[Environment]: fourth section.\n"
    "[Technical]: fifth section ends here."
)

ARGV_PROBE = """import json, sys
sys.stdout.write(json.dumps(sys.argv[1:]))
"""


def _capture_child_argv(argv_tail: list[str], tmp_path: Path) -> list[str]:
    """Spawn a real child process the same way the executor does and return
    the argv the child actually received."""
    probe = tmp_path / "argv_probe.py"
    probe.write_text(ARGV_PROBE, encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(probe), *argv_tail],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_multiline_prompt_and_trailing_flags_survive_the_subprocess_boundary(tmp_path: Path) -> None:
    """The whole point: every newline and every flag must arrive intact."""
    argv = executor.build_provider_argv(MULTILINE_PROMPT, SOUL_ID)
    received = _capture_child_argv(argv[1:], tmp_path)

    prompt_received = received[received.index("--prompt") + 1]
    assert prompt_received == MULTILINE_PROMPT
    assert prompt_received.count("\n") == MULTILINE_PROMPT.count("\n") == 4
    assert len(prompt_received) == len(MULTILINE_PROMPT)
    assert (
        hashlib.sha256(prompt_received.encode("utf-8")).hexdigest()
        == hashlib.sha256(MULTILINE_PROMPT.encode("utf-8")).hexdigest()
    )

    assert received[received.index("--soul-id") + 1] == SOUL_ID
    assert received[received.index("--aspect_ratio") + 1] == "9:16"
    assert received[received.index("--quality") + 1] == "2k"


def test_launcher_never_resolves_to_a_batch_shim() -> None:
    """A .CMD/.BAT launcher corrupts argv and must never be returned."""
    launcher = executor.resolve_provider_launcher()

    assert launcher, "launcher must not be empty"
    assert Path(launcher[0]).suffix.lower() not in {".cmd", ".bat"}


def test_launcher_fails_closed_when_only_an_unusable_shim_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the shim cannot be resolved to a real executable, refuse to run --
    never silently fall back to the argv-corrupting shim."""
    shim = tmp_path / "higgsfield.CMD"
    shim.write_text("@ECHO off\n", encoding="utf-8")
    monkeypatch.setattr(
        executor.shutil,
        "which",
        lambda name: str(shim) if name == executor.HIGGSFIELD_CLI_BINARY else None,
    )

    with pytest.raises(executor.ProviderCallError) as excinfo:
        executor.resolve_provider_launcher()

    assert excinfo.value.stage == "provider_launcher_unsafe"
    assert excinfo.value.subprocess_start_attempted is False
    assert excinfo.value.provider_submission_may_have_occurred is False


def test_prompt_is_last_argument_so_flags_cannot_be_swallowed() -> None:
    argv = executor.build_provider_argv(MULTILINE_PROMPT, SOUL_ID)

    assert argv[-2] == "--prompt"
    assert argv[-1] == MULTILINE_PROMPT


@pytest.mark.parametrize("placeholder", ["<FULL PROMPT>", "<redacted, len=3514>", "<prompt>"])
def test_placeholder_prompt_is_rejected_before_spend(placeholder: str) -> None:
    argv = ["node", "higgsfield.js", "generate", "create", "--prompt", placeholder]

    with pytest.raises(executor.ProviderCallError) as excinfo:
        executor._require_prompt_survives_argv_boundary(argv, MULTILINE_PROMPT)

    assert excinfo.value.stage == "prompt_argv_placeholder_rejected"
    assert excinfo.value.subprocess_start_attempted is False


def test_truncated_prompt_at_the_boundary_is_rejected_before_spend() -> None:
    """Exactly the production failure: prompt cut at its first newline."""
    truncated = MULTILINE_PROMPT.split("\n")[0]
    argv = ["node", "higgsfield.js", "generate", "create", "--prompt", truncated]

    with pytest.raises(executor.ProviderCallError) as excinfo:
        executor._require_prompt_survives_argv_boundary(argv, MULTILINE_PROMPT)

    assert excinfo.value.stage == "prompt_argv_length_mismatch"
    assert excinfo.value.subprocess_start_attempted is False
    assert excinfo.value.provider_submission_may_have_occurred is False


def test_same_length_but_altered_prompt_is_rejected_before_spend() -> None:
    altered = MULTILINE_PROMPT[:-1] + "X"
    argv = ["node", "higgsfield.js", "generate", "create", "--prompt", altered]

    with pytest.raises(executor.ProviderCallError) as excinfo:
        executor._require_prompt_survives_argv_boundary(argv, MULTILINE_PROMPT)

    assert excinfo.value.stage == "prompt_argv_sha_mismatch"


def test_exact_prompt_passes_the_boundary_guard() -> None:
    argv = ["node", "higgsfield.js", "generate", "create", "--prompt", MULTILINE_PROMPT]

    executor._require_prompt_survives_argv_boundary(argv, MULTILINE_PROMPT)


def test_missing_prompt_argument_is_rejected_before_spend() -> None:
    argv = ["node", "higgsfield.js", "generate", "create", "--soul-id", SOUL_ID]

    with pytest.raises(executor.ProviderCallError) as excinfo:
        executor._require_prompt_survives_argv_boundary(argv, MULTILINE_PROMPT)

    assert excinfo.value.stage == "prompt_argv_binding_missing"
