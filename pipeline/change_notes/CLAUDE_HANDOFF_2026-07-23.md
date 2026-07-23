# Claude Handoff - Lena Provider Retirement

This is the concise handoff for Claude or another coding agent.

## Repo

`C:\projects\ai\content_bot\lenadelapi_website_full_photo_autonomy`

## Git

- HEAD: `e23e94844ca96a187f887e25654b2c7c84ecb78b`
- Branch: detached HEAD
- State: dirty by design; provider-retirement patch is not staged or committed.

## User Intent

The user rejected the latest Lena Higgsfield output and then instructed: remove Kling Omni and OpenArt/Seedance completely. They are only using Higgsfield, but paid Lena generation through the current `text2image_soul_v2` path remains stopped until a better controlled Higgsfield path is selected offline.

## What Changed In The Dirty Patch

- Kling Omni and OpenArt/Seedance active surfaces were removed.
- Higgsfield is now the only configured Lena image-provider family.
- Video generation is disabled in policy.
- Legacy daily provider/orchestrator/scheduler entrypoints were removed.
- A provider-surface regression test was added to guard against retired provider routes returning.
- Historical runtime/audit evidence was preserved.

## Files To Treat As Intended Source Changes

Stage/review the tracked modifications and deletions shown by `git status --short`, plus:

- `tools/PROVIDER_SURFACES.md`
- `tests/test_lena_higgsfield_only_provider_surface_v1.py`

Do not stage these runtime artifacts unless Nicolas explicitly names them:

- `pipeline/approvals/lena/generation/2026-07-23/`
- `pipeline/higgsfield_debug/2026-07-23/`
- `pipeline/state/lena_engagement_demand_state_v1.json`
- `pipeline/state/lena_world_state_v1.json`
- `pipeline/strategy/`

## Verification

Use this as the current focused baseline, not a full-suite claim:

```powershell
python -B -m pytest -p no:cacheprovider tests/test_lena_higgsfield_only_provider_surface_v1.py tests/test_lena_prompt_brain_hair_and_safety_v1.py tests/test_lena_human_presence_prompt_plan_v1.py -q
```

Last result: `16 passed`.

Also reported green in this session:

- retirement changed-surface ring: `125 passed`
- canonical/prompt-brain ring: `37 passed`
- `git diff --check`
- scheduler syntax parse
- changed JSON parse check

## Current No-Go

Do not run paid provider generation. The latest generated image is rejected:

- provider job: `9a0e5ebf-40ff-4c70-823c-dfa99aa5664a`
- image: `pipeline/higgsfield_library/lena/2026-07-23/lenagate20260723e23e9484-pack000-00-photo_seed.png`
- reason: output ignored prompt constraints and produced open jeans, visible underwear/lower-abdomen exposure, body-centered crop, partially cropped face, and empty background.

## Next Safe Step

Review and commit the provider-retirement patch only. Suggested commit message:

`Retire legacy Lena provider surfaces`

After that, do offline research/planning for the next Higgsfield path. Prefer image-to-image, reference-guided, structure-controlled, or other stronger-control Higgsfield surfaces. Do not generate another image until Nicolas explicitly authorizes one paid test.
