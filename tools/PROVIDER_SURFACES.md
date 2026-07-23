# Lena Provider Surfaces

Higgsfield is the only supported Lena generation provider in this repository.
Paid Lena generation through `text2image_soul_v2` remains stopped after the
human rejection of provider job `9a0e5ebf-40ff-4c70-823c-dfa99aa5664a`.
Keeping the executor code does not authorize another paid call.

## Active photo-generation surfaces

| Entry point | Purpose |
|---|---|
| `pipeline/higgsfield_lena_api_executor.py` | Validates an approved handoff and performs one bounded Higgsfield generation |
| `tools/lena_full_photo_autonomy_v1.py` | Controlled photo-autonomy entry point |
| `tools/lena_bounded_live_cycle_v1.py` | Bounded live-cycle orchestration and cost controls |
| `tools/strategy/lena_build_next_live_image_handoff_v1.py` | Builds the exact approved Higgsfield handoff |
| `tools/lena_higgsfield_generation_approval_v1.py` | Validates manual generation approval |
| `tools/lena_higgsfield_standing_autonomy_generation_approval_v1.py` | Validates controlled standing-autonomy generation approval |

The verified Lena Soul id must be present in the handoff, approval, and exact
subprocess command binding. Provider submission remains fail-closed on prompt,
Soul, approval, claim, or lineage mismatch.

## Unsupported generation surfaces

No alternate image or video provider is supported. Video generation is disabled
in `pipeline/config/lena_generation_policy.json` until a separate provider path
is explicitly selected and approved.
