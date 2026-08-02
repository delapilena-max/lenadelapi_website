# ITB Dependency Map V1

Authority flows one way:

```text
schemas + canon
  -> contracts/artifact loader
  -> deterministic validation
  -> continuity and novelty
  -> deterministic compilers
  -> provider-neutral plan
  -> execution-disabled request interface
```

Library imports are acyclic: `contracts` imports no ITB module; `artifacts` imports `contracts`; `novelty` imports `contracts`; `validation` imports `artifacts`, `contracts`, and `novelty`; `compilers` imports `artifacts`, `contracts`, and `validation`. CLIs import these public modules and `itb_cli_support_v1`; no library imports a CLI.

Generators may use an LLM but produce provisional JSON only. Validators, novelty analysis, compilers, loaders, and CLIs prohibit provider/network activity. Only `atomic_write_json` may mutate files, and only after an explicit output path; validate-only paths never call it. The complete component and edge inventory is `dependency_map_v1.json` and is tested for cycles and coverage.
