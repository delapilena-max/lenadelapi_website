# Claude Handoff - Lena Reference-Guided Higgsfield Integration

## Repo

`C:\projects\ai\content_bot\lenadelapi_website_full_photo_autonomy`

## Git

- HEAD: `1fbd796b184f01faac0882926e59dbc97c822e8e`
- Branch: detached HEAD
- State: dirty by design with an uncommitted replacement integration.

## User Intent

Higgsfield is the only image provider. The rejected unrestricted `text2image_soul_v2` path must not be used again for Lena. Marketing Studio is not used. The replacement must still make pictures, with stronger identity and composition control.

## Selected Replacement

Use Higgsfield `soul_cinema_studio` with:

- exact Lena Soul ID `e45ec580-a6db-4063-a9b2-f9163856daae`
- exactly one SHA-bound `image_references` source
- source `pipeline/higgsfield_library/lena/2026-07-09/prompt_isolation_tests/readypack0709-pack004-08-wardrobe-test-c_seed.png`
- source SHA-256 `7649a7ab360832390eac0e5f06ed7bb4f21d941f31e57201ef6721c00a313ffb`
- aspect ratio `9:16`
- quality `2k`
- `enhance_prompt=false`
- the exact approved full prompt

## What The Dirty Patch Does

- Adds `pipeline/identity/lena_higgsfield_soul_cinema_contract_v1.py`.
- Switches active policy and prompt routing to reference-guided Soul Cinema.
- Binds the source image through handoff, approval, standing authorization, claim, receipt, manifest, and retry lineage.
- Fails before spend on missing, wrong, stale, malformed, or SHA-mismatched source evidence.
- Requires the verified Lena Soul ID in the provider command.
- Binds the exact local Soul/reference command to the returned job UUID.
- Keeps historical `text2image_soul_v2` evidence intact.
- Does not enable Marketing Studio, video, Kling, OpenArt, or Seedance.

## Verification

- Executor contract: `65 passed`
- Generation approval: `115 passed`
- Retry pair: `53 passed`
- Provider policy/config: `12 passed`
- Handoff builder: `16 passed, 1 unrelated test deselected`
- Cross-boundary focused ring: `14 passed`
- Controlled success path: `1 passed`
- `git diff --check`: clean

Known unrelated test issues are recorded in `pipeline/change_notes/NEXT_SESSION_START.md`; do not fix them as part of this integration.

## Runtime Evidence

Do not stage:

- `pipeline/approvals/lena/generation/2026-07-23/`
- `pipeline/higgsfield_debug/2026-07-23/`
- `pipeline/state/lena_engagement_demand_state_v1.json`
- `pipeline/state/lena_world_state_v1.json`
- `pipeline/strategy/`

## Next Safe Step

Review and commit only the intended integration. A first paid proof, if Nicolas explicitly approves it, must be one executor-only generation followed by download and human review. No Anthropic, queue, publish, or scheduler action.

## Addendum (Claude, later same day) - Soul ID rotation

The paid proof above ran (job `64084207-2b32-4ed4-bcfa-c32fa66eeedd`, slot `lenagate2026072382b626ca-pack000-00-photo`, completed, image downloaded). Nicolas reviewed the image and it did not look like Lena. Investigation (read-only `higgsfield` CLI lookups, no spend) found that `e45ec580-a6db-4063-a9b2-f9163856daae` was itself a fresh Soul (created 2026-07-20) that had never produced a generation matching Lena's known appearance -- every historically-accepted Lena image, including the pinned reference photo, traces to the older, by-then-already-retired id `90a293d7-f3af-4377-8751-3304a27b6f31`.

Nicolas then erased the account's Souls and retrained a new Lena Soul 2.0: `79119c27-64fc-47f8-9ff3-c174d12932aa` (confirmed via `higgsfield soul-id list --json`, `type: soul_2`, `status: completed`). Production code now points at this id (`pipeline/identity/lena_higgsfield_soul_cinema_contract_v1.py::CUSTOM_REFERENCE_ID`); `e45ec580` is preserved as historical fact in `pipeline/identity/lena_higgsfield_identity.py::APPROVED_CUSTOM_REFERENCE_IDS`, same as every prior rotation. This new id has not yet been proven with a live generation -- do not treat it as visually confirmed until one is run and reviewed.
