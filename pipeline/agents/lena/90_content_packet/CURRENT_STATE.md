# Current State -- 90_content_packet

**Last verified:** 2026-07-07, at slice creation -- no prior state to compare
against.

## Status: docs/design only, no code

This is the sixth Lena folder-native agent slice (after
`40_identity_continuity/`, `50_prompt_builder/`, `60_executor/`,
`70_visual_qa/`, `80_repair/`). Created 2026-07-07 as a docs-only design
pass, following a read-only audit that found `tools/strategy/
lena_build_content_packet_dryrun_v1.py` (the previously-assumed "official"
content-packet builder) is disconnected from the real live chain -- see
`pipeline/change_notes/NEXT_SESSION_START.md`'s 2026-07-07 banner and the
corrected `information_hierarchy/Projects/Lena Influencer Node/Instructions/
Instructions.md`.

**Nothing beyond this folder's five Markdown docs exists.** No
packet-builder code, no automated QA-to-packet pipeline, no queue-draft
writer.

## What exists right now

- This folder's 5 docs (`AGENT.md`, `RULES.md`, `INPUTS.md`, `OUTPUTS.md`,
  `CURRENT_STATE.md`).
- **One real, hand-built precedent**, not produced by any tool:
  `pipeline/publish_packets/lena/2026-07-07/
  LENA_PUBLISH_PACKET_2026-07-07-03-photo.md`, built by Claude directly from
  the real QA-passed render at `pipeline/kling_library/lena/2026-07-07/
  2026-07-07-03-photo_seed.png` and its QA verdict at `pipeline/
  asset_review/lena/2026-07-07/2026-07-07-03-photo_qa.json`. This packet was
  later used, via a manually-built queue item, in the one real live
  Instagram publish this project has ever made (media id
  `18154201054431808`).

## What does NOT exist yet

- No packet-builder script or module of any kind.
- No automated QA-verdict-to-packet pipeline.
- No queue-JSON-draft writer.
- No connection to a `95_publish_gate/` slice -- that slice does not exist
  either, and this one intentionally comes first (see `RULES.md`).
- No second real packet to compare the one precedent against -- the exact
  Markdown template is documented in `OUTPUTS.md` as a working target based
  on a sample size of one, not a locked, validated schema.

## Next action

Not decided, and not proposed by this folder's creation. Per `RULES.md`'s
human-approval list, building actual packet-builder code is a separate,
future, explicitly-approved step -- this folder only records the design so a
future session (Claude or Codex) has a grounded starting point instead of
re-deriving it from scratch or, worse, assuming `tools/strategy/
lena_build_content_packet_dryrun_v1.py` is the live builder.

## What is NOT currently proven

- Whether the one real packet's exact section structure generalizes to other
  scenes/outfits/lanes, or was shaped by this particular rooftop-sunset
  render's specifics -- untested against a second example.
- Whether an automated builder, once built, would actually save meaningful
  time over the manual process that produced the one real packet -- not yet
  measured.
- Whether a queue-JSON draft written by a future builder would need any
  contract-validation step beyond what `pipeline/posting_manager.py`
  already enforces on real queue items -- not yet investigated.
