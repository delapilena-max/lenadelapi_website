# ITB Generator Contract V1

Every generator using this contract returns exactly one JSON object and no surrounding prose. Its output is provisional until the deterministic loader, schema validator, cross-artifact authority validator, and applicable domain validators pass.

Required operating modes are `full_autonomous`, `guided`, and `co_written`. The input envelope supplies `mode`, validated upstream artifact IDs, user locks, user-forbidden elements, and explicit assumptions. The output must repeat upstream artifact IDs, preserve every lock byte-for-byte at its governed JSON pointer, list assumptions, and use only fields defined by the target schema.

Generators must not calculate trusted SHA-256 values, declare their output validated, mutate a continuity ledger, compile provider requests, call providers, access a network, read secrets, or emit prose outside JSON. Unknown facts must be represented as explicit assumptions where the target schema permits them; otherwise generation must stop with a structured provisional error object.
