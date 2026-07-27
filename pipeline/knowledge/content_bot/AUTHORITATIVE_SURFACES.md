# Authoritative Surfaces — content_bot / Lena

**Purpose:** Which specific files are the source of truth for a given concern.
When two files seem to disagree, the one listed here wins — and if this file and
reality disagree, fix this file, don't guess.

Grounded in direct reads of each module's header/docstring on 2026-07-06.

## Doctrine and continuity (read these before touching anything)

| Concern | File |
|---|---|
| Master system prompt / permanent doctrine | `pipeline/knowledge/content_bot/CONTENT_BOT_MASTER_SYSTEM_PROMPT_V1_3.md` |
| Session start / current blocker / next step | `pipeline/change_notes/NEXT_SESSION_START.md` |
| Mandatory repo warm-up procedure for new chats | `pipeline/knowledge/content_bot/SESSION_BOOT_PROTOCOL.md` |
| Full pivot doctrine, architecture, current state (§0) | `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md` |
| Running technical log, batch-by-batch | `pipeline/change_notes/lena_agentic_pivot_changelog.md` |
| Repo orientation (this layer) | `pipeline/knowledge/content_bot/*.md` |

## Identity

| Concern | File |
|---|---|
| Lena photo identity resolution — element-id cleaning, expected/forbidden elements, manual-override fail-closed guard, allowed reference-mode contract | `pipeline/identity/lena_identity.py` |
| Filesystem-native front door to the above (docs only, no logic) | `pipeline/agents/lena/40_identity_continuity/` |

`lena_identity.py` consolidated logic previously duplicated across
`kling_apilena_api_executor.py`, `tools/lena_preflight.py`, and
`lena_production_job.py` (Batch 2, 2026-07-05). Those three files now delegate to
it; they are not independent sources of identity truth even though identity-related
code still physically touches them.

## Execution

| Concern | File |
|---|---|
| Real live Kling image-submission executor | `pipeline/kling_apilena_api_executor.py` |
| Prompt construction (positive + negative, compaction, garment-obedience lock) | `pipeline/prompting/lena_prompt_brain.py` |
| Daily production orchestration | `pipeline/lena_production_job.py` |
| Contract/queue readiness gate | `tools/lena_preflight.py` |
| Machine-readable live-path manifest | `pipeline/config/lena_live_path_manifest_v1.json` |
| Human-readable routing legend for `tools/` | `tools/LEGACY_PROVIDER_SURFACES.md` |

## QA

| Concern | File |
|---|---|
| Structured QA verdict schema (checklist, pass/fail/unreviewed) | `pipeline/qa/lena_photo_qa.py` |
| Read-only proof-review helper — assembles everything needed to review one slot (image, submit payload, prompt receipt, QA result, slot metadata) | `tools/lena_review_proof_render_v1.py` |
| Per-slot QA verdict artifacts | `pipeline/asset_review/lena/<date>/<slot_id>_qa.json` |

`lena_photo_qa.py` formalizes what used to be prose judgments written by hand into a
machine-readable record. It does not run QA itself — no automated vision model is
wired in; a human or Claude fills in the checklist after viewing the actual image.
It never overwrites an existing QA file — stale verdicts must be explicitly
replaced, not silently left in place.

## Precedence rule when files conflict

1. `NEXT_SESSION_START.md` and the master file's §0 — most current, updated every
   session close.
2. The named authoritative module itself (read the code, not a doc paraphrasing it).
3. `lena_live_path_manifest_v1.json` — machine-readable, deliberately kept in sync.
4. Everything else (README-style docs, `.bak_*` files, older handoffs) — treat as
   historical context only, verify before trusting.
