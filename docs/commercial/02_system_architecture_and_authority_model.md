# System Architecture and Authority Model

**Visibility:** Customer under NDA
**Document type:** Technical draft. No legal review required; engineering review required before distribution.
**Status:** First draft, internal only. Every file path and behavior below was verified directly
against `origin/main` at commit `94da3c3d` on 2026-07-16 — not against any local, uncommitted, or
quarantined workspace content.
**Owner:** Engineering lead (name to be assigned)
**Review cadence:** On every merge touching the files named below; otherwise quarterly.

## Purpose

Map the real pipeline stages to the real, currently-merged code that owns them, and state precisely
which stage has authority over which decision.

## Intended Audience

Technical buyers under NDA, integration engineers, internal engineering.

## Scope

Covers the pipeline from strategic recommendation through publishing, for the current single-creator
implementation, as it exists in the shared repository today — explicitly distinguishing implemented,
partially implemented, being integrated, and planned.

## The Ten Separated Decisions

No earlier decision is allowed to imply authority for a later one:

| Decision | Implies authority for the next stage? |
|---|---|
| Strategic recommendation | No — does not authorize generation |
| Executable candidate selection | No — does not authorize spending |
| Recommendation/candidate reconciliation | No — does not authorize provider access |
| Handoff preparation | No — handoff artifacts do not carry a live-execution-authorized flag set to true by construction |
| Generation approval | No — does not authorize publishing; scoped to one attempt |
| Provider execution | No — a returned image is not itself publish-eligible |
| Accounting | N/A — records what happened, authorizes nothing |
| QA disposition | No — a pass verdict makes an asset eligible for packaging, not published |
| Retry authorization | No — a retry is its own bounded, separately-approved attempt |
| Publishing authorization | Independently gated by the autonomy ladder's Level 3 state, never inferred from any of the above |

## Pipeline Map: Real Stages, Real Files (Verified Against `origin/main`)

| Stage | Real file(s) | Status |
|---|---|---|
| Post-outcome learning state | `tools/strategy/lena_build_post_outcome_learning_state_v1.py` | Implemented |
| Strategic recommendation | `tools/strategy/lena_recommend_next_generation_step_v1.py` | Implemented |
| Queue dry-run planning | `tools/strategy/lena_build_autonomous_generation_queue_dryrun_v1.py` | Implemented |
| Candidate selection | `tools/strategy/lena_pre_generation_candidate_gate_v1.py` | Implemented |
| Recommendation/candidate reconciliation artifact | `tools/strategy/lena_build_generation_reconciliation_v1.py` | Implemented (merged) |
| Operator reconciliation decision | `tools/strategy/lena_record_generation_reconciliation_decision_v1.py` | Implemented (merged); authorizes `handoff_preparation_only` and nothing further |
| Handoff construction | `tools/strategy/lena_build_next_live_image_handoff_v1.py` | Implemented for the recommendation/candidate equality check; **does not yet reference the reconciliation-decision artifact** — wiring reconciliation into handoff construction is in progress on a separate active branch |
| Identity/continuity authority | `pipeline/identity/lena_identity.py`, `pipeline/identity/lena_visual_reference_authority_v1.json` | Implemented |
| Generation approval | `tools/lena_higgsfield_generation_approval_v1.py`, `tools/lena_record_higgsfield_generation_approval_v1.py` | Implemented |
| Provider execution | `pipeline/higgsfield_lena_api_executor.py` | Implemented; defaults to dry-run |
| Quality review | `pipeline/qa/lena_photo_qa.py`, `tools/lena_photo_qa_disposition_v1.py` | Implemented as a fixed checklist; QA itself is human-executed, not automated |
| Publish-queue construction (gated) | `tools/lena_build_approved_publish_queue_v2_8.py` | Implemented; calls the autonomy-ladder gate directly (see below) |
| Autopublish execution | `tools/lena_autopublish_approved_queue_v2_8.py` | Implemented |
| Autonomy ladder enforcement | `pipeline/influencer_nodes/lena/autonomy_ladder.py`, `pipeline/influencer_nodes/lena/autonomy_ladder_v1.json` | Implemented |

## Reconciliation: Current State Is "Being Integrated," Not "Complete"

Two real, merged pieces exist:
- `lena_build_generation_reconciliation_v1.py` produces a reconciliation artifact when recommendation
  and selected candidate disagree.
- `lena_record_generation_reconciliation_decision_v1.py` lets a human record an explicit, auditable
  decision about that disagreement — but this decision artifact is scoped to authorize
  `handoff_preparation_only`. It hardcodes `live_generation_authorized: false` and
  `publishing_authorized: false` on every code path, independently of what the operator decides.

**What is not yet true:** `lena_build_next_live_image_handoff_v1.py`, as merged on `origin/main`
today, contains no reference to the reconciliation-decision artifact at all — confirmed by direct
source search. This means a recorded reconciliation decision does not yet change what the handoff
builder actually does. Wiring this consumption in is explicitly in progress on a separate branch.
Do not describe reconciliation as "complete" or "enforced end-to-end" until that integration merges
and this document is updated.

## Generation Approval Is Attempt-Specific

`tools/lena_higgsfield_generation_approval_v1.py` produces a scoped authorization bound to one
handoff, with its own expiration, independently re-validated at approval and execution time against
the live on-disk state of the artifacts it claims to bind to.

## Publishing Is a Separately, Independently Gated Authority — Verified in Real Code

This is the strongest concrete evidence that generation and publishing are separate authorities in
this codebase, not just separate names for the same approval. `tools/lena_build_approved_publish_queue_v2_8.py`
calls, directly in its `main()`:

```python
autonomy_ladder.assert_allowed(
    "lena_build_approved_publish_queue_v2_8",
    level=3,
    action="human-approved posting preparation",
)
```

`pipeline/influencer_nodes/lena/autonomy_ladder.py` reads the ladder policy file and raises
`AutonomyLadderError`/`AutonomyLadderBlocked` if the requested level is not enabled. Level 3
(`human_approved_posting`) is `enabled: false` in the current policy file — **so running this real,
merged tool today fails closed before it does anything else**, independent of whether a generation
was approved, executed, or QA-passed. This is verifiable by reading the ladder policy file directly;
it is not a claim resting on any unmerged or uncommitted code.

## The Publish Freeze

`pipeline/influencer_nodes/lena/autonomy_ladder_v1.json` sets `publish_freeze.active: true` and lists
the frozen surfaces explicitly (`approved_queue`, `autopublish`, `manual_publish_automation`,
`connector_dispatch`). No code path in the reviewed files lifts this automatically from a QA pass,
a generation approval, or any other upstream signal — lifting it is necessarily a distinct,
out-of-band change to the policy file itself. This document does not assert any specific historical
instance of the freeze being lifted; no such record exists in the shared repository as of this
writing.

## Defense in Depth

The reconciliation, binding, and approval checks are implemented at more than one layer (builder,
approval module, executor) rather than checked once and trusted downstream. A defect or tamper in
any single layer does not, by itself, produce an unauthorized provider call — though see the
Reconciliation section above for the one control that is not yet wired end-to-end.

## Responsibilities

- **Engineering:** maintains the reconciliation, binding, and ladder-enforcement checks; treats a
  change to any of them as a governance-relevant change.
- **Governance/compliance owner:** confirms this document matches merged code after any PR touching
  the files listed above.

## Controls

See sections above.

## Procedures

See the Operator Runbook (Internal visibility) for the exact current command sequence.

## Audit Evidence

Every file path in the pipeline map above was confirmed present via `git ls-files` against
`origin/main` at commit `94da3c3d` on 2026-07-16.

## Exceptions

- Reconciliation-to-handoff integration is in progress, not complete (see above).
- `tools/LEGACY_PROVIDER_SURFACES.md`, the repository's own routing legend, currently describes a
  Kling-based path as canonical and does not mention the Higgsfield-based executor/approval modules
  at all, despite those modules being extensively developed and merged. This is an internal
  documentation inconsistency in the repository itself, not resolved by this document — do not
  assert which generation provider is canonical without checking current state directly.
- No automated retry/repair system exists yet; retry-related fields in artifacts are honored where
  present but the decision logic for when to retry is only partially implemented.

## Version and Review Cadence

- **Version:** 0.3 — full rewrite after discovering that a prior draft of this document had been
  grounded in uncommitted, quarantined local-workspace content (a `pipeline/agents/lena/` slice-
  documentation folder, a two-phase publish-approval schema, specific historical publish events)
  that does not exist anywhere in `origin/main`. All such content has been removed. Every claim in
  this version was independently re-verified against the shared repository.
