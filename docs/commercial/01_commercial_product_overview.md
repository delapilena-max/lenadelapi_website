# Commercial Product Overview

**Visibility:** Public
**Document type:** Business draft — requires review by qualified counsel and marketing/legal before any external use.
**Status:** First draft, internal only, not yet approved for external distribution.
**Owner:** Product/commercial owner (name to be assigned)
**Review cadence:** Re-review on every architecture change affecting autonomy levels or the publish freeze; otherwise quarterly.

## Purpose

Define, in commercial terms, what this product is: a governed decision-and-control layer around
AI-generated creator content, not any single component of it.

## Intended Audience

Prospective customers, partners, sales engineers, and internal leadership.

## Scope

Covers what the product is and where the current implementation sits relative to the longer-term
architecture. Implementation detail lives in the System Architecture document (Customer-under-NDA
visibility); this document intentionally omits internal file paths, error codes, and operational
names.

## What the Product Is

**A governed autonomous content-operations platform for AI-powered digital creators and brands.**

The product is the infrastructure around AI-generated media that makes it safe to operate at scale:
a decision engine that recommends what to create, a candidate-generation and filtering layer that
turns a recommendation into an executable request, reconciliation logic that resolves disagreement
between strategy and execution before money is spent, a scoped human-approval workflow gating every
provider call, an accounting and audit trail, a mandatory quality-review gate, and — held
deliberately separate from all of the above — publishing authority itself.

This is not, and should never be described as: a prompt generator, a social-media bot, an image
generator, an influencer automation script, or an autonomous publishing bot. Those are components
the platform orchestrates, not the product.

## The Pipeline, End to End

1. Read identity, visual style, content strategy, historical performance, and operating policy.
2. Recommend what content to create next.
3. Generate structured candidate prompts from approved recipes, scenes, wardrobe, poses, and
   identity anchors.
4. Filter unsafe, incoherent, low-quality, or contradictory candidates.
5. Select the strongest currently executable candidate.
6. Reconcile strategic intent against actual candidate availability when they diverge.
7. Build a generation handoff with immutable provenance and content hashes.
8. Require scoped, attempt-specific human approval before any provider credit is spent.
9. Call the external generation provider for a bounded number of attempts.
10. Record accounting, provider job identifiers, outputs, and audit evidence.
11. Run mandatory generated-asset quality review.
12. Permit a retry only when policy, budget, lineage, and QA evidence allow one.
13. Hold publishing as a wholly separate authority, disabled unless explicitly enabled.

## Current Implementation Status (Honest Accounting)

| Capability | Status |
|---|---|
| Recommendation, candidate generation, filtering, handoff construction | Currently implemented |
| Reconciliation between recommendation and candidate when they disagree | Currently being integrated — the reconciliation-decision mechanism exists; wiring it into the handoff-construction step is in progress |
| Scoped generation approval, bounded provider execution | Currently implemented and in active use under the platform's lowest live-generation autonomy tier |
| Quality review gate | Currently implemented as a fixed, multi-criterion checklist; still human-executed, not model-automated |
| Retry / repair decisioning | Partially implemented — policy exists for some decisions; broader automated repair is planned, not built |
| Publishing authority | Currently implemented and independently gated; disabled by default pending explicit authorization |
| Multi-provider support | Currently implemented at the architecture level (the platform is not hard-wired to one generation provider); which specific provider is canonical for new work is an internal operational detail, not asserted here |
| Multi-creator / multi-tenant support | Planned, not yet implemented. The current codebase is organized per-creator, which is a reasonable foundation, but no tenant-isolation mechanism exists today |
| Identity/likeness rights basis for the current creator persona | Subject to legal review — unresolved, see the dedicated identity/likeness record (Legal-draft visibility) |

## Responsibilities

- **Product/commercial owner:** keeps this document aligned with actual system behavior.
- **Engineering:** notifies the product owner when a pipeline or autonomy change would invalidate a
  claim here.

## Controls

All claims trace to a control described in the System Architecture document (Customer-under-NDA) or
the Artifact/Approval/Audit-Provenance Specification (Internal). No claim of compliance,
certification, or specific security control appears without that backing, and none is asserted in
this Public document beyond what is stated above.

## Procedures

Before this document is used in any customer-facing or public context, the product/commercial owner
confirms every claim still matches current repository state.

## Audit Evidence

Detailed evidence (file paths, schemas, test references) for every claim above is maintained in the
Customer-under-NDA and Internal documents in this suite, not reproduced here.

## Exceptions

- This document makes no uptime, SLA, certification, or encryption-standard claims.
- Multi-tenant/multi-creator capability is described as a directional architecture goal, not a
  present capability.
- No claim is made about which specific third-party generation provider is currently canonical;
  internal operational documentation on this point is inconsistent as of this writing and is being
  reconciled separately (see the Internal-visibility Security Whitepaper, Exceptions section).

## Version and Review Cadence

- **Version:** 0.3 — corrected against `origin/main` at commit `94da3c3d`; removed all claims that
  were only supported by uncommitted local workspace content rather than the shared repository.
