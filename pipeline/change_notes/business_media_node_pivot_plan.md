# Business Media Node Pivot Plan

**Date:** 2026-07-07
**Status:** Strategic memo — docs only, nothing built. Grounds every claim below in what
actually exists in this repo as of 2026-07-07, not aspirational architecture.
**Owner:** Nicolas Parker

---

## 1. New positioning

`content_bot` is no longer framed as "an AI influencer node system" (Lena only). It is
reframed as **horizontal media production infrastructure**: a repo capable of running
multiple independent "media node" types, each turning some raw input into finished,
platform-ready content, each with its own folder, its own docs, its own generation/QA/
publish rules.

Lena (the AI-influencer photo/video pipeline) was always the **first node built** —
she just happened to be built before this framing existed. Nothing about her changes
technically; what changes is how the repo is described and how the next node gets built
next to her, not instead of her.

## 2. Revenue Lane vs. Lena R&D Lane

| | **Lena R&D / Demo Lane** | **Revenue Lane (new)** |
|---|---|---|
| Role | Stress-test node. Proves the infrastructure (identity continuity, QA schema, folder-native agent docs, repair doctrine, continuity discipline) works under a hard, adversarial case — a single photoreal AI persona across constant novel prompts. | Where money actually gets made. Business-facing media nodes serving paying clients. |
| Status | **Generation frozen** pending the Kling visual-reference API answer (see `NEXT_SESSION_START.md`'s RENDER FREEZE banner). Frozen ≠ abandoned — nothing is deleted, downgraded, or deprioritized as infrastructure. | **Active build target**, starting now. |
| First product | None yet (never published) | **Podcast / Long-Form Repurposing Node** |
| What it's for | Learning: does the QA-schema pattern, the folder-native agent pattern, the repair-doctrine pattern, the continuity-file discipline all hold up? Yes — proven across this session's wardrobe-fix, schema-v2, and root-cause work. | Applying those same proven patterns to a business offer that can be sold this week, without waiting on Lena's Kling blocker. |

**This is not a demotion.** Lena is the hardest node to get right (identity continuity
across arbitrary generative image content) and everything learned building her
QA/repair/continuity discipline is the reason the new node can be built lightweight and
fast instead of from scratch.

## 3. First sellable offer

**Internal name:** `business_media_node` / `podcast_repurpose`

**External framing (the actual pitch):**
> "I turn your existing videos, podcasts, calls, and business knowledge into a month of
> short-form social content."

## 4. First target customers / ideal customer profiles

Owner-led businesses that already have raw media sitting unused and no repurposing
system:

- Podcast hosts (business/expertise-driven, not comedy/entertainment) with a backlog of
  episodes and no clip strategy.
- Coaches/consultants/course creators with recorded calls, webinars, or Zoom sessions.
- Local/regional service businesses (contractors, med-spas, financial advisors, real
  estate) sitting on raw iPhone clips and testimonials with no edit/caption pipeline.
- Any small business with a YouTube channel posting long-form and nothing short-form.

Common thread: **they already have the raw material.** This offer needs zero content
creation from the client beyond what they already recorded — the sellable value is
repurposing, not production.

## 5. Exact monthly deliverables (proposed starter package — not yet priced/committed)

A first-pass package shape to pressure-test with real prospects, not a locked SKU:

- 8–12 short-form clip ideas per month, each with a timestamp reference into the source
  media.
- A hook line per clip.
- A caption per clip.
- A title/on-screen text option per clip.
- A thumbnail/cover-text suggestion per clip.
- One posting calendar for the month (day/platform suggestion per clip).
- 2–3 CTA variants usable across the batch.
- One bundled **content packet** (all of the above, one document/folder, ready for the
  client's editor or the client themselves to execute).
- One **approval packet** — what the client reviews and signs off on before anything is
  considered "delivered" (mirrors the Lena publish-approval discipline: nothing ships
  without an explicit approval step).
- Light analytics/iteration notes after the first batch posts, to inform the next
  month's clip selection.

**Note:** this repo does not currently produce edited video — the deliverable is the
*plan* (clip selection, hooks, captions, calendar), not cut footage, unless/until a
later phase adds actual editing. This scope boundary should be explicit in the sales
conversation.

## 6. MVP workflow (manual, human-in-the-loop — no code yet)

1. **Intake:** client provides raw media (podcast episode, YouTube video, Zoom
   recording, webinar, raw clips, testimonials) plus basic business context (site copy,
   product/service info).
2. **Transcribe:** get a transcript of the raw media (tool-agnostic at this stage).
3. **Identify clip-worthy moments:** scan the transcript for standalone, hook-worthy
   segments (a strong claim, a story, a stat, an emotional beat, a controversial take).
4. **Draft the angle per clip:** hook line, caption, title/on-screen text, thumbnail/
   cover-text suggestion — reusing the *pattern* already proven in Lena's
   `strong_hook_bank_v1.json` (scored hook dimensions: visual pairing, curiosity,
   comment potential, platform safety, voice fit), adapted to a business voice instead
   of an influencer voice.
5. **Assemble the content packet:** all clip angles + a posting calendar + CTA variants
   into one deliverable.
6. **Build the approval packet:** what the client reviews/approves before anything is
   considered done.
7. **Deliver, client posts (or a later phase posts on their behalf).**
8. **Light analytics feedback:** what worked, feeding clip selection next month.

Every step above is manual/human-run for the MVP. No code is being built this turn —
this is the workflow the future code should encode, once approved.

## 7. Folder / node structure

```
pipeline/nodes/
  business_media/
    podcast_repurpose/
      README.md       -- what this node is/does
      INPUTS.md        -- accepted raw media + business context
      OUTPUTS.md       -- the content packet + approval packet + deliverables
      WORKFLOW.md      -- the MVP manual workflow above
      OFFER.md         -- the external sellable offer + proposed package
      CURRENT_STATE.md -- docs-only status, next actions
```

Deliberately **lightweight** — not the full Lena-style `40_identity_continuity/
50_prompt_builder/60_executor/70_visual_qa/80_repair/` numbered-agent-slice pattern.
That pattern is proven and available to adopt later if/when this node has real code and
real failure modes worth that level of structure. Building it now, before a single
client exists, would be over-engineering ahead of revenue.

## 8. What carries over from Lena infrastructure (patterns, not code)

- **Folder-native Markdown documentation pattern** (a node folder with README/INPUTS/
  OUTPUTS/WORKFLOW-or-RULES/CURRENT_STATE) — the *convention* carries over; this node's
  own files above already follow it, lightweight version.
- **Continuity-file discipline** (`NEXT_SESSION_START.md` +
  `lena_filesystem_native_agent_pivot_master.md`-style master doc + dated changelog) —
  the practice of "every meaningful step updates the continuity layer" carries over to
  this node's own future work, not just Lena's.
- **Structured QA-verdict pattern** (schema-versioned checklist + explicit hard-gating
  vs. advisory fields + a false-green validator) — the *idea* of judging output against
  a structured, versioned rubric instead of vibes is directly reusable for judging
  content-packet quality (e.g., "does this hook actually hit curiosity/platform-safety/
  voice-fit") — not `pipeline/qa/lena_photo_qa.py` itself, which is photo/identity-
  specific.
- **Repair-doctrine pattern** (`80_repair`'s hard-stop-vs-retryable framing, capped
  retries, a stated hypothesis per retry) — generically useful once this node has real
  failure modes (e.g., a clip idea that tests badly) worth formalizing.
- **Session-continuity skills** (`lena-session-start` / `lena-session-checkpoint`) — the
  pattern of a bootstrap-and-checkpoint skill pair is reusable; whether this node gets
  its own skills or a shared/generalized pair is a later decision, not made now.
- **Hook-bank pattern** (`pipeline/prompt_banks/lena/strong_hook_bank_v1.json`'s scored
  hook-text structure: category, hook text, visual pairing, best platforms, scored
  dimensions) — the *shape* of a scored hook bank is directly portable to a business-
  voice hook bank; the actual Lena-flavored hook content is not (wrong voice/audience).
- **Repo-knowledge layer** (`pipeline/knowledge/content_bot/*.md`) — already named
  `content_bot`, not `lena`, and already infrastructure-wide in intent. Should extend to
  document this new node too (a later, separate update — not done this turn).
- **Generic engineering infra** — env loading (`pipeline/env_loader.py`), git/venv
  conventions, this Claude session's memory/skills setup — trivially reusable.

## 9. What stays Lena-specific / isolated (do not dilute into the new node)

- `pipeline/identity/lena_identity.py`, `pipeline/prompting/lena_prompt_brain.py`,
  `pipeline/kling_apilena_api_executor.py` — Lena's identity/prompt/execution stack.
- The wardrobe/environment/scene catalogs (`pipeline/prompt_banks/lena/*.json`) —
  tuned to one photoreal persona, not portable to a business-voice content node.
- `pipeline/qa/lena_photo_qa.py` and the QA schema v2 `production_scoring` block —
  photo/identity/styling-specific fields (hook strength *for a sexy photo*, styling
  safety, wardrobe fidelity) don't map onto a business content packet's QA needs.
- The five Lena folder-native agent slices
  (`pipeline/agents/lena/40_identity_continuity/` through `80_repair/`).
- The Kling reference-image investigation and render freeze — entirely Lena's blocker,
  irrelevant to this new node (it uses no image generation at all).
- Lena's Instagram publishing path (`posting_manager.py` as wired to
  `lenadelapineapple.official`) — single-account, single-persona; not part of a
  multi-client business node's publishing needs (which will differ per client anyway).

## 10. 7-day build plan (MVP, docs → first pilot)

- **Day 1 (today):** this memo + node doc scaffolding (done this turn). No code.
- **Day 2 (done, 2026-07-07, docs-only, committed as `fe1c5ce4`):** finalized the
  offer/package wording and a pricing hypothesis in
  `pipeline/nodes/business_media/podcast_repurpose/OFFER.md` (anchor $997/month,
  explicitly unvalidated), and drafted a short outbound pitch script in the same
  folder's new `PITCH_SCRIPT.md`. Both are draft/unsent/untested — see that folder's
  `CURRENT_STATE.md` for status.
- **Day 3–4:** manual outreach to identify first 3 pilot prospects (see §12 below).
  Zero code — this is relationship/sales work.
- **Day 5:** run the MVP workflow **by hand** (no code) on one real or sample piece of
  client media, to prove the workflow itself before writing any automation. This is the
  single highest-value validation step — do it before building anything.
- **Day 6:** based on what Day 5 exposed as tedious/error-prone, decide what (if
  anything) is worth turning into a first small script — but only if the manual pass
  proved the workflow is sound. Do not build automation for an unvalidated workflow.
- **Day 7:** review the pilot outcome, adjust the package/offer if needed, decide
  whether to formalize a `CURRENT_STATE.md` update declaring pilot-validated status.

## 11. What NOT to build yet

- No transcription/clip-detection/caption-generation code. The MVP workflow is run by
  hand first (Day 5 above) to validate it before automating any of it.
- No Blotato integration (explicitly deferred, per direction).
- No multi-client posting/scheduling infrastructure — Lena's `scheduler.py`/
  `posting_manager.py` are single-account and not yet proven generalizable; don't
  attempt that generalization before there's a second real client needing it.
- No full Lena-style numbered agent-slice folder structure for this node (see §7) —
  premature before real failure modes exist to document rules against.
- No pricing commitment beyond the proposed package in §5 — validate with real
  prospect conversations first.
- No Lena generation work of any kind — that thread stays frozen on its own timeline
  (Kling support answer), unrelated to this pivot's pace.

## 12. How to sell the first 3 clients manually

No code or automation needed for this — it's outreach and conversation:

1. **Start warm, not cold.** List every owner-led business in your existing network
   (or Nicolas's) that already publishes long-form content (podcast, YouTube, webinar
   replays) but visibly has no short-form/social presence, or a thin one. This is a
   visible, checkable signal — you can literally see the gap before reaching out.
2. **Lead with the specific gap, not a generic pitch.** "I noticed you've got 40
   episodes and no clips on Instagram/TikTok — want me to turn last month's episode
   into a content pack for free, so you can see what it looks like before paying
   anything?"
3. **Offer one free/discounted pilot batch** (using the Day 5 manual workflow above) to
   the first 1–3 prospects, in exchange for a testimonial and permission to use the
   result as a portfolio sample. This directly produces the "first 3 clients" and a
   proof sample simultaneously.
4. **Ask pilot clients what they'd actually pay** for this monthly, before proposing a
   price yourself — this validates or corrects the §5 package/pricing hypothesis with
   real signal instead of a guess.
5. **Convert pilots to the first paid month** once they've seen one real batch and
   said yes to a price. No landing page, no ads, no automation needed to get to three
   paying clients — this is a relationship-and-proof-of-work motion, not a marketing
   funnel.

---

*Nothing in this memo is code. No Kling call, no render, no `.env` edit, no publish, no
production-routing change, no Blotato work. See the node docs at
`pipeline/nodes/business_media/podcast_repurpose/` for the node-level detail, and the
continuity files (`NEXT_SESSION_START.md`, master file, changelog) for how this pivot is
now recorded for future sessions.*
