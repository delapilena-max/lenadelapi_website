# Lena Influencer Node Instructions

## Status

Lena is the active proof node for the creator-node operating system.

The business goal is maximized engagement that compounds into monetization and reusable infrastructure. Lena is first; future nodes, UGC deliverables, brand work, affiliate systems, and platform products depend on proving this node with quality and consistency.

## Hard Safety Rules

- Do not read, print, edit, stage, or commit `.env`, tokens, cookies, sessions, or credential files.
- Do not upload, publish, queue, schedule, or post without explicit approval from Nicolas.
- Do not change Lena identity, body, reference, or element IDs.
- Do not use, route to, optimize for, or worry about OpenArt for this project. OpenArt references are legacy artifacts only.
- Do not mark wardrobe, environments, assets, or generated outputs approved without Nicolas.
- Do not run live paid generations unless explicitly approved.
- Do not treat scratchpad scripts as production authority.
- Do not stage generated assets or ignored manifests unless Nicolas explicitly intends them to be versioned.

## Source Of Truth

Use these before inventing a new path:

- `information_hierarchy/README.md`
- `information_hierarchy/My Business/About Me.md`
- `information_hierarchy/My Business/About My Business.md`
- `information_hierarchy/My Business/About My Voice.md`
- `information_hierarchy/My Business/My Offers.md`
- `information_hierarchy/Projects/Lena Influencer Node/Source Audit.md`
- `pipeline/influencer_nodes/lena/node_manifest.json`
- `pipeline/influencer_nodes/lena/growth_monetization_manifest.json`
- `pipeline/influencer_nodes/lena/publishing_policy.json`
- `pipeline/influencer_nodes/lena/disclosure_compliance_policy_v1_9.json`
- `pipeline/influencer_nodes/lena/quality_standard.json`
- `pipeline/influencer_nodes/lena/kling_profile.json`
- `pipeline/influencer_nodes/lena/provider_router.json`
- `pipeline/influencer_nodes/lena/lena_global_character_anchor_v2_5_2.json`
- `pipeline/influencer_nodes/lena/life_engine_realism_memory_policy_v1.json`
- `pipeline/prompt_banks/lena/lena_high_caliber_prompt_recipe_bank_v1.json`
- `pipeline/prompt_banks/lena/lena_wardrobe_catalog_v1.json`
- `pipeline/prompt_banks/lena/lena_environment_catalog_v1.json`
- `pipeline/prompt_banks/lena/strong_hook_bank_v1.json`
- `pipeline/prompting/lena_prompt_brain.py`

Visual source of truth: use the Kling Character/Element named `Lena` as the visual reference for Lena. OpenArt saved-character files, OpenArt workorders, and OpenArt/Seedance provider manifests are legacy context only and must not guide active generation.

Life-engine realism rule: every generation review must teach the node why an image felt real or fake across face/skin, body, wardrobe continuity, environment detail, camera realism, and social-account believability. Do not learn only "good" or "bad"; learn the realism causes.

## Current Production-Proof Loop

**Corrected 2026-07-07 — the section below was stale.** It previously named
`hcr_001`/`wc_p045`/BODYLOCK-era scripts as the "official" live pipeline.
Those scripts and that proof loop are superseded. The actual current live
Lena photo chain, confirmed against real render/publish artifacts through
2026-07-07, is:

```
lena_prompt_brain.py
  -> kling_apilena_api_executor.py
  -> lena_photo_qa.py
  -> publish packet / queue
  -> posting_manager.py
  -> instagram_graph_adapter.py
```

This chain has produced real, verified results: a reference-by-URL Kling
photo path proven 4-for-4 photoreal/identity-matched (patched into
`kling_apilena_api_executor.py`'s `_submit_photo()`), a schema-v2 QA pass on
a real render, and one real successful Instagram publish (media id
`18154201054431808`). Treat this chain, not the scripts below, as the source
of truth for how Lena photo generation and posting actually work today.

**`tools/strategy/lena_build_content_packet_dryrun_v1.py` is currently an
upstream ideation/planning aid, not the live publish-packet builder.** It
still runs and still produces a dry-run JSON packet from the recipe/hook/
wardrobe/environment catalogs, but it is disconnected from the live chain
above: it does not read rendered images, QA schema v2 /
`production_scoring`, reference-by-URL render artifacts, queue files, or
publish receipts, and it writes to a different location
(`pipeline/strategy/lena/content_packets/`) using a different prompt schema
than the one the live executor actually submits. Its last real output on
disk predates the reference-by-URL breakthrough. It can still be useful for
early hook/recipe brainstorming, but must not be treated as "the" content
packet builder or as proof that a packet is publish-ready.

**The real missing piece is a future `90_content_packet/` folder-native
slice/tool** that builds an actual publish packet from a real, QA-passed
render (the way the one successful 2026-07-07 publish packet was built by
hand) — not yet built. Do not build it without separate explicit approval;
this note only records that the gap exists.

`tools/strategy/lena_build_kling_payload_dryrun_v1.py` and
`tools/strategy/lena_submit_kling_payload_v1.py` (the former "official Kling
payload builder" and "official submitter") are deleted from the working
tree (recoverable via git history) and were never confirmed to have
succeeded live under their own documented recipe. They are legacy, not
current. The live submitter is `kling_apilena_api_executor.py`.

**Video generation is disabled for now; photo lane first.** The Kling
contract (`pipeline/config/lena_kling_contract.json`) currently sets all
video-count fields to `0` and routes daily generation to photo only. A
studio Kling element exists and is reserved for a later, separate video/
studio lane — it is out of scope right now and must not be used until that
lane is explicitly started.

Active provider rule: Kling is the only active generation provider for Lena. Do not build OpenArt workorders, run OpenArt cleanup, migrate to OpenArt/Seedance, or select OpenArt as fallback unless Nicolas explicitly changes this project rule in writing.

Current rule: do not render or call Kling without explicit approval for the specific command being run, per the live render-freeze/approval discipline recorded in `pipeline/change_notes/NEXT_SESSION_START.md`.

Kling dry-runs must not read `.env` or check credential presence. Live generation through `kling_apilena_api_executor.py` requires an explicit, current-session confirmation from Nicolas before any `CONTENT_BOT_KLING_EXECUTE=1` run.

Approved-queue building may be automated from approved packets. Public posting is not autonomous. `tools/lena_autopublish_approved_queue_v2_8.py` may be used for dry-run previews, but live connector execution must require explicit live approval flags and Nicolas approval.

Root batch launchers whose names imply live autopublish are not approval. They must remain blocked-by-default wrappers unless Nicolas deliberately authorizes a live release procedure. They may run validators or point to dry-runs, but they must not build/mutate queues or publish directly.

Approved publish queue build/rebuild launchers must also remain blocked during polish mode. Legacy publisher deploy/test launchers, especially anything that can control Chrome or SocialBee, must remain blocked unless Nicolas explicitly approves a live account-state test.

Known result status (historical record, BODYLOCK/hcr_001/wc_p045-era, superseded by the reference-by-URL chain above -- kept for history, not as current guidance):

- First hcr_001 proof improved realism but failed on mirror type, neckline, and minor freckle scatter.
- Second hcr_001 proof fixed mirror drift but is rejected/test proof because `wc_p045` rendered as a two-piece crop top plus skirt with unintended midriff/navel, worsened freckle scatter, and portrait-forward framing.
- Third hcr_001 proof, Kling task `899977838852440077`, repeated the `wc_p045` two-piece crop/skirt failure, exposed midriff/navel, added heavy freckle scatter, and was too portrait-forward.
- `wc_p045` is rejected. Do not use it for future generation. (The recipe bank's `hcr_001` entry has since moved on to a different outfit/environment pairing; this history is retained for context only.)

## Lena Identity And Brand

Lena's face/body identity is locked. Improve scene, wardrobe, lighting, realism, and conversion logic around her, not her identity.

Lena is classy, sexy, confident, fashion-forward, and platform-safe. She is not conservative, frumpy, generic, or corporate. Skin exposure is allowed when planned by the outfit and scene. Unplanned exposure, garment drift, or identity drift is a rejection condition.

Public captions/prompts must not mention AI, virtual, synthetic, generated, avatar, fake, bot, or internal production methods.

## Engagement And Monetization Doctrine

Optimize for:

- Saves
- Shares
- Follows
- Profile visits
- Comments
- Repeat viewers
- Reels completion and replay
- DMs or opt-ins when compliant
- Brand/affiliate readiness
- Content proof that can support future offers

Do not optimize for:

- Spam
- Fake engagement
- Deceptive DM bait
- Ban-evasion
- Undisclosed paid relationships
- Unsupported product claims
- Short-term sexualized clicks that damage account trust or brand value

## Official Dry-Run Validation

Before live generation or PR-ready source changes, run the relevant dry-run validators:

- `python tools/strategy/lena_validate_wardrobe_guardrails_v1.py`
- `python tools/strategy/lena_validate_hot_model_expansion_v1.py`
- `python tools/strategy/lena_validate_captain_alignment_v1.py`
- `python tools/strategy/lena_validate_kling_transport_v1.py`

After selecting a replacement outfit, rebuild the `hcr_001` content packet and Kling payload in dry-run only before any live approval. Dry-runs do not publish, upload, schedule, queue, call Kling, or read Kling credentials.

## Captain Warnings

Warn Nicolas when:

- A prompt is near the 2500 character limit and may begin truncating important identity or scene constraints.
- A policy says one thing but a script or catalog says another.
- A path in this information hierarchy is stale or missing.
- A live operation would spend credits, mutate queues, upload media, publish content, or touch account state.
- A monetization idea could create legal, platform, brand-trust, or disclosure risk.
- A proposed shortcut improves speed but weakens the information hierarchy.

## Next Strategic Phase

Run a repo-wide alignment audit after the hcr_001 proof loop:

- Identify canonical policy/source files.
- Find contradictions across scripts and policy files.
- Align everything to profit, engagement, locked identity, intentional sexiness, garment accuracy, real-photo scene logic, official pipeline usage, and fail-closed autonomy.
- Mark old scripts and recipes as legacy/test-only where needed.
- Add validators for contradictions once the audit identifies recurring failure classes.
