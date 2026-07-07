# Inputs -- 95_publish_gate

No code exists yet (see `CURRENT_STATE.md`). This documents what a future
approval-decision process (human-run today, possibly checker-tool-assisted
later) should read, entirely defined by `90_content_packet/`'s real,
already-built outputs -- not redefined here.

## Required inputs

| Input | Source | Role |
|---|---|---|
| Markdown publish packet | `pipeline/publish_packets/lena/<date>/LENA_PUBLISH_PACKET_<slot_id>.md`, produced by `tools/lena_build_publish_packet_v1.py` | The document a human reviews: image, QA summary, caption options, CTA/poll/pin ideas, platform notes, the packet's own unchecked approval checklist. |
| QA verdict (via pointer, never re-derived) | `pipeline/asset_review/lena/<date>/<slot_id>_qa.json`, referenced by the packet's `qa_path`/`qa_overall` fields | Re-checked at approval time, not trusted from the packet's cached claim -- `overall` must still read `pass` (RULES.md hard block). |
| Queue-draft JSON, when one is expected | `<out-dir>/<date>/<slot_id>_queue_draft.json`, produced by `tools/lena_build_publish_packet_v1.py --queue-draft` | Carries `approved_for_live_publish: false`, `operator_review_required: true`, `metadata.queue_draft_only: true`, and the placeholder caption -- all read, none mutated (RULES.md). |
| Final chosen caption | The operator, after reading the packet's caption options | Must not equal the queue draft's placeholder string or an unedited packet option -- this is the input this slice exists to validate. |
| Operator approval statement | The operator, current session, explicit | Must be unambiguous (RULES.md "unclear operator approval" hard block) -- not inferred from silence or prior unrelated approvals. |

## What this folder does NOT read

- **No wardrobe, scene, or prompt-construction content directly** -- that's
  `pipeline/prompting/lena_prompt_brain.py`, owned by `50_prompt_builder/`.
  This slice only sees what the packet already surfaced from that content.
- **No identity-resolution logic** -- owned by `40_identity_continuity/`.
- **No render/submission logic** -- owned by `60_executor/`. This slice
  never calls the executor and never reads live Kling credentials.
- **No QA-scoring logic** -- owned by `70_visual_qa/`. This slice reads the
  *verdict* (`overall`, via the pointer), never scores an image itself.
- **No packet/queue-draft construction logic** -- owned by
  `90_content_packet/`. This slice consumes that slice's outputs; it does
  not redefine or duplicate their shape.
- **Nothing from `pipeline/queue/`** -- this slice's job ends before any
  file reaches that directory (RULES.md "must never do").
- **Nothing from `pipeline/posting_manager.py` or `tools/process_queue.py`**
  beyond knowing, at a doctrine level, that a human runs
  `tools/process_queue.py --live` manually after this slice's (future)
  approval step -- this slice never imports or calls either.
