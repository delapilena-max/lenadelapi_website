# Lena Provider Surfaces

Higgsfield is the only supported Lena generation provider in this repository.
The rejected unrestricted `text2image_soul_v2` route is retired for new Lena
generation. The active replacement contract is reference-guided
`soul_cinema_studio`: it requires Lena's verified Soul plus one SHA-bound
source image and preserves the approved prompt bytes with
`enhance_prompt=false`. Keeping the executor code does not authorize a paid
call.

## Active photo-generation surfaces

| Entry point | Purpose |
|---|---|
| `pipeline/higgsfield_lena_api_executor.py` | Validates an approved handoff and performs one bounded Higgsfield generation |
| `tools/lena_full_photo_autonomy_v1.py` | Controlled photo-autonomy entry point |
| `tools/lena_bounded_live_cycle_v1.py` | Bounded live-cycle orchestration and cost controls |
| `tools/strategy/lena_build_next_live_image_handoff_v1.py` | Builds the exact approved Higgsfield handoff |
| `tools/lena_higgsfield_generation_approval_v1.py` | Validates manual generation approval |
| `tools/lena_higgsfield_standing_autonomy_generation_approval_v1.py` | Validates controlled standing-autonomy generation approval |

The verified Lena Soul id and authoritative source-image path/SHA must be
present in the handoff, approval, and exact subprocess command binding.
Provider submission remains fail-closed on prompt, Soul, source image,
approval, claim, or lineage mismatch.

## Source-only video compilation surface

Lena video creative authority lives under
`pipeline/media_properties/lena/video/`. The deterministic compiler targets
the model constrained by that source-only authority only when direct binding to
Character Element `6a842337-ef20-4cb9-a0ff-04fa5eb8f8d3` is supported. It
produces a validated provider-neutral plan and an execution-disabled compiled
request for exactly 8 seconds at 720p portrait 9:16, with a 36-credit aggregate
ceiling. The exact compiled prompt must also remain within the active
4,096-character Higgsfield repository execution policy; automatic truncation or
shortening is forbidden.

| Entry point | Purpose |
|---|---|
| `tools/lena_video_validate_v1.py` | Validates the complete local Lena video authority chain without network access or writes |
| `tools/lena_video_compile_higgsfield_v1.py` | Deterministically compiles local validated JSON; writes only when an explicit output directory is supplied |

There is no video provider executor in this V1. A compiled request never
authorizes execution, attempts, retries, spend, generation, or publication.
Any future provider action requires separate authority bound to the exact
validated request hash.

## Unsupported generation surfaces

No alternate image provider or executable video provider surface is supported.
Video generation remains disabled in
`pipeline/config/lena_generation_policy.json` until a separate execution path,
attempt count, and request-bound authorization are explicitly approved.
