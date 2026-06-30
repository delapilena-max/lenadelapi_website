# Legacy Provider Surfaces

This document is the routing legend for the `tools/` directory.

## Active Lena generation path (Kling-only)

These are the canonical surfaces for current work:

| Entry point | Purpose |
|---|---|
| `lena_strategy_autonomy_run_v1.py` | Top-level strategy + Meta refresh + dry-run prep |
| `lena_daily_orchestrator_v1.py` | Orchestrator with strategy gate enforcement |
| `strategy/lena_run_strategy_autonomy_prep_v1.py` | Full dry-run prep stack |
| `strategy/lena_submit_kling_payload_v1.py` | Live Kling image submit |
| `run_lena_strategy_autonomy.ps1` | Windows wrapper for the top-level runner |

Provider policy: `pipeline/influencer_nodes/lena/provider_router.json`

## Legacy surfaces — blocked (require `--allow-legacy-openart-seedance`)

These files route work to OpenArt or Seedance, which are no longer the active Lena path.
They will refuse to run without an explicit override flag and should not be used for new work.

| File | Was used for |
|---|---|
| `lena_route_provider_v1_5.py` | Routed workorders to OpenArt/Seedance |
| `run_lena_provider_only_daily_v1_5_2.py` | Ran the full legacy OpenArt/Seedance daily pipeline |
| `wire_lena_v1_5_openart_seedance_provider.py` | Patched `run_lena_generate_daily.ps1` to insert the legacy provider steps |
| `generation/lena_generation_adapter_interface_v1.py` | Planned OpenArt/Seedance multi-scene keyframe pipeline |

## Legacy surfaces — named but not blocked

These files have OpenArt or Seedance in their names or logic but do not route live work.
They are preserved as historical context. Do not treat them as active architecture.

| File | Notes |
|---|---|
| `lena_prepare_openart_seedance_workorders_v1_5.py` | Built manual workorder exports for OpenArt/Seedance |
| `lena_enhance_openart_workorders_v1_5_2.py` | Enhanced those workorders |
| `lena_cleanup_openart_seedance_workorders_v1_5_3.py` | Cleaned up old workorder files |
| `lena_import_openart_seedance_outputs_v1_5_1.py` | Imported outputs from OpenArt/Seedance |
| `lena_validate_openart_anchor_v1_5_2.py` | Validated OpenArt anchor config |
| `lena_openart_anchor_status_v1_5_2.py` | Reported anchor status |
| `lena_openart_prompt_cleanup_status_v1_5_3.py` | Reported prompt cleanup status |
| `lena_provider_status_v1_5.py` | Legacy provider status report |
| `lena_validate_provider_layer_v1_5.py` | Validated the OpenArt/Seedance provider layer |
| `lena_validate_provider_import_v1_5_1.py` | Validated asset imports from legacy providers |
| `lena_init_provider_import_v1_5_1.py` | Initialized legacy provider import flow |
| `lena_control_panel_v1_5_4.py` | Legacy control panel for OpenArt/Seedance ops |
| `lena_validate_control_panel_v1_5_4.py` | Validated that control panel |
| `lena_autonomous_asset_generation_controller_v1.py` | Controller preview for OpenArt/Seedance generation jobs |
| `generation/lena_provider_adapter_shell_v1.py` | Provider adapter shell for legacy stack |
| `generation/lena_kling_pipeline_readiness_v1.py` | Early Kling readiness checker (pre-strategy era) |
| `generation/lena_kling_request_payload_preview_v1.py` | Early Kling payload preview (pre-strategy era) |

## Pipeline data — historical only

`pipeline/provider_workorders/openart_seedance/` and related subdirectories contain
archived workorder JSON from the OpenArt/Seedance era. These are read-only historical
artifacts. The active workorder and publish surface is under `pipeline/publishing/lena/`.
