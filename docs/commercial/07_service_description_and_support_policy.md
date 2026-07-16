# Service Description and Support Policy

**Visibility:** Customer under NDA
**Document type:** Business draft — **mandatory legal/commercial review before use as an actual
customer-facing terms document.**
**Status:** First draft, internal only. Describes the service as it exists today (single creator,
operator-run), not a scaled commercial offering.
**Owner:** Commercial/product owner (name to be assigned)
**Review cadence:** Before any commercial launch; whenever the autonomy tiering or publish freeze
policy changes.

## Purpose

Describe what is actually delivered today (a single-creator, operator-run content-operations
pipeline) versus what a future multi-tenant commercial service would need to add, so no support
commitment is made that current operations cannot back.

## Intended Audience

Customers (once a commercial offering exists), support staff, internal leadership.

## Scope

Covers the current operating model and its real limitations. Does not cover pricing/packaging
(undefined in this draft) or legal terms of service (must be drafted separately with counsel).

## What Is Delivered Today

A single managed creator persona is operated through the pipeline described in the System
Architecture document (Customer-under-NDA visibility): recommendation, candidate generation,
reconciliation (partially integrated — see that document's Exceptions), scoped generation approval,
bounded provider execution, accounting, mandatory quality review, packaging, and an independently
gated, currently-frozen publish authority. This is operated by a single accountable human operator,
not a self-service customer product.

## What Is NOT Delivered Today

- **No multi-tenant account model.** There is no mechanism today for a second creator/brand/customer
  to run an isolated instance of this pipeline under the same platform.
- **No self-service operator console.** Every gate (approval, publish preparation) is currently
  operated via command-line tools by the accountable operator directly.
- **No defined SLA, uptime commitment, or support-response-time commitment.** None should be quoted
  commercially until one is deliberately defined and the operational capacity to meet it exists.
- **No general publishing autonomy.** Publishing is frozen by default; no historical publish event is
  asserted or evidenced in this document (see the System Architecture document's Publish Freeze
  section).

## Service Boundaries by Autonomy Tier

Support and service expectations must track the actual autonomy tier in force — see the Autonomy
Levels and Promotion Criteria document (Internal visibility) for full definitions:

| Tier | What the service does | What it requires from the operator |
|---|---|---|
| Planning / candidate generation | Plans and prepares content, no spend | Nothing — fully automated within this bound |
| Live generation | Calls the generation provider for one bounded attempt per approval | An explicit, scoped generation approval per attempt |
| Publishing | Frozen by default | An explicit, separate authorization decision, from the accountable operator, before any use — no such authorization is asserted as having occurred in this document |

## Support Model (To Be Defined)

No formal support tiering, ticketing process, or response-time commitment exists today. Before this
document is used commercially, define: support channels and hours; severity classification; and an
escalation path to the accountable operator for anything touching the publish freeze or generation
approval.

## Responsibilities

- **Commercial/product owner:** defines the actual support model before any SLA is quoted.
- **Accountable operator:** remains the sole approver for generation and publish actions until a
  broader operator/support model is designed and implemented.

## Controls

Service boundaries are enforced by the same autonomy-tier and publish-freeze controls described in
the AI Governance document (Public visibility) — this document does not add new enforcement, it
describes what those controls mean for a customer.

## Procedures

Any commercial service description built from this draft must first resolve the "Support Model (To
Be Defined)" section before quoting to a customer.

## Audit Evidence

`pipeline/influencer_nodes/lena/autonomy_ladder_v1.json` (per-tier allowed/forbidden actions,
approval requirements) — confirmed present in `origin/main` at commit `94da3c3d`.

## Exceptions

- No pricing, packaging, or commercial terms are included in this draft.
- No SLA, uptime, or support-response commitment should be inferred from this document.
- No historical publish event or freeze exception is asserted in this document — a prior draft
  contained such a claim, sourced only from uncommitted local-workspace content, and it has been
  removed.

## Version and Review Cadence

- **Version:** 0.3 — removed an unverifiable historical publish/freeze-exception claim and a
  "two-phase publish approval" mechanism description that could not be confirmed against
  `origin/main`.
