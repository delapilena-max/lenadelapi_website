# Lena Reels execution-claim crash-recovery runbook

Scope: `tools/lena_governed_publish_pipeline_v1.py`, Reels lane only. Does not
apply to the photo lane.

## Background

Every Reels publish attempt (manual or autonomous) creates one atomic,
single-use **execution claim** file immediately before the one real network
action this pipeline performs (`publish_post()` -> Instagram Graph API). The
claim has three states:

```
claimed  -->  published_pending_closure  -->  closed
```

- `claimed`: the claim file exists; `publish_post()` has not yet been
  confirmed to return.
- `published_pending_closure`: `publish_post()` returned successfully and
  the result (including `instagram_media_id`) is recorded on the claim.
  Fingerprint-store, sidecar, and claim-closure bookkeeping have not run
  yet.
- `closed`: bookkeeping is complete. Terminal state.

The claim file itself is never deleted or "released" by this pipeline. Once
an asset is claimed, that fact is permanent, by design -- recovery always
moves a claim forward through its states, never removes it.

## The recovery tool

```
python tools/lena_governed_publish_pipeline_v1.py --mode reconcile-claim --claim-path <path to *.claim.json>
```

This is read-only inspection unless the claim is already in
`published_pending_closure`, in which case it also finishes bookkeeping
(fingerprint store + sidecar + claim closure) using only the claim's own
already-recorded result. **It never calls `publish_post()`.** There is no
"retry" mode anywhere in this tool -- retrying a Reels publish is always a
new, separate, independently-claimed and independently-approved attempt,
never an automatic action taken on an old claim.

`reconcile_stale_execution_claim()` returns one of three recommendations:

| action | meaning |
|---|---|
| `wait` | Claim is `claimed` and younger than 900s. A publish attempt may still be in flight. Re-check later. |
| `complete_pending_closure` | Claim is `published_pending_closure`. `publish_post()` already succeeded (a real `instagram_media_id` is recorded). Safe to finish bookkeeping with zero network calls. |
| `manual_verification_required` | Claim is `claimed` and at least 900s old, with no recorded result. **Not safe to infer anything locally.** |
| `none` | Claim is already `closed`. Nothing to do. |

## Scenario 1 -- crash before upload

**Symptom:** claim file exists, `state: "claimed"`, `publish_result: null`.
The process crashed before `publish_post()` was ever called.

**Procedure:**
1. Run `--mode reconcile-claim`. If the claim is younger than 900s, it will
   say `wait` -- do nothing yet, re-check shortly.
2. Once past 900s it will say `manual_verification_required`. Open the
   Instagram account directly (or run
   `tools/lena_reels_live_preflight_readonly.py` if useful for context) and
   check whether this asset's caption was actually posted.
3. If it was **not** posted: the asset was never published. Investigate/fix
   the crash cause, then start a **new** publish attempt for this asset from
   scratch (new proof gate run, new claim). Do not touch the old claim file.
4. If it **was** posted (rare for this scenario, but check anyway -- see
   Scenario 2): do not re-publish. Manually record the real
   `instagram_media_id`/`permalink` you observe, then hand-finish
   bookkeeping the same way `complete_pending_closure()` would (mark the
   fingerprint published, set the sidecar's `instagram_published: true`,
   set the claim to `closed`) -- or simplest, use
   `mark_claim_published()` + `--mode reconcile-claim` again so the normal
   `complete_pending_closure` path does it for you.

## Scenario 2 -- crash after container creation (before any local result)

**Symptom:** identical to Scenario 1 from this pipeline's point of view.
The Instagram Graph API "create container, then publish container" flow
means a container can exist server-side (or the publish call can have
actually succeeded) even though the local process crashed before writing
anything to the claim. **Local state alone cannot distinguish this from
Scenario 1.**

**Procedure:** identical to Scenario 1, step 2 onward. This is exactly why
`manual_verification_required` exists instead of a heuristic guess -- the
account itself is the only source of truth here.

## Scenario 3 -- crash after publish but before fingerprint/closure write

**Symptom:** claim file exists, `state: "published_pending_closure"`,
`publish_result` contains a real `instagram_media_id`. The real, one-time
network action already succeeded; only local bookkeeping is unfinished.

**Procedure:**
1. Run `--mode reconcile-claim`. It will report
   `complete_pending_closure` and finish the job automatically: adds the
   clean derivative's fingerprint to the shared publish-state store, sets
   `instagram_published: true` (with the recorded `instagram_media_id`,
   `permalink`, caption, and timestamp) on the asset's `*.status.json`
   sidecar, and marks the claim `closed`.
2. No further action needed. `publish_post()` is never called during this.

## Scenario 4 -- stale claim reconciliation without duplicate posting

This is the umbrella case Scenarios 1-3 all fall under. The one invariant
that must never be violated: **reconciliation must never cause a second
real publish call for an asset that might already be live.** Concretely:

- `reconcile_stale_execution_claim()` is read-only and imports nothing from
  `pipeline/publisher/instagram_graph_adapter.py`.
- `complete_pending_closure()` only ever reads `publish_result` off the
  claim that was written *before* this recovery ran; it cannot call
  `publish_post()` even by mistake, because it never imports it.
- There is no code path anywhere in `run_publish()`, `claim_execution()`,
  `reconcile_stale_execution_claim()`, or `complete_pending_closure()` that
  re-claims or re-uses an existing claim file's slot for a fresh
  `publish_post()` call. A genuinely new attempt always requires a new
  `claim_execution()` call, which itself will refuse if any claim file
  (in any state) already exists for that `slot_id` -- so an operator
  cannot accidentally double-post through the normal tooling. Retrying
  after `manual_verification_required` confirms "not actually posted"
  requires deliberately choosing a fresh `slot_id`/asset context, which is
  an explicit, visible decision, not something the tool does silently.

## Quick reference

```
# Inspect + auto-complete a claim if safe to do so (never calls publish_post):
python tools/lena_governed_publish_pipeline_v1.py --mode reconcile-claim --claim-path <path>

# Standing authorization lifecycle (lane-level, not per-asset):
python tools/lena_governed_publish_pipeline_v1.py --mode issue-standing-authorization --ttl-seconds 2592000
python tools/lena_governed_publish_pipeline_v1.py --mode revoke-standing-authorization
```
