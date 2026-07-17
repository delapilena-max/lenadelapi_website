# Human Presence Engine Operations

## Architecture

The Human Presence Engine is a deterministic, evidence-only lane:

- candidate ranking scores prompt-plan alignment;
- selected-candidate validation binds the chosen candidate to its deterministic dry-run path;
- prompt-plan compilation turns the contract into the active prompt text;
- prompt assembly embeds the compiled human-presence plan into the provider-facing prompt package;
- output QA validates integrity bindings and semantic observations;
- lifecycle summaries record what happened without authorizing publish, retry, or reconciliation;
- closure verification gathers the runtime evidence into a canonical report.

The HPE semantic layer is evidence-only. It must not change photo QA authority, approval, rejection, retry, publishing, or reconciliation.

## Controlled Proof

Suggested command:

```bash
python tools/lena_run_hpe_controlled_proof_v1.py \
  --date 2026-07-17 \
  --slot-id closure-proof-slot-00 \
  --image-index 0 \
  --manifest C:/path/to/manifest.json \
  --image C:/path/to/image.png \
  --output-root C:/path/to/output \
  --controlled-proof \
  --dry-run
```

The command can also accept `--candidate-input` when the operator already has a selected-candidate decision artifact.

Expected outputs:

- selected-candidate evidence;
- compiled prompt-plan evidence;
- final prompt package evidence;
- output QA artifact;
- lifecycle summary evidence;
- closure report.

Acceptance criteria:

- no paid provider call during the default path;
- exact candidate binding is preserved;
- prompt influence is observable through the compiled plan and provider-facing prompt;
- artifact writes are atomic and conflict-safe.

## Live Semantic Proof

Controls:

- `--live-presence-semantic-review`
- `--semantic-provider`
- `--semantic-model`
- `--semantic-timeout-seconds`

Rules:

- default is disabled;
- one semantic provider call per image when enabled;
- default timeout is `30.0`;
- `max_retries=0`;
- no semantic retry;
- the provider request must not leak local paths;
- the semantic result is written into the canonical HPE v2 artifact;
- provider failures remain bounded, while programmer defects propagate.

## Ordinary-Lane Proof

The same proof command runs the ordinary lane when `--controlled-proof` is omitted.

Difference from controlled proof:

- no controlled-proof override;
- normal candidate selection;
- normal prompt assembly;
- same evidence-only semantic boundary;
- no hidden proof-only authority.

## Closure Criteria

HPE closure is only satisfied when:

- focused and full tests pass;
- controlled proof passes;
- ordinary proof passes;
- live semantic proof is supported and bounded;
- authority boundaries remain unchanged across semantic outcomes;
- closure verification reports no blocking findings.

