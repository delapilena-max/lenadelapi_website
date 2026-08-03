# Authoritative Surfaces - content_bot / Lena

Purpose: identify the source of truth for permanent doctrine, current state,
and the active Lena production surfaces. When this file disagrees with current
repo reality, fix this file rather than guessing.

Updated for current main `824f58615eee41e15b93f72d71bb8b8241fcf169`.

## Doctrine And Continuity

| Concern | File |
|---|---|
| Master system prompt / permanent doctrine | `pipeline/knowledge/content_bot/CONTENT_BOT_MASTER_SYSTEM_PROMPT_V1_4.md` |
| Session start / current blocker / next step | `pipeline/change_notes/NEXT_SESSION_START.md` |
| Lena video architecture / canonical A-N authority | `pipeline/media_properties/lena/video/documentation/LENA_VIDEO_JSON_PRODUCTION_SYSTEM_V1.md` |
| Lena video source, validation, and compilation authority | `pipeline/media_properties/lena/video/` |
| Fresh Lena video creative source builder | `pipeline/media_properties/lena/video/fresh_creative_generation.py` |

## Identity

| Concern | File |
|---|---|
| Lena photo identity / Soul and reference lineage checks | `pipeline/identity/` |
| Lena video Character Element authority | `pipeline/media_properties/lena/video/contracts.py` and `pipeline/media_properties/lena/video/schemas/lena_video_character_authority_v1.schema.json` |
| Filesystem-native identity front door | `pipeline/agents/lena/40_identity_continuity/` |

## Execution And Prompt Boundaries

| Concern | File |
|---|---|
| Canonical Lena video validator | `pipeline/media_properties/lena/video/validation.py` |
| Canonical Lena video compiler | `pipeline/media_properties/lena/video/compiler.py` |
| Lena still-photo prompt contract | `pipeline/prompting/lena_canonical_prompt_contract_v1.py` |
| Lena still-photo prompt construction | `pipeline/prompting/lena_prompt_brain.py` |
| Higgsfield photo executor | `pipeline/higgsfield_lena_api_executor.py` |

## QA And Publication Evidence

| Concern | File |
|---|---|
| Structured photo QA disposition | `tools/lena_photo_qa_disposition_v1.py` |
| Read-only proof-review helper | `tools/lena_review_proof_render_v1.py` |
| Video pre-generation QA schema | `pipeline/media_properties/lena/video/schemas/lena_video_qa_v1.schema.json` |
| Per-slot QA/runtime evidence | `pipeline/asset_review/lena/`, `pipeline/higgsfield_debug/`, and governed runtime roots named by receipts |

Runtime evidence is immutable historical evidence unless a current governed
tool explicitly issues a new append-only artifact. Do not rewrite generated
outputs, receipts, cost records, authorizations, QA findings, or publication
records to make state look cleaner.

## Precedence Rule When Files Conflict

1. Nic's latest explicit instruction.
2. `pipeline/knowledge/content_bot/CONTENT_BOT_MASTER_SYSTEM_PROMPT_V1_4.md` for permanent doctrine.
3. `pipeline/change_notes/NEXT_SESSION_START.md` for current operating state and next step.
4. Current node-specific authoritative contracts and schemas.
5. Current verified code and runtime evidence.
6. Historical change notes, older handoffs, comments, old tests, and prior agent conclusions.

Durable operating rules belong in the master system prompt or node authority.
Temporary operational facts belong in `pipeline/change_notes/NEXT_SESSION_START.md`.
Do not ask Nic which internal document owns a rule; inspect the repo and update
the correct authority.
