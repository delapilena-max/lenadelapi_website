# Lena Identity, Likeness, and Reference Media Rights Record

**Visibility:** Legal draft
**Classification: Internal — Legal review required — Commercialization blocker until completed.**
**Status:** All fields below are unresolved placeholders. Nothing in this document invents consent,
ownership, or any other right. Every field must be filled in with a verified fact and a proof
location, or explicitly marked unresolved, before this record is considered complete.
**Owner:** Approving legal reviewer (to be assigned)
**Review cadence:** Not on a fixed schedule — this document blocks any commercialization decision
that depends on identity/likeness rights until every field is resolved.

## Purpose

Provide a single, structured record of the facts and rights that must be established regarding the
"Lena" persona's identity and reference media, so that no commercial, marketing, or product decision
proceeds on an assumed or invented answer to these questions.

## Why This Record Exists

The platform's generation pipeline uses identity reference material (tracked in
`pipeline/identity/lena_visual_reference_authority_v1.json` and referenced image files excluded from
version control) to anchor the visual identity of the "Lena" persona. Whether that reference material
depicts a real, identifiable person — and, if so, under what rights — is not established anywhere in
the shared repository. This record exists to force that question to an explicit, documented answer
rather than letting it remain implicit.

## Required Fields

| # | Field | Value | Proof location | Status |
|---|---|---|---|---|
| 1 | Whether Lena depicts a real, identifiable person | **UNRESOLVED** | — | Blocking |
| 2 | Legal name or entity of the depicted person (if applicable) | **UNRESOLVED** | — | Blocking |
| 3 | Identity owner (who holds the underlying identity rights) | **UNRESOLVED** | — | Blocking |
| 4 | Reference-image owner (who holds copyright/ownership in the specific reference images used) | **UNRESOLVED** | — | Blocking |
| 5 | Commercial likeness consent (does a valid, current consent or model release exist for commercial use of this likeness) | **UNRESOLVED** | — | Blocking |
| 6 | Permitted uses (exact scope of what the consent, if any, allows) | **UNRESOLVED** | — | Blocking |
| 7 | Prohibited uses (exact scope of what is explicitly disallowed) | **UNRESOLVED** | — | Blocking |
| 8 | Territory (geographic scope of any consent/license) | **UNRESOLVED** | — | Blocking |
| 9 | Duration (time period any consent/license remains valid) | **UNRESOLVED** | — | Blocking |
| 10 | Revocation terms (how and under what conditions consent can be withdrawn) | **UNRESOLVED** | — | Blocking |
| 11 | Deletion obligations (what must be deleted, and on what timeline, upon revocation or expiry) | **UNRESOLVED** | — | Blocking |
| 12 | Provider-processing consent (whether the identity owner has consented to the specific third-party generation provider(s) processing this reference material) | **UNRESOLVED** | — | Blocking |
| 13 | Derivative/generated-output rights (who owns or controls rights in AI-generated images/video derived from the reference material) | **UNRESOLVED** | — | Blocking |
| 14 | Proof-of-consent location (where the actual signed consent/release document is stored) | **UNRESOLVED** | — | Blocking |
| 15 | Approving legal reviewer | **UNRESOLVED — not yet assigned** | — | Blocking |
| 16 | Effective date | **UNRESOLVED** | — | Blocking |
| 17 | Review date (next mandatory re-review of this record) | **UNRESOLVED** | — | Blocking |
| 18 | Unresolved issues (open questions not captured by the fields above) | See "Unresolved Issues" section below | — | Blocking |

## Unresolved Issues

- The fundamental question (field 1) is unanswered: no document in the shared repository states
  whether the reference images are of a real person, a fully synthetic/AI-generated identity with no
  real-person source, or some other configuration (e.g., a real person's likeness used as a style
  reference without full identity adoption). This must be answered before any other field can be
  meaningfully completed.
- If the answer to field 1 is "yes, a real identifiable person," fields 2–14 all require a real legal
  process (identifying counsel, negotiating and executing a release, defining scope) that has not
  been started as of this record's creation.
- If the answer to field 1 is "no," this record should still be completed to affirmatively document
  that conclusion and the evidence for it (e.g., a description of how the reference material was
  generated), rather than left blank.
- A related, separate finding from the Security Whitepaper (Security-review confidential visibility)
  is relevant here: a real, tracked content-quality module maintains a list of terms banned from
  public captions, including disclosure-relevant terms such as "ai," "synthetic," "generated," and
  "not real." Legal counsel completing this record should review that finding directly, since it may
  bear on synthetic-media disclosure obligations independent of the identity/likeness question.

## Responsibilities

- **Approving legal reviewer (once assigned):** owns resolving every field above and signing off on
  this record.
- **Product/commercial owner:** treats this record's incompleteness as an active commercialization
  blocker, not a formality — no external claim about the Lena persona's nature (real vs. synthetic)
  should be made until field 1 is resolved.
- **Engineering:** does not introduce any new reference-media source without a corresponding update
  to this record.

## Controls

None of the fields in this record may be inferred, assumed, or filled in by an AI system, an
engineer, or a non-legal stakeholder. Every field requires a verified fact from a qualified legal
reviewer with a cited proof location.

## Procedures

This record must be fully resolved before: any public statement about whether Lena is a real or
synthetic persona; any commercial licensing of Lena's likeness; any use of Lena's likeness by a third
party; or any claim of ownership over Lena-derived generated content in a customer contract.

## Audit Evidence

`pipeline/identity/lena_visual_reference_authority_v1.json` is confirmed present in `origin/main` at
commit `94da3c3d` and is the technical artifact this legal record concerns — its existence is
evidence that reference material is used, not evidence of what rights exist in it.

## Exceptions

None. Every field in this record is currently unresolved.

## Version and Review Cadence

- **Version:** 0.1 — created as part of the commercial-documentation suite build-out. No field has
  yet been resolved.
