# Rules -- 90_content_packet

Grounded in the one real precedent
(`pipeline/publish_packets/lena/2026-07-07/
LENA_PUBLISH_PACKET_2026-07-07-03-photo.md`), the real QA schema
(`pipeline/qa/lena_photo_qa.py`), the real queue/publish path
(`pipeline/posting_manager.py`, `tools/process_queue.py`), and this
project's approval discipline (master file §7.9, `information_hierarchy/
Projects/Lena Influencer Node/Instructions/Instructions.md`'s hard safety
rules).

## Rule zero -- no QA pass, no packet

A packet must never be built for a slot that does not have a real QA verdict
on disk (`pipeline/asset_review/lena/<date>/<slot_id>_qa.json`) with
`overall: "pass"`. No exceptions, no "probably fine," no building a packet
ahead of QA to save a step. If the QA file is missing, stale (see the
stale-QA-file lesson in `70_visual_qa/RULES.md` -- check `reviewed_at_utc`
against the actual render), or `overall` is anything other than `pass`,
this slice has nothing safe to build from.

## Must never do

- **Never generate an image, call Kling, or touch the executor
  (`pipeline/kling_apilena_api_executor.py`)** -- this slice only reads a
  render that already exists.
- **Never publish, upload to R2, or call any Meta/Instagram Graph endpoint.**
- **Never edit `.env`, read credential values, or print secrets.**
- **Never set `approved_for_live_publish: true`** on any queue-JSON draft it
  produces. Every packet and every optional queue draft starts and stays
  unapproved until a human explicitly reviews and approves it.
- **Never auto-select a caption.** A packet offers caption *options*; the
  final choice is always a human decision, exactly as the real precedent's
  §8 approval checklist requires ("Caption chosen (A-E) and caption<->image
  match confirmed").
- **Never treat a stale QA verdict as current** -- same discipline as
  `70_visual_qa/RULES.md`'s stale-QA-file lesson, since this slice's whole
  precondition (Rule zero) depends on trusting the right QA file.
- **Never invent scene, wardrobe, or prompt content.** Everything in the
  packet (scene description, caption grounding, hashtags) must trace back to
  the real workorder metadata and QA notes for that exact render -- not a
  generic template detached from what was actually produced.
- **Never treat `tools/strategy/lena_build_content_packet_dryrun_v1.py`'s
  output as an input to this slice.** That tool is a separate, disconnected,
  pre-render ideation system (recipe/hook/wardrobe/environment catalogs, its
  own prompt schema) -- see `AGENT.md` and the 2026-07-07 information-
  hierarchy correction in `NEXT_SESSION_START.md`. It remains ideation/
  planning only, not a source this slice reads from.
- **Never write directly into `pipeline/queue/`** as a background/automatic
  step. If a queue-JSON draft is produced at all, it must land somewhere
  reviewable first, not directly in the live queue directory that
  `tools/process_queue.py`/`posting_manager.py` actively scan.

## What must hard-fail (once code exists)

- Any attempt to build a packet where `qa_result.get("overall") != "pass"`.
- Any attempt to build a packet where the QA file's `schema_version` is
  missing or the file doesn't parse.
- Any attempt to write a queue-JSON draft with `approved_for_live_publish`
  set to anything other than `false`.
- Any attempt to write directly to `pipeline/queue/` (the live scan
  directory) instead of a reviewable draft location.

## Human approval required

- Building the actual packet-builder code (a `lena_content_packet_builder.py`-
  style script, or equivalent) -- **no code exists yet; this entire folder is
  design documentation, not a green light to implement.**
- Choosing the final caption from the packet's offered options.
- Marking any queue draft `approved_for_live_publish: true`.
- Deciding the exact packet Markdown template/schema as final/locked, beyond
  the one real precedent this folder documents.
- Building the future `95_publish_gate/` slice, or deciding what artifact
  that gate should read from this slice's output.

## Why `90_content_packet/` comes before `95_publish_gate/`

A formal approval-gate artifact needs something real to gate. Building
`95_publish_gate/` first would have no real packet artifact to point at --
it would be gating nothing. `90_content_packet/` exists to produce that real
artifact first (a packet built from an actual QA-passed render); only once
that exists does a dedicated gate slice have a concrete thing to formalize
approval around. Building `95_publish_gate/` remains a separate, later,
explicitly-approved decision -- not implied or scheduled by this folder's
creation.

## Not yet decided / not yet built

- No packet-builder code exists anywhere in the repo. The one real packet
  (`LENA_PUBLISH_PACKET_2026-07-07-03-photo.md`) was hand-assembled by
  Claude directly, not produced by a tool.
- Whether the packet-builder, once built, should also write the optional
  queue-JSON draft, or whether that stays a fully separate manual step --
  not decided.
- Where a reviewable (not-yet-live) queue draft should live if the builder
  ever writes one automatically -- not decided; must not be
  `pipeline/queue/` directly (see "Must never do" above).
- The exact caption-option-count/format standard (the real precedent used 5
  options, each <=3 hashtags) -- treated as the working default, not yet
  formally locked as a rule.
- `95_publish_gate/`'s own shape and doctrine -- entirely out of scope for
  this folder; not started.
