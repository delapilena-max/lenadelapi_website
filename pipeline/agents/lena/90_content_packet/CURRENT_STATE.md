# Current State -- 90_content_packet

**Last verified:** 2026-07-07, after all three batches of the first real
tool were committed.

## Status: first real tool complete -- resolver, Markdown packet, optional queue draft

This is the sixth Lena folder-native agent slice (after
`40_identity_continuity/`, `50_prompt_builder/`, `60_executor/`,
`70_visual_qa/`, `80_repair/`). Created 2026-07-07 as a docs-only design
pass, following a read-only audit that found `tools/strategy/
lena_build_content_packet_dryrun_v1.py` (the previously-assumed "official"
content-packet builder) is disconnected from the real live chain -- see
`pipeline/change_notes/NEXT_SESSION_START.md`'s 2026-07-07 banner and the
corrected `information_hierarchy/Projects/Lena Influencer Node/Instructions/
Instructions.md`.

**`tools/lena_build_publish_packet_v1.py` now exists, complete, in three
committed batches:**
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
- **Batch 3 (`e9edb3d9`):** adds optional `--queue-draft`, writing a
  queue-shaped draft JSON to
  `<out-dir>/<date>/<slot_id>_queue_draft.json` (default under
  `pipeline/publish_packets/lena/`, never `pipeline/queue/`). A hard guard
  (`_assert_not_inside_live_queue()`) runs before any write this run
  whenever `--queue-draft` is passed and rejects `--out-dir pipeline/queue`
  and `--out-dir pipeline/queue/something` (confirmed by real tests). Draft
  fields are hardcoded safe: `approved_for_live_publish: false`,
  `operator_review_required: true`, `metadata.queue_draft_only: true`,
  placeholder-only caption (never auto-selected), and
  `metadata.publish_packet_path` pointing back to the Markdown packet.

**Still no `--live`/`--approve`/publish flag anywhere in the tool, still no
import of `posting_manager`/`process_queue`/any publisher-API
module/the Kling executor/`requests`/`urllib`/`pipeline.env_loader`.**

## What exists right now

- This folder's 5 docs (`AGENT.md`, `RULES.md`, `INPUTS.md`, `OUTPUTS.md`,
  `CURRENT_STATE.md`).
- **`tools/lena_build_publish_packet_v1.py`** (all three batches, `346d0006`
  + `ea139e69` + `e9edb3d9`) -- the first real code owner this slice has
  had, now feature-complete against its original design.
- **One real, hand-built precedent**, not produced by the tool above (it
  predates the tool):
  `pipeline/publish_packets/lena/2026-07-07/
  LENA_PUBLISH_PACKET_2026-07-07-03-photo.md`, built by Claude directly from
  the real QA-passed render at `pipeline/kling_library/lena/2026-07-07/
  2026-07-07-03-photo_seed.png` and its QA verdict at `pipeline/
  asset_review/lena/2026-07-07/2026-07-07-03-photo_qa.json`. This packet was
  later used, via a manually-built queue item, in the one real live
  Instagram publish this project has ever made (media id
  `18154201054431808`). The tool's Markdown and queue-draft output were both
  validated (in a scratch directory, then deleted) against this exact slot
  and matched its structure and provenance details (same Kling task id).

## What does NOT exist yet

- No automated QA-verdict-to-packet pipeline beyond this one CLI tool (still
  operator-run, not scheduled/triggered automatically).
- No connection to a `95_publish_gate/` slice -- that slice does not exist
  yet. Per `RULES.md`, it was intentionally sequenced *after*
  `90_content_packet/` so it would have a real packet/queue-draft artifact
  to gate. That precondition is now met (all three batches committed) --
  `95_publish_gate/` is the next reasonable docs-only design target, not yet
  started.
- No second *tool-generated* packet or queue draft has been kept on disk to
  compare against the one hand-built precedent -- everything generated
  during validation across all three batches was written to a scratch
  directory and deleted after inspection, per the approved validation plan
  each time.

## Next action

Not decided. `95_publish_gate/` (docs-only design) is the next reasonable
target now that packet/queue-draft behavior is settled, but building it
needs its own separate approval, same as every prior slice. A further Kling
reliability check remains a separate, unrelated, alternative track.

## What is NOT currently proven

- Whether the packet's exact section structure/caption-option quality holds
  up as genuinely useful across other scenes/outfits/lanes -- only validated
  against the one real precedent slot so far (in a scratch directory, not
  kept).
- Whether an automated builder actually saves meaningful time over the
  manual process that produced the one real packet -- not yet measured.
- Whether a queue-JSON draft, once actually promoted into `pipeline/queue/`
  by a human, needs any contract-validation step beyond what `pipeline/
  posting_manager.py` already enforces on real queue items -- not yet
  investigated with a real promoted draft (only checked against the
  documented schema).
- Whether `95_publish_gate/`'s eventual shape will consume this slice's
  Markdown packet, the queue draft, both, or something else -- not decided.
