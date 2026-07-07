# Rules -- 95_publish_gate

Grounded in `90_content_packet/RULES.md`/`OUTPUTS.md` (the real queue-draft
shape and its hardcoded safety fields), `pipeline/posting_manager.py` and
`tools/process_queue.py` as they actually exist, and the real
2026-07-07-03-photo packet/queue/receipt chain.

## Rule zero -- this slice records a decision, it does not make one

Nothing in this slice, now or in any future built version, may generate,
infer, or default an approval. Every field in the eventual approval
artifact must trace back to an explicit, current-session human statement --
never to a heuristic, a prior approval on a different post, or a "looks
fine" inference from QA passing.

## Required inputs from `90_content_packet/` (see `INPUTS.md` for detail)

An approval decision must never be recorded without all of the following
present and resolved:
- The Markdown publish packet.
- The optional queue-draft JSON, when one is expected for this workflow.
- The QA path/verdict the packet itself points to (read via the pointer,
  never re-derived).
- The final chosen caption (operator-picked, not a packet option left
  unedited, not the queue-draft placeholder).
- An explicit operator approval statement.

## Hard blocks -- must prevent recording approval

- **Placeholder caption still present.** If the queue draft's `caption`
  field (or the caption text otherwise associated with this approval) still
  equals `tools/lena_build_publish_packet_v1.py`'s
  `QUEUE_DRAFT_CAPTION_PLACEHOLDER` string, or is otherwise clearly
  unedited, block. This is the single most important check -- it is exactly
  the failure mode `90_content_packet/RULES.md`'s "never auto-select a
  caption" rule exists to prevent from reaching this far downstream.
- **More than 3 hashtags** in the final chosen caption.
- **QA not `pass`.** Re-check the QA verdict at the packet/draft's own
  `qa_path` pointer -- `overall != "pass"` blocks, regardless of what the
  packet or draft claim, per the same discipline as
  `90_content_packet/RULES.md` Rule zero and `70_visual_qa/RULES.md`'s
  stale-QA-file lesson (re-check `reviewed_at_utc` against the actual
  render, don't trust a cached claim).
- **Missing packet.** No Markdown packet, no approval.
- **Missing queue draft, when a queue draft is expected for this workflow.**
  (A packet built without `--queue-draft` has no draft to reference; that's
  a different, valid state -- see `INPUTS.md`. This block is for when a
  draft was supposed to exist and doesn't.)
- **`metadata.queue_draft_only` missing or `false`** on the queue draft
  being referenced. If this field isn't present and `true`, the file being
  pointed at may not actually be a `90_content_packet/`-produced draft at
  all -- block rather than guess.
- **Unclear operator approval.** No inferred approval from silence, from a
  prior turn's unrelated "approved" language, or from the mere existence of
  a chosen caption. The statement must be unambiguous and current.

## Safe handling of the queue-draft's existing safety fields

The queue draft produced by `90_content_packet/` already carries hardcoded
safety fields. This slice must never mutate them:

- **`approved_for_live_publish` stays `false` in the draft file, always.**
  This slice's approval decision is recorded as a **separate artifact**,
  never as an edit to the queue-draft JSON. `pipeline/posting_manager.py`
  does not read this field as a gate anyway (confirmed by direct code
  read) -- the real safety value here is the separate, durable approval
  record this slice would define, not flipping a flag the publish code
  ignores.
- **`operator_review_required` stays `true` in the draft file, always.**
  Same reasoning -- this slice's own artifact is what actually demonstrates
  review happened; the draft's own field is a permanent, correct statement
  about what that file type is.
- **`metadata.queue_draft_only` stays `true` in the draft file, always.**
  It is a true statement about the file's nature (a draft), independent of
  whether it was later approved.

## Must never do

- **Never move, copy, or write any file into `pipeline/queue/`**, in any
  form, at any point -- not the queue draft, not a modified copy of it, not
  a new file. This boundary stays a human, manual action indefinitely.
- **Never run `tools/process_queue.py`**, with or without `--live`.
- **Never call `pipeline/posting_manager.py`** or any of its methods.
- **Never call Kling, upload to R2, or read/edit `.env`.**
- **Never generate, infer, or default an approval** (Rule zero).
- **Never treat an approval recorded for one slot/render as applying to a
  different one**, even a superficially similar rerender.

## Output concept (not built yet -- see `OUTPUTS.md`)

If a future approval-artifact format is designed and built, its output is
**a record, plus human-readable manual promotion instructions** -- never an
automated file move. See `OUTPUTS.md` for the full concept.

## Human approval required

- Designing the exact approval-artifact schema/format as final/locked.
- Building any approval-artifact writer code -- **no code exists yet; this
  entire folder is design documentation, not a green light to implement.**
- Building any tool that reads an approval artifact and prints promotion
  instructions (a read-only checker, the most automation this slice could
  ever plausibly justify -- see `AGENT.md`/`OUTPUTS.md`).
- Any change to what counts as a hard block above.
- Any future decision to let *any* code write into `pipeline/queue/` --
  flagged here as something this slice's doctrine currently forbids
  outright, not merely defers.

## Not yet decided / not yet built

- No approval-artifact format is finalized -- `OUTPUTS.md` documents a
  concept, not a schema.
- No approval-artifact writer, reader, or checker code exists anywhere in
  the repo.
- No queue-promotion tool exists, and none is currently planned beyond
  printing manual instructions (see `OUTPUTS.md`).
- Whether this slice will ever need its own storage location for approval
  records (e.g. alongside the packet, or in a new folder) -- not decided.
