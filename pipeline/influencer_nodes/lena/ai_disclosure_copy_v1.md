# Lena Delapi — AI / Virtual Creator Disclosure Copy (v1)

Status: **DRAFT, APPROVED COPY, NOT YET APPLIED.** As of this file's creation
(2026-07-08), none of the text below has been published to any live
Instagram/Facebook/TikTok profile, pinned post, website, or brand-facing
document. This file exists so a human operator can manually copy/paste the
approved text into the relevant live surface. No automated tool in this repo
writes bio/profile fields, and this patch does not add one.

## Scope and relationship to `BANNED_PUBLIC_TERMS`

`BANNED_PUBLIC_TERMS` (`pipeline/prompting/lena_prompt_brain.py`) and the
"never say or imply AI" rules in `SKILL.md` and `persona.json` govern
**ordinary in-character captions, replies, and content voice only**. They do
not apply to, and must never be used to justify omitting disclosure language
from, the durable disclosure surfaces below. See
`pipeline/influencer_nodes/lena/disclosure_compliance_policy_v1_9.json` →
`ai_virtual_creator_disclosure` for the doctrine tying these together.

Lena must not be represented to users or brands as a real private human.

## Durable disclosure surfaces and approved copy

### 1. Instagram/profile bio — short option
```
AI / virtual creator. Fashion, fitness-glam, creator life, and high-glam moments.
```

### 2. Instagram/profile bio — polished option
```
Virtual creator / AI fashion persona. Luxury fit-checks, creator life, and high-glam moments.
```
Use one of the two bio options above, not both. Either should sit in the
literal bio field of every live platform account (Instagram, Facebook,
TikTok, YouTube) Lena is published to.

### 3. Pinned intro post / website "about" page
```
Lena Delapi is a fictional AI-generated virtual creator operated as a
digital fashion and creator-life project. Her photos, videos, captions, and
character presentation are produced through AI-assisted creative tools and
human approval.
```
This should be pinned at the top of the feed on every live platform account,
and/or reproduced verbatim on the website's about page.

### 4. Brand / media-kit / sponsorship outreach copy
```
Lena Delapi is an AI-generated virtual creator / digital fashion persona.
Brand collaborations are reviewed and approved by the operator, and Lena
should not be represented as a real human spokesperson.
```
This copy is also emitted programmatically as `profile_fields.ai_disclosure`
by `tools/lena_generate_media_kit_brief_v1_9.py` (see
`pipeline/influencer_nodes/lena/media_kit_schema_v1_9.json`) — any human
sending a media kit or outreach message should still paste this line
explicitly into the message body, not rely solely on the JSON field being
read by the recipient.

## Manual application checklist (not automated by this patch)

- [ ] Update live Instagram bio field
- [ ] Update live Facebook page bio/about field
- [ ] Update live TikTok bio field (if/when TikTok account goes live)
- [ ] Publish a pinned intro post using the copy in section 3
- [ ] Add an "about" section to the live website using the copy in section 3
- [ ] Confirm every future media-kit/brand-outreach message includes section 4's copy

None of the above checklist items were performed by this patch. This file
only adds the approved copy and the doctrine tying it to
`BANNED_PUBLIC_TERMS`'s actual (narrower) scope.
