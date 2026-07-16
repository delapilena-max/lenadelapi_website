# AI Governance and Human Oversight Policy

**Visibility:** Public
**Document type:** Business/governance draft — requires review by qualified counsel before external
or regulatory use.
**Status:** First draft, internal only, not yet approved for external distribution.
**Owner:** Governance/compliance owner (name to be assigned)
**Review cadence:** On every change to the autonomy tiering or the publish freeze; otherwise quarterly.

## Purpose

State where human judgment is mandatory, where automation is permitted today, where it is planned,
and what independent controls stop automated action regardless of any upstream approval.

## Intended Audience

Buyers evaluating governance posture, trust & safety reviewers, regulators/auditors, internal
leadership.

## Scope

Covers the platform's graduated autonomy model and the separation between generation authority and
publishing authority, at a level appropriate for public description. Implementation-level detail
(file names, exact error codes) is intentionally omitted here and lives in the Customer-under-NDA
and Internal documents in this suite.

## A Graduated Autonomy Model

Autonomy is graduated, not all-or-nothing, across six tiers (numbered 0 through 5). Today, the
platform operates at the tiers covering: planning and candidate preparation with no spend; live
generation gated by an explicit, per-attempt human approval; and quality review. Publishing sits at
a materially higher tier that is currently disabled by default. Two further tiers, covering bounded
automatic retry/generation and multi-node operation, are designed but not implemented.

## Mandatory Human Approval for Live Generation

No live provider call occurs without a human-authored, attempt-specific approval. The execution
component defaults to a no-op / dry-run mode, and a live call without a valid, matching approval is
rejected outright.

## Publishing Is a Separate, Independently Held Authority

Generation approval never implies publishing authorization. This is enforced structurally: the
component responsible for preparing content for publication independently checks whether publishing
is currently authorized before doing anything else, and currently, that check fails closed — meaning
publishing preparation does not proceed today, regardless of how many generations have been approved
or how well they scored in quality review.

## The Publish Freeze

A standing, independently controlled freeze blocks every publishing surface by default. No automated
signal — not a quality-review pass, not a generation approval, not a successful test run — can lift
it. Lifting it requires an explicit, separate, out-of-band decision.

## Quality Review Before Retry or Publish Eligibility

A generated asset's eligibility for packaging toward publication, and its eligibility to inform a
retry decision, is gated by a mandatory quality-review verdict against a fixed, multi-criterion
checklist. A successful generation from the provider is not itself sufficient — quality review is a
distinct, later, currently human-executed gate.

## Retry / Repair Is Partially Designed, Not Fully Automated

Policy exists for some retry decisions; broader automated repair and retry-under-policy is a planned
capability, not a delivered one. Every retry decision made in current operation is a human judgment
call, not an automated process.

## Reconciliation Between Strategy and Execution

When the platform's strategic recommendation and its executable-candidate selection disagree, an
explicit reconciliation step exists to resolve that disagreement. As of this writing, the mechanism
for recording an operator's reconciliation decision is implemented, and connecting that decision into
the content-generation build step is currently being integrated — this is in-progress work, not yet
complete end-to-end.

## Fail-Closed Is a Governance Requirement

Every reconciliation, binding, and authorization check in this platform is designed to fail closed —
stopping rather than proceeding on missing, stale, or inconsistent evidence.

## Responsibilities

- **Accountable operator (designated individual, to be named):** sole authority to lift the publish
  freeze; reviews and gives generation approvals.
- **Engineering:** may not introduce a path that authorizes a higher autonomy tier without a
  corresponding update to this document and the underlying policy.
- **Governance/compliance owner:** maintains this document.

## Controls

- A versioned, explicit autonomy-tiering policy.
- An independently-controlled publish freeze.
- A mandatory, checklist-based quality-review gate.
- A documented (partially automated) retry-cap approach.

## Procedures

See the Operator Runbook (Internal visibility) for the exact current command sequence, and the
Incident Response plan (Internal visibility) for halting the system if a control is suspected to have
failed.

## Audit Evidence

Detailed file-level and schema-level evidence for every claim above is maintained in the
Customer-under-NDA System Architecture document and the Internal Artifact/Approval/Audit-Provenance
Specification.

## Exceptions

- This document does not assert compliance with any specific regulatory AI framework.
- "Designated accountable operator" is a role description, not yet bound to a named individual or
  formal delegation instrument in this draft.
- No historical instance of the publish freeze being lifted is asserted in this document.

## Version and Review Cadence

- **Version:** 0.3 — rewritten at Public visibility; removed internal file paths, error codes, and
  any historical operational claim not independently verifiable against the shared repository.
  Mandatory qualified-counsel review before regulator- or customer-facing use.
