# Security Whitepaper

**Visibility:** Security-review confidential
**Document type:** Business/technical draft — requires review by qualified counsel and a dedicated
security review before external use. This document is not itself a security audit.
**Status:** First draft, internal only.
**Owner:** Security lead (name to be assigned)
**Review cadence:** Before any external distribution, at minimum annually thereafter, or immediately
after any change to credential handling, provider integration, or the controls below.

## Purpose

Describe security-relevant controls actually present in `origin/main` today, and explicitly disclaim
any control, certification, or standard not currently evidenced.

## Intended Audience

Security reviewers, procurement/vendor-risk teams under confidentiality, technical buyers performing
due diligence.

## Scope

Covers artifact-integrity controls, autonomy-tier enforcement, secret-handling practices, and gating
controls that bound blast radius. Does not cover infrastructure/hosting security posture.

## What This Document Does NOT Claim

- No third-party security certification (SOC 2, ISO 27001, or similar) — none is evidenced.
- No compliance claim with any specific regulatory security framework.
- No specific encryption-at-rest/in-transit standard.
- No uptime, availability, or completed-penetration-test result.

## Artifact-Integrity Controls (Verified Against `origin/main`)

- `tools/strategy/lena_build_next_live_image_handoff_v1.py` records source-artifact paths and
  SHA256 hashes for its recommendation and candidate inputs, and fails closed
  (`selected_candidate_recommendation_mismatch`) if they disagree.
- `tools/lena_higgsfield_generation_approval_v1.py` independently re-reads and re-hashes the
  artifacts it binds an approval to, rather than trusting values passed as arguments.
- `tools/strategy/lena_record_generation_reconciliation_decision_v1.py` (merged, PR #62) hardcodes
  `live_generation_authorized: false` and `publishing_authorized: false` on every code path, and its
  own test suite includes an AST-based check confirming the module imports none of the live
  executor/approval/QA/retry modules.

## Autonomy-Tier Enforcement Is a Real, Code-Level Security Control

`pipeline/influencer_nodes/lena/autonomy_ladder.py` is a real, small, auditable module: it reads a
single policy file and raises a typed error if a calling tool requests a tier that is not enabled.
`tools/lena_build_approved_publish_queue_v2_8.py` calls this gate directly before doing anything
else, requesting the tier associated with human-approved posting preparation — and that tier is
currently disabled, so this call fails closed today. This is a genuine architectural control, not
just a documented intention: it was confirmed by reading both files directly.

## Fail-Closed Behavior

Every integrity and reconciliation check reviewed fails closed with a specific named error code
rather than falling back to a default or "best effort" continuation.

## Continuous Integration Runs the Real Test Suite

As of the commit this document was verified against, the repository's CI configuration installs a
pinned, minimal dependency set and runs the complete automated test suite on every pull request and
on every push to the main branch, failing the check on any test failure, compilation error, or
whitespace/conflict-marker issue. This was previously not the case — CI checks existed but did not
actually validate anything. This is stated here as a real, currently-implemented control, not a
planned one.

## Secret and Credential Handling (Partial, As-Observed)

- Provider and platform credentials are expected to be held in a local, version-control-excluded
  configuration file. No plaintext credential was found committed in the files reviewed for this
  document. This is not a substitute for a dedicated secret-scanning audit, which has not been
  performed.
- One local-configuration file matching a `*.local.json` naming convention exists under
  `pipeline/influencer_nodes/lena/` — its naming convention suggests it is intended to hold
  deployment-specific, non-committed values, but its actual tracked content was not exhaustively
  reviewed for this document and should be checked directly by a security reviewer before any
  external distribution of this whitepaper, to confirm no credential material is present in a
  tracked file despite the naming convention.

## A Disclosure-Policy Observation Worth a Reviewer's Attention

A real, tracked content-quality module (`pipeline/lena_publish_quality_gate.py`) maintains an
explicit list of terms that are banned from public-facing captions, including terms like "ai,"
"synthetic," "bot," "generated," "avatar," and "not real." This is a genuine, code-level policy
choice about what language is allowed to reach the public, and it has direct relevance to platform
synthetic-media-disclosure obligations and to the identity/likeness questions raised in the Data
Privacy and Legal-draft documents in this suite. It is flagged here as a fact a security/trust-and-
safety reviewer should examine directly, not characterized further in this document.

## Blast-Radius Controls

The autonomy-tier model and the publish freeze bound what any automated or malfunctioning component
could do: live provider calls require an explicit flag plus a valid, attempt-specific approval, and
publish-preparation tooling independently checks and currently fails the autonomy-tier gate before
doing anything else.

## Responsibilities

- **Security reviewer (to be assigned):** performs the dedicated review this document is not a
  substitute for — infrastructure, dependency, secret-scanning, and transport security, including
  direct inspection of the `*.local.json` configuration file noted above.
- **Engineering:** maintains the integrity and fail-closed controls.

## Controls

See sections above.

## Procedures

A dedicated security review should be scheduled before this document supports any external decision.

## Audit Evidence

File paths cited above were confirmed present in `origin/main` at commit `94da3c3d` via direct
listing and reading, not recalled from any prior session or local workspace.

## Exceptions

- No dedicated security audit has been performed to produce this document.
- No dependency vulnerability scan result is cited.
- No infrastructure security review is included.
- `tools/LEGACY_PROVIDER_SURFACES.md` currently identifies a different generation-provider path as
  canonical than the one most actively developed in recent merged work — this inconsistency has
  direct relevance to understanding the platform's actual current attack surface and should be
  resolved by engineering before this document is finalized.

## Version and Review Cadence

- **Version:** 0.3 — full rewrite; removed all claims previously grounded only in uncommitted local
  workspace content (a two-phase publish-approval schema, a specific real-publish precedent with
  platform-reported identifiers, an identity-resolution mechanism referred to as "Rule Zero," and a
  clean-export re-verification chain) that could not be independently confirmed against
  `origin/main`. Replaced with claims verified directly against the shared repository.
