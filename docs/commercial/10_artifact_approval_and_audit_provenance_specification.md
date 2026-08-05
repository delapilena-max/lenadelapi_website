# Artifact, Approval, and Audit-Provenance Specification

**Visibility:** Internal
**Document type:** Internal engineering/audit draft. No legal review required.
**Status:** First draft, internal only.
**Owner:** Engineering lead / audit owner (names to be assigned)
**Review cadence:** On every change to any artifact schema named below; otherwise quarterly.

## Purpose

Specify what a decision artifact in this platform is required to contain, citing which fields are
confirmed present in real, merged schemas today and which are recommended additions not yet
implemented.

## Intended Audience

Engineers, auditors.

## Scope

Covers the artifact contract for handoffs, reconciliation decisions, and generation approvals, as
verified against `origin/main` at commit `94da3c3d`.

## The Artifact Field Model

| Field category | Confirmed present today | Evidence |
|---|---|---|
| Schema version | Yes | Present on the autonomy ladder policy and on candidate/recommendation artifacts |
| Timestamps | Yes | Generation timestamps on candidate/recommendation artifacts; approval/expiry timestamps on generation approvals |
| Source paths | Yes | Recorded on the handoff artifact for its recommendation and candidate inputs |
| SHA256 hashes | Yes | Recorded on the handoff artifact; independently re-validated at approval and executor time |
| Candidate / recipe / slot IDs | Yes | Present on the candidate artifact and the handoff |
| Prompt hashes | Yes | Bound and cross-checked in the approval module |
| Operator identity | Confirmed on the reconciliation-decision path (merged, PR #62); not independently confirmed on the generation-approval path in this review — verify directly before making an audit claim spanning both |
| Authority scope | Yes, via hardcoded negative flags | `live_generation_authorized: false` / `publishing_authorized: false` hardcoded on every path in the reconciliation-decision artifact; handoff artifacts do not set a live-execution-authorized flag to true by construction |
| Explicit "not authorized" statements | Yes, as boolean flags; not as narrative text | A narrative field explaining *why* an artifact does not authorize an action would improve human auditability and is a recommended addition, not a current feature |
| Explicit "next allowed action" | Not currently implemented | No artifact reviewed carries a field naming the specific next allowed action — recommended addition |

## The Reconciliation-Decision Artifact Is Scope-Limited By Design

`tools/strategy/lena_record_generation_reconciliation_decision_v1.py` (merged, PR #62) hardcodes
`live_generation_authorized: false` and `publishing_authorized: false` as Python literals with no
code path to set them true, and its own test suite includes an AST-based check confirming the
module imports none of the live executor, approval, QA, or retry modules. This was independently
re-verified for this document.

## Approval Records and Downstream Records: A Design Principle, Not Yet an Evidenced Operational History

This platform's intended design treats a pre-action approval record as an immutable signoff and any
post-action record (e.g., what a provider or destination actually reported) as a separate artifact
type, never rewritten into the approval. **This document previously asserted a specific historical
instance of this discipline being followed in practice, including platform-reported identifiers —
that assertion could not be confirmed against `origin/main` during fact-checking and has been
removed.** The design principle is stated here as intent, grounded in the fact that the codebase
does define distinct artifact types for approvals versus execution results (see the generation
approval and executor modules), not as a claim that a specific real-world event was observed to
follow it.

## Fail-Closed Conditions (Confirmed, by Error Code)

| Condition | Error code |
|---|---|
| Recommendation/candidate disagreement | `selected_candidate_recommendation_mismatch` |
| More than one selected candidate on the same date | `ambiguous_selected_candidate` |
| Handoff missing candidate provenance | `handoff_selected_candidate_missing_or_invalid` |

## Responsibilities

- **Engineering:** treats any change to a field listed as "confirmed present" as a schema-versioning
  event.
- **Audit/compliance owner:** uses this document's confirmed-vs-recommended distinction when
  representing audit capability to a customer — never round up a recommended field to a confirmed
  one.

## Controls

See field table and fail-closed condition table above.

## Procedures

Before claiming full field-level audit provenance to a customer, either implement the recommended
additions above or explicitly disclose that they are not yet present.

## Audit Evidence

`tools/strategy/lena_build_next_live_image_handoff_v1.py`,
`tools/strategy/lena_record_generation_reconciliation_decision_v1.py`,
`tools/lena_higgsfield_generation_approval_v1.py` — all confirmed present in `origin/main` at commit
`94da3c3d`.

## Exceptions

- Operator-identity binding is confirmed on the reconciliation-decision path but not independently
  confirmed on the generation-approval path in this review.
- No specific historical operational event is asserted anywhere in this document.

## Version and Review Cadence

- **Version:** 0.3 — removed a specific historical approval/receipt precedent (including
  platform-reported identifiers) that could not be confirmed against `origin/main`; replaced with a
  design-principle statement clearly distinguished from operational history.
