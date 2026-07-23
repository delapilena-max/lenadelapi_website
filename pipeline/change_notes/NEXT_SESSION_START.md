# Next Session Start - Lena Provider Surface Retirement

Updated: 2026-07-23
Repo: `C:\projects\ai\content_bot\lenadelapi_website_full_photo_autonomy`

## Current Git State

- HEAD: `e23e94844ca96a187f887e25654b2c7c84ecb78b`
- Branch: detached HEAD
- Worktree: intentionally dirty; do not assume clean state.
- No staging or commit has been performed for the provider-retirement patch.

## Primary Objective

Retire Kling Omni and OpenArt/Seedance from Lena's active codebase surfaces. The user explicitly wants Higgsfield to be the only configured image provider.

## Current Operational State

- No live generation is authorized.
- No Higgsfield paid generation should be run in the next session.
- No Anthropic visual QA, queue mutation, publishing, scheduler activation, or `.env` access is authorized.
- The latest Higgsfield `text2image_soul_v2` Lena output was a hard human rejection and must not be queued or published.
- Higgsfield remains the only configured image-provider family, but the current Lena paid `text2image_soul_v2` lane is stopped pending an offline replacement/provider-boundary decision.

## Human-Rejected Output To Preserve

- Provider job: `9a0e5ebf-40ff-4c70-823c-dfa99aa5664a`
- Rejected image: `pipeline/higgsfield_library/lena/2026-07-23/lenagate20260723e23e9484-pack000-00-photo_seed.png`
- Rejection reasons: open/unbuttoned jeans, underwear/lower-abdomen exposure, body-centered framing, partially cropped face, plain empty background, weak scene/brand presentation.
- Do not delete or overwrite this evidence.

## Intended Dirty Source Changes

The current uncommitted patch removes retired provider surfaces and keeps Higgsfield as the sole active provider.

Deleted tracked surfaces include:

- `pipeline/config/lena_kling_contract.json`
- `pipeline/prompt_banks/lena/kling_omni_daily_scene_bank_v1.json`
- `pipeline/identity/lena_identity.py`
- `pipeline/workorders/lena/README_BODYLOCK_PRODUCTION_RULES_2026-06-24.md`
- `tools/generation/lena_apply_bodylock_to_daily_batch_v1.py`
- `tools/generation/lena_run_daily_bodylock_live_v1.py`
- `tools/generation/lena_run_daily_kling_omni_live_v1.py`
- `tools/strategy/lena_build_kling_payload_dryrun_v1.py`
- `tools/strategy/lena_submit_kling_payload_v1.py`
- `tools/run_lena_provider_only_daily_v1_5_2.py`
- `tools/wire_lena_v1_5_openart_seedance_provider.py`
- `tools/lena_daily_orchestrator_v1.py`
- `tools/lena_publish_packet_director_generate_v2_4.py`
- `tools/run_lena_generate_daily.ps1`
- `tools/lena_influencer_node_v1_3.py`
- `tools/LEGACY_PROVIDER_SURFACES.md`

New intended files:

- `tools/PROVIDER_SURFACES.md`
- `tests/test_lena_higgsfield_only_provider_surface_v1.py`

Important untracked runtime artifacts remain under:

- `pipeline/approvals/lena/generation/2026-07-23/`
- `pipeline/higgsfield_debug/2026-07-23/`
- `pipeline/state/lena_engagement_demand_state_v1.json`
- `pipeline/state/lena_world_state_v1.json`
- `pipeline/strategy/`

Do not stage runtime artifacts unless the user explicitly asks for a specific artifact.

## Verification Already Run

Final focused provider-retirement smoke:

```powershell
python -B -m pytest -p no:cacheprovider tests/test_lena_higgsfield_only_provider_surface_v1.py tests/test_lena_prompt_brain_hair_and_safety_v1.py tests/test_lena_human_presence_prompt_plan_v1.py -q
```

Result: `16 passed`.

Additional focused rings reported green before this handoff:

- Changed-surface ring: `125 passed`
- Canonical/prompt-brain follow-up: `37 passed`
- `git diff --check`: passed, with CRLF warnings only
- Scheduler PowerShell parser: passed
- Changed JSON parse check: passed

A broader mixed ring had unrelated/stale failures before the final retirement smoke. Do not claim the full suite is green for this dirty patch.

## Next Safe Action

1. Review the dirty provider-retirement patch and confirm only Kling Omni and OpenArt/Seedance retirement changes are included.
2. Run the final focused smoke above if freshness is needed.
3. Commit only the intended source/test/doc changes; do not include runtime artifacts under `pipeline/strategy`, `pipeline/higgsfield_debug`, `pipeline/approvals`, or `pipeline/state`.
4. After that, plan the replacement Higgsfield generation path offline. Do not run paid generation.

## Hard Prohibitions For Next Session

- Do not run live generation.
- Do not call Higgsfield.
- Do not call Anthropic.
- Do not queue or publish the rejected image.
- Do not activate scheduler.
- Do not print or edit `.env`.
- Do not restore Kling Omni, OpenArt, Seedance, BodyLock, or legacy video-provider paths.
- Do not stage untracked runtime evidence by accident.
