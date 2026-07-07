# Current State -- 90_content_packet

**Last verified:** 2026-07-07, after Batches 1+2 of the first real tool were
committed.

## Status: first real tool exists, Markdown-only, no queue-draft writing yet

This is the sixth Lena folder-native agent slice (after
`40_identity_continuity/`, `50_prompt_builder/`, `60_executor/`,
`70_visual_qa/`, `80_repair/`). Created 2026-07-07 as a docs-only design
pass, following a read-only audit that found `tools/strategy/
lena_build_content_packet_dryrun_v1.py` (the previously-assumed "official"
content-packet builder) is disconnected from the real live chain -- see
`pipeline/change_notes/NEXT_SESSION_START.md`'s 2026-07-07 banner and the
corrected `information_hierarchy/Projects/Lena Influencer Node/Instructions/
Instructions.md`.

**`tools/lena_build_publish_packet_v1.py` now exists, in two committed
batches:**
- **Batch 1 (`346d0006`):** read-only resolver. Resolves a named
  `--date`/`--slot`, requires an existing rendered image, requires an
  existing, internally-consistent QA verdict, hard-fails unless
  `overall == "pass"`. Writes nothing. Deliberately does not reuse
  `tools/lena_review_proof_render_v1.py`'s `build_review_bundle()`, because
  that function's `save_qa_template()` call can write a QA scaffold file as
  a side effect -- wrong for a resolver that must hard-fail with zero
  writes.
- **Batch 2 (`ea139e69`):** adds Markdown publish-packet writing only, to
  `pipeline/publish_packets/lena/<date>/LENA_PUBLISH_PACKET_<slot_id>.md`,
  non-clobber by default (`--force` overwrites only the exact resolved
  file, never a directory). Caption options are deterministic/mechanical
  drafts grounded in the real workorder caption/scene metadata, not
  generated copy.

**Still no queue-draft writer.** No `--queue-draft` flag, no write access to
`pipeline/queue/`, no `--live`/`--approve`/`--queue` flag anywhere in the
tool.

## What exists right now

- This folder's 5 docs (`AGENT.md`, `RULES.md`, `INPUTS.md`, `OUTPUTS.md`,
  `CURRENT_STATE.md`).
- **`tools/lena_build_publish_packet_v1.py`** (Batches 1+2, `346d0006` +
  `ea139e69`) -- the first real code owner this slice has had.
- **One real, hand-built precedent**, not produced by the tool above (it
  predates the tool):
  `pipeline/publish_packets/lena/2026-07-07/
  LENA_PUBLISH_PACKET_2026-07-07-03-photo.md`, built by Claude directly from
  the real QA-passed render at `pipeline/kling_library/lena/2026-07-07/
  2026-07-07-03-photo_seed.png` and its QA verdict at `pipeline/
  asset_review/lena/2026-07-07/2026-07-07-03-photo_qa.json`. This packet was
  later used, via a manually-built queue item, in the one real live
  Instagram publish this project has ever made (media id
  `18154201054431808`). The tool's Markdown output was validated (in a
  scratch directory, then deleted) against this exact slot and matches its
  structure and provenance details (same Kling task id).

## What does NOT exist yet

- **No queue-JSON-draft writer** (Batch 3, optional/deferred, needs separate
  approval).
- No automated QA-verdict-to-packet pipeline beyond this one CLI tool.
- No connection to a `95_publish_gate/` slice -- that slice does not exist
  either, and this one intentionally comes first (see `RULES.md`).
- No second *tool-generated* packet has been kept on disk to compare against
  the one hand-built precedent -- the one generated during Batch 2 validation
  was written to a scratch directory and deleted after inspection, per the
  approved validation plan.

## Next action

Not decided. Two options remain open, both needing separate explicit
approval: Batch 3 (`--queue-draft` JSON emission to a non-live path,
`approved_for_live_publish` hardcoded `false`), or a further Kling
reliability check on an unrelated track. `95_publish_gate/` remains deferred
until packet/queue-draft behavior is settled.

## What is NOT currently proven

- Whether the packet's exact section structure/caption-option quality holds
  up as genuinely useful across other scenes/outfits/lanes -- only validated
  against the one real precedent slot so far (in a scratch directory, not
  kept).
- Whether an automated builder actually saves meaningful time over the
  manual process that produced the one real packet -- not yet measured.
- Whether a queue-JSON draft, if Batch 3 is ever approved, would need any
  contract-validation step beyond what `pipeline/posting_manager.py`
  already enforces on real queue items -- not yet investigated.
