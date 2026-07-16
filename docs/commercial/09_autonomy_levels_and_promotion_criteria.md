# Autonomy Levels and Promotion Criteria

**Visibility:** Internal
**Document type:** Internal engineering/governance draft. No legal review required.
**Status:** First draft. Reflects `pipeline/influencer_nodes/lena/autonomy_ladder_v1.json` as present
in `origin/main` at commit `94da3c3d`.
**Owner:** Engineering lead / governance owner (names to be assigned)
**Review cadence:** On every change to the ladder policy file; otherwise quarterly.

## Purpose

Define, level by level, what is allowed, what is required, and what must be true before promotion to
the next level, using the actual policy file as the source of truth.

## Intended Audience

Internal engineering, governance reviewers.

## Scope

Covers the implemented six-level ladder (0–5) as it exists in the shared repository today. Does not
cover operator command sequences (Operator Runbook, Internal visibility).

## The Implemented Ladder

Source: `pipeline/influencer_nodes/lena/autonomy_ladder_v1.json`, schema `lena_autonomy_ladder_v1`.

| Level | Name | Status | Key allowed actions | Key forbidden actions | Approval requirements |
|---|---|---|---|---|---|
| 0 | `dry_run_no_live` | active | dry-run strategy prep, read-only learning reads, candidate scoring, dry-run queue/handoff construction | provider calls, posting, approval consumption, claims, receipts, queue mutation | None required |
| 1 | `candidate_generation_only` | active | candidate generation, dry-run packet/queue previews | provider calls, posting, approval consumption, claims, receipts | None required |
| 2 | `live_higgsfield_generation_with_explicit_approval` | active | live generation, per-slot approval consumption, claim/receipt creation, QA disposition, bounded retry handoff and execution under separate approval | publishing, queue promotion, auto-approval, implicit escalation, unbounded retry | Human generation approval and human retry approval, both per-slot; posting approval explicitly separate |
| 3 | `human_approved_posting` | disabled | human-approved posting prep, manual publish review, approved queue construction, connector dispatch after explicit approval | autonomous posting, auto-approval, queue promotion without separate approval | Human posting approval, separate from generation approval, per item/batch |
| 4 | `bounded_autonomous_posting` | disabled, future | reserved | autonomous posting, auto-approval, live publish without explicit policy unlock | Future policy unlock required |
| 5 | `multi_node_autonomous_media_engine` | disabled, future | reserved | cross-node autonomy without governance, auto-approval | Future policy unlock required |

## Cross-Cutting Autonomy Rules (Apply at Every Level)

- Auto-approval is forbidden at every level.
- Implicit escalation is forbidden at every level.
- Generation approval does not imply posting approval, at every level.

These are top-level ladder rules — no level definition may override them.

## Current Operating Point

The system operates at **Levels 0–2 active**, with Level 3 explicitly disabled. Level 3's code-level
enforcement is independently confirmed real: a merged, tracked publish-preparation tool calls the
ladder's enforcement function requesting Level 3 and is rejected today (see the System Architecture
document, Customer-under-NDA visibility).

## Promotion Criteria: What Actually Gates Moving Up a Level

Per-level `tests_required` fields in the policy file name the test suites expected before a level is
considered proven:
- Level 0 → 1: strategy autonomy dry-run tests, candidate gate tests.
- Level 1 → 2: candidate selection tests, dry-run queue tests.
- Level 2 → 3: generation-approval tests, claim/receipt tests, QA disposition tests, bounded retry
  tests.
- Level 3 → 4, and 4 → 5: no test suite exists yet, because no code exists yet at these levels.

**No separate, independently-tracked operating-history readiness score is asserted in this document.**
A prior draft referenced a specific numeric readiness score and classification from a tool that was
not found anywhere in the shared repository during fact-checking for this revision — it has been
removed rather than asserted without evidence. If such a tool exists in a private or local
environment, it should be re-added here only once confirmed present in `origin/main`.

## Promotion Is Never Automatic

No code path promotes a level automatically based on test results. Level enablement (`enabled:
true/false`) is a value in the policy file itself, changed by an explicit, reviewed edit — not a
runtime computation.

## Responsibilities

- **Engineering:** keeps `tests_required` accurate for each level; does not flip `enabled` without a
  corresponding governance review.
- **Governance/compliance owner:** reviews any proposed level-enablement change against the named
  test suites.

## Controls

- Explicit, versioned, human-edited level-enablement flags.
- Named test-suite requirements per level transition.
- Independent code-level enforcement confirmed via a real, merged tool (see Current Operating Point).

## Procedures

Before proposing to enable Level 3, confirm all named test suites for the 2→3 transition pass.

## Audit Evidence

`pipeline/influencer_nodes/lena/autonomy_ladder_v1.json` and `pipeline/influencer_nodes/lena/autonomy_ladder.py`,
both confirmed present in `origin/main` at commit `94da3c3d`.

## Exceptions

- No historical freeze-exception event is asserted in this document.
- No numeric operating-history readiness score is asserted in this document (see above).

## Version and Review Cadence

- **Version:** 0.3 — removed a numeric readiness-review score and a historical freeze-exception
  reference, neither of which could be confirmed against `origin/main`; added confirmation that
  Level 3's enforcement is independently verified in real, merged code.
