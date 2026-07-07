# Outputs -- 95_publish_gate

**No approval-artifact code exists anywhere in the repo yet.** Everything
below documents a *concept*, not a built or even fully-specified format.
This slice's precondition (a real packet/queue-draft artifact to gate) is
now met by `90_content_packet/`'s completed tool, but that only means this
slice is *ready to be designed further*, not that anything here is built.

## Output concept 1: an approval decision artifact (not built, format not finalized)

**Intent:** replace today's ephemeral, free-text chat-message approval
("APPROVED TO PUBLISH...") with something durable and machine-readable, so
a future session can see *that* and *how* a specific packet was approved
without needing conversation history.

**Would need to capture**, per `RULES.md`'s required-inputs list:
- Which packet (path) and which slot/date it covers.
- The QA verdict it was approved against (path + `overall` value, re-checked
  at approval time).
- The final chosen caption -- the actual approved text, not a packet option
  reference.
- Platform(s) and any crop/format decision.
- Post timing decision.
- An explicit "approved to publish" statement, attributed and timestamped.
- Confirmation this is a manual, one-off controlled post (matching the real
  packet's own §8 checklist item).

**Where it would live, what format:** not decided. Candidates not yet
evaluated: a sibling JSON next to the packet (e.g.
`pipeline/publish_packets/lena/<date>/<slot_id>_approval.json`), or
something else. No decision made in this docs pass.

## Output concept 2: human-readable manual promotion instructions (not built)

**Intent:** once an approval decision exists, tell the operator exactly
what to do next -- in plain text, for a human to execute by hand. Something
like: "copy `<queue_draft_path>` to `pipeline/queue/`, replace the caption
field with the approved text below, then run `python
tools/process_queue.py --live --media-type photo --date <date>`."

**This is never an automated file move.** No code in this slice, now or in
any future built version, writes into `pipeline/queue/` or invokes
`tools/process_queue.py` -- see `RULES.md`'s "must never do" list. The most
this concept could ever justify is a **read-only checker** that verifies an
approval record and its referenced queue draft are consistent (no
placeholder caption remaining, QA still `pass`, etc.) and then *prints*
these instructions -- it would still require the human to perform the copy
and the `--live` invocation themselves.

## Who would consume these outputs (once built)

- The approval-decision artifact (concept 1) would be read by the operator
  themselves, and by any future session needing to confirm a specific past
  approval actually happened and what was approved.
- The promotion instructions (concept 2) are for the operator to execute by
  hand -- no automated consumer exists or is planned.

## Explicit gap statement

**Nothing in this slice is built.** No approval-artifact writer, no
approval-artifact reader, no promotion-instruction printer, no queue-file
mover. This folder documents a target concept only, following the same
docs-only genesis every other Lena agent slice went through
(`90_content_packet/` most recently). Building any of the above requires
separate, explicit approval (see `RULES.md`).
