# Operator Runbook

**Visibility:** Internal
**Document type:** Internal technical draft. No legal review required.
**Status:** First draft. Every command below was verified to exist (by CLI-argument inspection) in
`origin/main` at commit `94da3c3d` on 2026-07-16. Verify current flag names against `--help` before
running, since this pipeline changes frequently.
**Owner:** Engineering lead / accountable operator (names to be assigned)
**Review cadence:** On every change to any script named below; otherwise monthly.

## Purpose

Give the accountable operator the exact, safe command sequence for generation (recommendation
through a bounded live attempt) and for publish-preparation tooling, clearly marking what currently
fails closed by design.

## Intended Audience

Internal operators only.

## Scope

Covers command sequences and their safety classification. Does not cover the underlying authority
model (System Architecture document, Customer-under-NDA visibility) or incident handling (Incident
Response plan, Internal visibility).

## Phase 1 — Recommendation to a Reconciled, Approvable Handoff

Report-only: no provider call, no spend, no approval creation, no queue mutation.

| Step | Command | Effect |
|---|---|---|
| 1 | `python tools/strategy/lena_build_post_outcome_learning_state_v1.py --date <date>` | Writes the learning-state artifact. |
| 2 | `python tools/strategy/lena_recommend_next_generation_step_v1.py --date <date> --learning-artifact-path <path from step 1>` | Writes the recommendation artifact. |
| 3 | `python tools/strategy/lena_build_autonomous_generation_queue_dryrun_v1.py --date <date>` | Writes the queue dry-run artifact. |
| 4 | `python tools/strategy/lena_pre_generation_candidate_gate_v1.py --date <date> --required-recipe-id <recommended recipe from step 2>` | Selects one executable candidate, pinned to the recommendation. Run exactly once per date. |
| 5 | `python tools/strategy/lena_build_generation_reconciliation_v1.py --date <date>` (if step 2 and step 4 disagree) | Produces a reconciliation artifact describing the disagreement. |
| 6 | `python tools/strategy/lena_record_generation_reconciliation_decision_v1.py ...` (per its own CLI contract) | Records an explicit operator decision. **Authorizes handoff preparation only** — does not authorize generation or publishing, and as of this writing is not yet consumed by step 7. |
| 7 | `python tools/strategy/lena_build_next_live_image_handoff_v1.py --date <date>` | Builds the handoff. Currently enforces the recommendation/candidate equality check directly; does not yet reference the reconciliation-decision artifact from step 6 (integration in progress). |

## Phase 2 — Scoped Generation Approval and One Bounded Attempt

| Step | Command | Effect |
|---|---|---|
| 8 | Record a generation approval via `tools/lena_higgsfield_generation_approval_v1.py` / `tools/lena_record_higgsfield_generation_approval_v1.py` per their own CLI contracts | **Real authorization to spend provider credit.** Confirm the handoff is correct before running. |
| 9 | `python pipeline/higgsfield_lena_api_executor.py --handoff-artifact <path>` (no `--live`) | Dry-run validation. Safe. |
| 10 | `python pipeline/higgsfield_lena_api_executor.py --handoff-artifact <path> --live` | **Spends provider credit.** Requires a valid, unexpired approval bound to this exact handoff. |

## Phase 3 — Quality Review

| Step | Action | Effect |
|---|---|---|
| 11 | Fill in the QA scaffold for the rendered slot via `pipeline/qa/lena_photo_qa.py` / `tools/lena_photo_qa_disposition_v1.py` | Produces the fixed-checklist verdict (identity fidelity, face realism, skin realism, wardrobe class fidelity, public-scene clothing continuity, outerwear-underlayer correctness, body-shape continuity, hands/anatomy sanity, environment realism, caption-scene coherence, plus a scene-compliance field). Confirm you are scoring the current render, not a stale verdict from an earlier attempt on the same slot. |

## Phase 4 — Publish Preparation (Currently Blocked by Design)

| Step | Command | Effect |
|---|---|---|
| 12 | `python tools/lena_publish_packet_director_generate_v2_4.py --date <date>` | Builds publish packets from QA-passed renders. |
| 13 | `python tools/lena_build_approved_publish_queue_v2_8.py --date <date> [--platforms <list>] [--replace]` | Builds the approved-publish queue. **Calls the autonomy-tier gate directly at the start of `main()`, requesting the human-approved-posting-preparation tier. That tier is currently disabled, so this command fails closed today, printing `{"ok": false, ...}` and returning a nonzero exit** — this is expected, correct behavior, not a bug to work around. |
| 14 | `python tools/lena_autopublish_approved_queue_v2_8.py --date <date> [--platforms <list>] [--dry-run\|--live] [--limit N]` | Publishes from the approved queue. Has both `--dry-run` and `--live` modes. Cannot meaningfully run today because step 13 does not produce an approved queue while the relevant autonomy tier is disabled. |

## Non-Negotiable Operator Rules

- Never hand-edit an artifact JSON to make a fail-closed check pass.
- Never run the candidate gate (step 4) more than once per date without clearing the prior selected
  artifact.
- Never treat a reconciliation decision (step 6) as authorizing anything beyond handoff preparation.
- Never assume the publish tier is enabled; step 13 will fail closed while it isn't, which is
  correct.

## Responsibilities

- **Operator:** executes this sequence exactly; escalates any unexpected fail-closed result rather
  than working around it.
- **Engineering:** keeps this runbook's commands in sync with the real CLI contracts.

## Controls

Every "safe" classification above is enforced by code-level gates, not operator discipline alone.

## Procedures

See Phase 1–4 tables above.

## Audit Evidence

Every command above corresponds to a file confirmed present in `origin/main` at commit `94da3c3d`;
CLI flags for the Phase 4 tools were confirmed by direct inspection of their `argparse` definitions.

## Exceptions

- Exact CLI flags for the reconciliation-decision recorder and the generation-approval tools should
  be confirmed against `--help` output before running, since flag names change across commits.
- Phase 4, step 13's fail-closed behavior was confirmed by reading the code path directly
  (`autonomy_ladder.assert_allowed(..., level=3, ...)`), not by actually running the command against
  live operational state — this document does not assert having executed step 13 for real.

## Version and Review Cadence

- **Version:** 0.3 — replaced an entirely fictional Phase 3 "publish-gate" command sequence (based on
  tool names — a queue-promotion tool, a two-phase approval recorder, a clean-export verifier — that
  do not exist anywhere in `origin/main`) with the real, verified Phase 4 sequence using the actual
  tracked publish-preparation tools.
