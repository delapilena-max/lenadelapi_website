# Data Privacy and Processing Overview

**Visibility:** Legal draft
**Document type:** Business draft — **mandatory legal review before any external or regulatory
use.** This document is not a privacy policy and must not be published as one without counsel
review and completion of the open items below.
**Status:** First draft, internal only.
**Owner:** Legal/privacy owner (name to be assigned)
**Review cadence:** Before any external distribution; immediately upon any new third-party
integration or resolution of the identity/likeness question.

## Purpose

Describe what data categories this platform processes, where they flow, and flag the single open
question that most affects privacy/likeness classification.

## Intended Audience

Privacy officers, legal counsel, and — once finalized and legally reviewed — end users or platform
partners requesting a privacy disclosure.

## Scope

Covers data processed by the generation pipeline and known third-party data flows. Does not cover
any customer-specific deployment's additional data flows.

## Data Categories Processed (Verified Against `origin/main`)

| Category | Where it lives |
|---|---|
| Prompt/scene construction data | Repository policy files under `pipeline/prompt_banks/lena/` |
| Generated image/video assets | Local disk / library paths, excluded from version control |
| Outcome/learning data | Strategy-pipeline artifact directories |
| Approval and audit records | Runtime state, not committed to git |
| Identity reference material | Referenced by path and SHA256 in `pipeline/identity/lena_visual_reference_authority_v1.json`, the file itself excluded from version control |

## Open Question That Must Be Resolved Before Any Privacy Claim Is Made

The identity reference material behind the current creator persona is treated internally as visual
proof material for a managed persona. **Whether this reference material depicts a real, identifiable
individual — and under what license, consent, or model-release terms — is not established anywhere
in the shared repository and must be confirmed by product/legal before any privacy or
likeness-related claim is made.** See the dedicated identity/likeness rights record (Legal-draft
visibility) for the structured fields this must resolve.

**Until this is resolved, do not represent to any customer, partner, or regulator that the platform
processes no personal data.** Treat that as an open item, not a settled fact.

## Third-Party Data Flows

- **Generation provider:** receives prompt text and reference image data to produce generated
  images. Internal repository documentation is currently inconsistent about which specific
  generation provider is canonical for new work (see the Security Whitepaper's Exceptions section) —
  this document does not resolve that inconsistency and makes no claim about a specific provider
  beyond noting one is used.
- **Publishing destination:** real, tracked publisher modules exist for Meta-platform destinations
  (Instagram, Facebook). Publishing itself is currently blocked by the platform's independently
  controlled publish freeze (see the AI Governance document) — no live publish event is asserted or
  evidenced in this document.
- **Object storage:** used as a media host for content that has been promoted/published, per
  repository configuration; not independently audited for this document.

## What Is Not Yet Known (Must Be Resolved Before External Use)

- The identity/likeness question above — the single highest-priority open item.
- Data retention period for generated images, approval artifacts, and learning/outcome data.
- Whether any generated or intermediate data is transmitted to, or stored by, any analytics or
  monitoring third party.
- The legal basis and data-processing role (controller/processor) applicable to each third-party
  flow above.
- Whether any jurisdiction-specific data residency requirement applies to this deployment.

## Responsibilities

- **Legal/privacy owner:** resolves the open items above, starting with the identity/likeness
  question.
- **Engineering:** documents any new data flow here before it ships.

## Controls

- Generated images and identity reference material are excluded from version control.
- Approval and handoff artifacts are treated as audit records, which has retention implications that
  must be resolved per the open items above.

## Procedures

Before this document is used as a customer- or public-facing privacy disclosure: legal/privacy owner
resolves the identity/likeness question and the remaining open items; engineering confirms the
data-category table still reflects current pipeline state; counsel reviews and approves final
language.

## Audit Evidence

Data-category and third-party-flow claims above were checked directly against `origin/main` at
commit `94da3c3d`.

## Exceptions

- This document is explicitly **not** a privacy policy.
- No claim is made about compliance with any specific privacy regulation (GDPR, CCPA, or similar).
- No specific historical publish event, platform-reported identifier, or receipt is asserted in this
  document — none could be independently verified against the shared repository.

## Version and Review Cadence

- **Version:** 0.3 — full rewrite; removed a specific historical publish narrative and platform
  identifiers that were only supported by uncommitted local-workspace content, and corrected the
  publisher-module description to what is actually tracked in `origin/main`.
