# ITB JSON Creative Operating System V1

## Production authority

Loose prose is useful for exploration but cannot prove which creative decisions reached production. ITB therefore treats validated, versioned JSON as authority. Every artifact has a stable ID, property and episode identity, creation time, producer version, and canonical SHA-256 bindings to its upstream artifacts. A downstream hash mismatch is a blocking stale-authority error. Compiled prompts are reproducible outputs, never upstream creative sources.

Only validated JSON is executable authority. Generator output remains provisional until syntax, schema, cross-artifact, continuity, timing, diversity, novelty, platform, ceiling, user-lock, disclosure, and compilation-readiness checks pass. V1 intentionally stops before provider execution.

## Five engines

1. **Canon Engine.** Owns property identity, narrator doctrine, institutional tone, graphics, sound, comedy, recurring terminology, continuity hooks, and non-imitation boundaries. Episode learning cannot override it.
2. **World Engine.** Combines the Creative Genome, concept, world dossier, and entity sheet. It must turn impossible ideas into observable rules, geometry, materials, movement, scale, customs, hazards, and survival procedures.
3. **Story Engine.** Produces the timed Bureau script and visual sequence from validated upstream authority. It preserves user locks and separates narration meaning from shot execution.
4. **Production Engine.** Deterministically compiles the visual sequence into a provider-neutral generation plan and then an execution-disabled compiled-request interface. No LLM, random choice, current time, environment state, provider call, or absolute machine path participates.
5. **Learning Engine.** Records platform evidence, confidence, allowed conclusions, and prohibited overfitting. It may influence later concept selection but cannot rewrite canon, user locks, historical ledger entries, or safety rules.

## Creative Genome

The Creative Genome is machine-comparable episode DNA. Comparison fields use normalized slugs, governed enums, tag sets with unordered semantics, and integer basis-point weights totaling 10,000. The twelve V1 dimensions are environment family, hazard family, entity silhouette, scale, palette, camera grammar, humor mechanism, opening structure, ending reveal, instruction verbs, emotional flavor, and thumbnail grammar.

The novelty governor compares exact normalized values, reports every overlap, checks active lockouts, rejects more than two repeated major dimensions against either previous-two episode, and reports weighted similarity across at most thirty prior episodes. A high score can request revision, but deterministic comparison does not claim to replace semantic creative review.

## Authority order

```text
Business and user intent
  -> Bureau canon
  -> Creative Genome and concept card
  -> World dossier and entity sheet
  -> Audio plan and episode script
  -> Visual sequence
  -> deterministic validation and continuity/novelty analysis
  -> provider-neutral generation plan
  -> execution-disabled compiled request
  -> future generation, edit, QA, publishing and learning
```

No arrow points upward. Episode manifests and learning records preserve evidence but do not become creative sources. The machine-readable edge list in `dependency_map_v1.json` is acyclic and tested.

## Schema map

| Authority | Schema | Primary role |
|---|---|---|
| Canon | `bureau_canon_v1.schema.json` | Property identity and invariants |
| Canon/Concept | `bureau_creative_genome_v1.schema.json` | Normalized creative DNA |
| Concept | `bureau_concept_card_v1.schema.json` | Hook, impossible rule, intent and locks |
| World | `bureau_world_dossier_v1.schema.json` | Observable world mechanics |
| World | `bureau_entity_sheet_v1.schema.json` | Entity form, behavior and continuity |
| Story | `bureau_audio_plan_v1.schema.json` | Narrator, timing, music and sound |
| Story | `bureau_episode_script_v1.schema.json` | Timed narration and Bureau procedure |
| Story/Production | `bureau_visual_sequence_v1.schema.json` | Exact shot semantics and timing |
| Production | `bureau_generation_plan_v1.schema.json` | Provider-neutral asset requests |
| Disposable output | `bureau_compiled_request_v1.schema.json` | Ordered prompts and disabled interface payloads |
| Evidence | `bureau_episode_manifest_v1.schema.json` | Future asset, job, cost and lineage evidence |
| QA | `bureau_episode_qa_v1.schema.json` | Machine, semantic and optional-human separation |
| Continuity | `bureau_continuity_ledger_v1.schema.json` | Thirty-episode memory and lockouts |
| Learning | `bureau_episode_learning_v1.schema.json` | Metrics and bounded conclusions |

`common_defs_v1.schema.json` is the single local fragment authority for IDs, timestamps, hashes, upstream references, locks, disclosures, normalized tags, and genome snapshots. All `$ref` values are local and network resolution is forbidden.

## Canonical JSON and hashes

`contracts.canonical_json_bytes()` is the only canonicalization function. Its contract is UTF-8 without BOM, Unicode preserved, lexicographically sorted object keys, comma/colon separators without insignificant whitespace, and no line endings in serialized output. Booleans, null, strings, arrays, objects, and integers are supported. Floats are forbidden; exact durations use milliseconds, money uses cents, and ratios use basis points. Formatting, indentation, key order, BOM-free line ending choice, and disk representation do not affect canonical hashes.

Artifact SHA-256 covers the complete canonical object, including authority timestamps. The compiled-request fingerprint intentionally excludes only `compilation_timestamp` and its own `deterministic_compilation_fingerprint`. A changed creative field changes its artifact hash, invalidates downstream bindings, and requires deterministic recompilation.

## Generator versus compiler

The nine generator packs may be used by an LLM to draft schema-shaped JSON in `full_autonomous`, `guided`, or `co_written` mode. They must preserve locks, cite upstream IDs, state assumptions, and output JSON only. They cannot validate themselves, calculate trusted hashes, mutate the ledger, or create execution authority.

The four compiler functions use explicit ordered field templates. They do not invoke an LLM or reinterpret fields:

1. `compile_world_to_script_context`
2. `compile_script_to_visual_context`
3. `compile_visual_to_generation_plan`
4. `compile_plan_to_request`

The same authoritative inputs produce byte-equivalent canonical outputs. Pilot 001's checked-in generation plan and compiled request were produced through these functions.

## User input modes

`full_autonomous` permits candidate creation within canon and lockouts. `guided` binds explicit user choices while the system fills unbound fields. `co_written` treats user-authored material as locked authority and only completes explicitly delegated fields. Every mode passes through the same deterministic validation; no mode is a bypass.

## Validation stages

The governed loader handles JSON syntax, schema/type/version, artifact identity, local path containment, traversal, symlink/junction escape, and precise structured errors. Episode validation then checks cross-file hashes and cycles, property/episode identity, world specificity, script/audio fit, shot count and duration, required shot roles, diversity, entity states and tokens, plan neutrality, ceiling constraints, user locks, disclosures, novelty, and compiled fingerprints.

Semantic visual quality, narrator performance, world believability, and Bureau identity remain explicit evaluator fields. Deterministic success never fabricates semantic approval.

## Folder structure

```text
interstitial_travel_bureau/
  contracts.py       canonical JSON, errors, counters, atomic writes
  artifacts.py       schemas, governed loading, local references, authority graph
  validation.py      deterministic episode rules
  novelty.py         normalized thirty-episode comparison
  compilers.py       four pure ordered compilation stages
  schemas/           fourteen artifact schemas plus common definitions
  generators/        shared generator contract plus nine instruction packs
  pilots/pilot_001/  complete generic-pipeline example
  fixtures/invalid/  adversarial mutation catalog
  documentation/     architecture and dependency maps
```

Thin commands live in `tools/itb_*_v1.py`; business logic does not.

## Creating a new episode

1. Copy only the artifact shape, not Pilot 001 content.
2. Produce provisional canon reference, genome, concept, world, entity, audio, script, and visual JSON using the schemas and instruction packs.
3. Bind canonical upstream hashes in one direction and run `itb_validate_episode_v1 --validate-only` as artifacts become complete.
4. Add the proposed continuity entry, run `itb_novelty_check_v1` against the governed ledger, and revise any rejected genome.
5. Run `itb_compile_episode_v1 --validate-only`; the validated ledger is SHA-bound into the neutral plan. Then supply an explicit output directory to materialize the neutral plan and disabled request.
6. Add the QA plan, pre-generation manifest, and awaiting-publication learning record. Validate the complete fourteen-artifact root.
7. Stop. Provider execution requires a separate future authority and is absent from V1.

## Future providers

A future adapter may consume only validated `bureau_generation_plan_v1` or regenerated `bureau_compiled_request_v1` data. It must map capability requirements and the minimal request interface to a provider without changing canon, world rules, script meaning, shot semantics, genome, continuity, or user locks. Provider names, models, credentials, account IDs, environment files, execution, polling, and receipts are intentionally absent now.

## Reuse for Lena video later

The reusable ideas are canonical JSON, upstream SHA bindings, loader safety, validator/compiler separation, explainable novelty, and disposable compiled requests. Lena can later adopt equivalent neutral contracts in her own namespace. ITB canon, narrator, terminology, entity identity, continuity ledger, prompts, and episode data must never be imported into Lena; Lena identity, HPE, scheduler, publishers, provider policy, queues, and runtime evidence must never be imported into ITB.

## Error contract

Every error includes a stable code, stage, message, blocking/advisory severity, and applicable artifact ID, JSON pointer, expected/actual values, source file, and correction. Principal codes are `json_syntax_invalid`, `schema_*`, `artifact_path_traversal`, `artifact_path_escape`, `artifact_symlink_forbidden`, `upstream_artifact_missing`, `upstream_sha256_mismatch`, `circular_artifact_reference`, `property_id_mismatch`, `episode_id_mismatch`, `generic_world_description`, `narration_too_long`, `shot_duration_fit_failed`, `shot_diversity_insufficient`, `entity_continuity_token_invalid`, `entity_state_conflict`, `user_lock_changed`, `commercial_disclosure_missing`, `imitation_or_copy_request`, `provider_neutrality_violation`, `creative_genome_novelty_rejected`, `compiled_fingerprint_mismatch`, `output_collision`, and `cli_arguments_invalid`.

## Deliberately deferred

V1 has no provider adapter, media generation, semantic evaluator implementation, voice/music system, scheduler, publisher, metrics ingestion, schema migration framework, plugin system, database, or generic workflow engine. Those are deferred until a real consumer proves the need. The standard-library schema validator implements only keywords used by the repository-controlled V1 schemas; adding new schema keywords requires matching tests before use.
