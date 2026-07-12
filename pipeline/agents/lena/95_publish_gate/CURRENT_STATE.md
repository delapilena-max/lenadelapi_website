# Current State -- 95_publish_gate

**Last verified:** 2026-07-12, later session, after the first real Lena
Reel published through this gate under a one-action publish-freeze
exception. Everything below this point in the file up to "## What exists
right now" describes the 2026-07-07 design/state and is now historical --
see the 2026-07-12 update immediately below for current reality.

## 2026-07-12 update: clean-export enforcement wired in; first real Reel promoted and published (one-action freeze exception)

Since the 2026-07-10 live-publish milestone (see the changelog for the
full history of `tools/lena_promote_to_queue_v1.py` and the two-phase
approval schema), `tools/lena_promote_to_queue_v1.py` gained mandatory
clean-export re-verification
(`tools/lena_verify_clean_export_v1.py::verify_clean_export()`) before any
write: it re-verifies the clean derivative, then points the promoted
item's `media_path` at the verified clean derivative (never the raw
source), while preserving the raw source path/hash as provenance
metadata. `pipeline/publisher/instagram_queue_bridge.py` independently
re-verifies the same clean-export contract again at publish time
(`_validate_downstream_clean_export()`), never trusting the promoted
item's self-reported `clean_export_verified` flag alone. A new
`higgsfield_derived_shortform` provider resolver was also added so a
derived Reel/Story video (prepared from an already-approved photo slot,
no new generation) can be promoted under its own distinct `slot_id` while
Rule Zero still resolves identity against the true source generation
slot via `--source-slot`.

Nicolas explicitly, narrowly lifted the standing publish freeze (see
`NEXT_SESSION_START.md`) for exactly one item,
`readypack0709-pack007-00-photo-reel` -- a one-action exception, not a
general lift. `tools/lena_promote_to_queue_v1.py --provider
higgsfield_derived_shortform --source-slot
readypack0709-pack007-00-photo --promote` re-validated the approval
artifact and clean-export contract and wrote exactly one file to
`pipeline/queue/`. `tools/process_queue.py --live --media-type reel
--max-posts 1` (date-prefix-targeted) then published it, skipping the
other 10 real queue items untouched. **Real result:** Instagram media ID
`18114662917723939`, permalink
`https://www.instagram.com/reel/DatBbJdkjzD/`, published at
`2026-07-12T18:49:44+0000`, container polling reached `FINISHED`, Graph
`video_url` payload used the verified clean derivative (sha256
`59aa5a6cf864a6d707af80e027755a45b2fec4dc5efff63f4c19b0311f006928`), never
the raw provider original. Receipt: `pipeline/queue/published/
readypack0709-pack007-00-photo-reel.json.receipt.json`. The approval
record was not rewritten; the receipt is the authoritative post-publish
record. The standing publish freeze remains fully in force for every
other item. Full detail: the changelog's matching 2026-07-12 (later
session) entry.

## Status: first real tool complete -- read-only checker + approval-record writer

This is the seventh Lena folder-native agent slice (after
`40_identity_continuity/`, `50_prompt_builder/`, `60_executor/`,
`70_visual_qa/`, `80_repair/`, `90_content_packet/`). Created 2026-07-07 as
a docs-only design pass, following the completion of all three batches of
`tools/lena_build_publish_packet_v1.py` (`90_content_packet/`'s real tool),
which satisfied the precondition `90_content_packet/RULES.md` named for
this slice to exist meaningfully: a real packet/queue-draft artifact for a
gate to gate.

**`tools/lena_record_publish_approval_v1.py` now exists, in two committed
batches:**
- **Batch 1 (`bd4b6135`):** read-only checker. Validates the publish
  packet exists, the queue draft exists with `metadata.queue_draft_only:
  true`, QA re-validates to `overall == "pass"`, the approved caption is
  not the placeholder and has <=3 hashtags, `--approved-by` is non-empty,
  and `--confirm` exactly matches the required phrase. Writes nothing.
  Reuses (imports) `tools/lena_build_publish_packet_v1.py`'s placeholder
  constant and live-queue guard so the two tools can never drift out of
  sync.
- **Batch 2 (`68bba745`):** adds `--record`/`--force`. `--record` writes
  the durable approval artifact to
  `<out-dir>/<date>/<slot_id>_approval.json` (default under
  `pipeline/publish_packets/lena/`, never `pipeline/queue/`), non-clobber
  by default, `--force` overwrites only the exact resolved file.

**With this tool, the full Lena photo chain is now: photo render -> QA
pass -> publish packet -> queue draft -> approval record.** The final live
step -- manual promotion of a queue draft into `pipeline/queue/` and
running `tools/process_queue.py --live` -- **stays manual, not
automated**, exactly as `RULES.md` requires. No queue-promotion tool
exists, and none is currently planned.

## What exists right now

- This folder's 5 docs (`AGENT.md`, `RULES.md`, `INPUTS.md`, `OUTPUTS.md`,
  `CURRENT_STATE.md`).
- **`tools/lena_record_publish_approval_v1.py`** (both batches, `bd4b6135`
  + `68bba745`) -- the first real code owner this slice has had.
- The one real hand-built precedent this slice's design leaned on:
  `90_content_packet/`'s `LENA_PUBLISH_PACKET_2026-07-07-03-photo.md` and
  the free-text chat approval that accompanied the one real live publish
  this project has made. This tool's approval-artifact schema formalizes
  that same kind of decision, but no real (non-scratch) approval artifact
  has been written yet -- only scratch-directory validation runs, all
  deleted after inspection.

## What does NOT exist yet

- **No queue promotion tool.** No code moves, copies, or writes anything
  into `pipeline/queue/` -- that boundary stays a human, manual action
  indefinitely, per `RULES.md`.
- **No real approval artifact on disk anywhere** -- every one produced so
  far was a scratch-directory validation run, inspected then deleted.
- No connection between this slice and `tools/process_queue.py` or
  `pipeline/posting_manager.py` beyond doctrine-level awareness that a
  human runs them manually after recording an approval -- this tool never
  imports or calls either.

## Next action

Not decided. The full Lena photo chain (render -> QA -> packet -> queue
draft -> approval record) is now built and documented end-to-end up to the
manual-promotion boundary. A further Kling reliability check remains a
separate, unrelated, alternative track, needing its own explicit approval.
No further code work on this slice is currently proposed.

## What is NOT currently proven

- Whether this approval-decision artifact will actually get used in
  practice, versus reverting to chat-message approval out of convenience --
  untested against a real (non-scratch) approval.
- Whether the live-queue guard on the approval-artifact output path
  (`write_approval_record()`'s own `_assert_not_inside_live_queue()` call)
  is reachable via any real CLI invocation, given the earlier
  packet-existence check currently catches every tested `--out-dir
  pipeline/queue` scenario first -- confirmed correct via a direct
  unit-level test of the guard function in isolation, but not yet exercised
  end-to-end through the CLI.
- Whether a read-only checker/writer pair meaningfully reduces operator
  error versus manual review alone -- not measured in real use.
