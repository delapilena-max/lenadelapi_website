# 95_publish_gate

**Role:** Own the durable human approval decision record for a Lena publish
packet -- the checkpoint between "a packet/queue-draft exists"
(`90_content_packet/`) and "a human may manually promote a queue file into
the live publish flow."
**Status:** Seventh filesystem-native slice. Documentation/design only -- no
code exists yet.
**Real owners (authoritative code):** none. Like `80_repair/` before its own
code existed, this entire folder is decision doctrine, not automation.

## Who this agent is

`content_bot`'s only "approval" mechanism today is a free-text chat message
("APPROVED TO PUBLISH..."), used exactly once, for the one real live
Instagram publish this project has made. `95_publish_gate/` exists to
define what a *durable, machine-readable* version of that same human
decision should look like, grounded in the real publish packet's own §8
approval checklist (`pipeline/publish_packets/lena/2026-07-07/
LENA_PUBLISH_PACKET_2026-07-07-03-photo.md`) and the real queue-draft shape
`tools/lena_build_publish_packet_v1.py` already produces.

This slice was intentionally sequenced *after* `90_content_packet/`
(`90_content_packet/RULES.md`'s own "Why 90_content_packet comes before
95_publish_gate" section) because a gate needs a real packet/queue-draft
artifact to gate. That precondition is now met -- `90_content_packet/`'s
tool is feature-complete across all three of its batches.

## What it does (target scope, once designed further / built)

- Defines the shape of an **approval decision artifact**: which packet was
  approved, the final chosen caption (not the placeholder), platform(s),
  timing, and an explicit operator "approved to publish" statement with a
  timestamp.
- Defines the hard blocks that must prevent recording an approval (see
  `RULES.md`).
- Defines human-readable, manual promotion instructions an operator would
  follow *after* recording approval -- never an automated file move.

## What it explicitly does not do

- **Does not build publish packets.** That's `90_content_packet/`.
- **Does not build queue drafts.** That's also `90_content_packet/`.
- **Does not QA images.** That's `70_visual_qa/`.
- **Does not move files into `pipeline/queue/`, ever, in any form.** No code
  in this slice, now or in any future built version, writes there.
- **Does not run `tools/process_queue.py`.**
- **Does not call `pipeline/posting_manager.py`.**
- **Does not publish, upload to R2, call Kling, or touch `.env`.**
- **Does not auto-approve anything.** Every approval this slice would ever
  record is a human decision, captured, never generated.

## Files in this folder

- `AGENT.md` -- this file.
- `RULES.md` -- required inputs, hard blocks, safe handling of the
  queue-draft's existing safety fields, and human-approval boundaries.
- `INPUTS.md` -- exact artifacts this slice would read from
  `90_content_packet/` and elsewhere.
- `OUTPUTS.md` -- the intended approval-artifact shape and the
  manual-promotion-instructions concept; explicit statement that neither is
  built yet.
- `CURRENT_STATE.md` -- status and next actions.

## How a new Claude/Codex session should use this folder

1. Read this file first for orientation.
2. Read `RULES.md` before assuming any queue draft is "approved" --
   nothing in this repo currently records that decision durably; a chat
   message is not an artifact.
3. Read `CURRENT_STATE.md` to confirm no approval-artifact code exists yet.
4. Read `90_content_packet/RULES.md` and `90_content_packet/OUTPUTS.md`
   directly -- this slice's inputs are entirely defined by that slice's
   outputs; do not redefine the packet or queue-draft shape here.
5. Do not propose or write approval-artifact code, or any code that touches
   `pipeline/queue/`, without separate, explicit approval, per `RULES.md`'s
   human-approval list.
