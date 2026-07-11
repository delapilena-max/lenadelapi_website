# Chat Session Boot Prompt - content_bot

Use this at the start of a new chat when you want the assistant to orient
deeply before doing technical work.

```text
Before doing anything else, familiarize yourself with content_bot from the
repo itself, not from chat memory.

Follow this exact order:
1. Read pipeline/knowledge/content_bot/SESSION_BOOT_PROTOCOL.md
2. Read pipeline/change_notes/NEXT_SESSION_START.md
3. Read the current-state section of
   pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md
4. Read the latest relevant entries in
   pipeline/change_notes/lena_agentic_pivot_changelog.md
5. Read pipeline/knowledge/content_bot/AUTHORITATIVE_SURFACES.md
6. Read pipeline/knowledge/content_bot/QUARANTINED_SURFACES.md
7. Read pipeline/knowledge/content_bot/REPO_MAP.md
8. Read pipeline/knowledge/content_bot/LIVE_PATHS.md
9. Read pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md
10. Read the current owning modules for identity, prompting, QA, preflight,
    posting manager, queue bridge, and Graph adapter.
11. Before working in any subsystem, read its AGENT.md, RULES.md, and
    CURRENT_STATE.md.

First establish repo truth from git:
- exact repo path
- current branch
- current HEAD
- recent `git log --oneline -8`
- full `git status --short`
- explicit recognition of the pre-existing dirty pile
- exact owned write scope, if any

Immediately surface these standing truths and verify them from repo files:
- one autonomous Lena content loop is the north star
- Reels primary, Feed second, Stories third
- publish freeze remains active unless explicitly lifted by Nicolas
- no publishing, live queue promotion, or outward R2 publishing until the
  clean-export conditions are proven and Nicolas explicitly lifts the freeze
- metadata scrubber is important but currently untracked/uncommitted unless
  later repo continuity says otherwise
- never build duplicate systems without checking for existing metrics,
  learning, history, observability, or publisher infrastructure first
- no `.env` access or edits unless explicitly authorized
- preserve the unrelated dirty pile
- read-only first
- no render/provider/publish action without explicit approval
- repo files outrank chat memory

Then give me a concise boot report with these exact headings:
- CURRENT REPO PATH
- CURRENT HEAD
- RECENT COMMITS
- CURRENT BRANCH
- REPO STATUS
- PRIMARY OBJECTIVE
- CURRENT LIVE PATH
- CURRENT BLOCKERS
- CURRENT PUBLISH FREEZE STATUS
- LATEST COMPLETED STEP
- NEXT APPROVED STEP
- OPEN ARCHITECTURE DECISIONS
- UNTRACKED / DIRTY FILES OF INTEREST
- EXPLICIT WRITE SCOPE
- HARD PROHIBITIONS
- CONTRADICTIONS FOUND
- FILES READ

Do not propose code changes or next steps until you have done that alignment.
When stating facts, distinguish between:
- verified from code
- verified from continuity docs
- historical only
- inference
```
