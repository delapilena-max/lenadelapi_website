# Session Boot Protocol - content_bot

**Purpose:** Give every new chat a reliable, repo-native way to acquire a
focused understanding of `content_bot` before it proposes or changes
anything.

This protocol is mandatory for any session that might touch Lena pipeline
logic, publishing, QA, generation, queueing, or infrastructure. The goal is
not "read some docs." The goal is: **the chat can state the current
architecture, live path, freezes, blockers, and authoritative modules in its
own words before doing work.**

## Standing truths that must be surfaced immediately

Every boot report must state these repo-level truths up front, then verify
their current wording from the continuity files:

- one autonomous Lena content loop is the north star
- Reels are primary, Feed is second, Stories are third
- the current publish freeze remains in force unless Nicolas explicitly lifts
  it
- no publishing, live queue promotion, or outward R2 publishing is allowed
  until the clean-export conditions are proven and Nicolas explicitly lifts
  the freeze
- the metadata scrubber is important but currently untracked/uncommitted
  unless later continuity updates say otherwise
- never build duplicate systems before checking whether metrics, learning,
  history, observability, or publisher infrastructure already exists
- no `.env` access or edits unless explicitly authorized
- preserve the unrelated dirty pile
- read-only first
- no render, provider call, or publish action without explicit approval
- repo files outrank chat memory

## Repository identity and git truth

Every new session must establish repo truth from git before any write action:

1. Confirm the exact repo path.
2. Run `git branch --show-current`.
3. Run `git log --oneline -8`.
4. Run `git status --short`.
5. Explicitly recognize the pre-existing dirty pile.
6. Identify the exact paths owned by the current task before editing.
7. Use exact path-based staging only.
8. Never use `git add .`, `git add -A`, broad cleanup commands, repo-wide
   formatting, or unrelated rewrites.
9. Never clean, revert, move, rename, delete, or format unrelated files.

If `HEAD` changes during the task:

1. Stop before any further write.
2. Re-read `SESSION_BOOT_PROTOCOL.md`.
3. Re-read `pipeline/change_notes/NEXT_SESSION_START.md`.
4. Re-read relevant subsystem `CURRENT_STATE.md` files.
5. Re-run `git log --oneline -8`.
6. Re-run `git status --short`.
7. Inspect what changed.
8. Continue only if the new commit is clearly non-overlapping with the
   assigned scope.

## Outcome required before any technical work

Before proposing edits, running meaningful commands, or making architecture
claims, the chat must be able to answer all of these correctly from the repo:

1. What is the standing product objective?
2. What is currently frozen, and what explicitly remains forbidden?
3. Which publishing architecture(s) exist right now, and is there a canonical
   winner?
4. What is the current live generation/publish path vs historical/legacy
   paths?
5. Which files are authoritative for identity, prompt construction, QA,
   publish gating, queueing, and continuity?
6. Which current blockers are product/policy blockers versus technical ones?
7. Which actions are explicitly prohibited this session unless separately
   approved?

If the chat cannot answer those from repo evidence, it is not warmed up yet.

## Mandatory read order

Read in this exact order. Do not skip ahead just because a file seems
familiar.

### Layer 1 - standing doctrine and session truth

1. `pipeline/knowledge/content_bot/SESSION_BOOT_PROTOCOL.md`
2. `pipeline/change_notes/NEXT_SESSION_START.md`
3. `pipeline/change_notes/lena_filesystem_native_agent_pivot_master.md`
4. `pipeline/change_notes/lena_agentic_pivot_changelog.md`

What to extract:
- standing product objective
- current freeze(s)
- latest architecture/bifurcation findings
- current autonomy truth
- exact next-step discipline
- hard prohibitions

### Layer 2 - source-of-truth map

5. `pipeline/knowledge/content_bot/AUTHORITATIVE_SURFACES.md`
6. `pipeline/knowledge/content_bot/QUARANTINED_SURFACES.md`
7. `pipeline/knowledge/content_bot/REPO_MAP.md`
8. `pipeline/knowledge/content_bot/LIVE_PATHS.md`
9. `pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md`

What to extract:
- which files win when docs disagree
- what is live vs quarantined vs historical
- high-level repo ownership
- current proof status and proven/unproven paths

### Layer 3 - infrastructure and pipeline code truth

Read the actual implementation files that own the current path or current
guardrails relevant to the task:

10. `pipeline/identity/lena_identity.py`
11. `pipeline/prompting/lena_prompt_brain.py`
12. `pipeline/qa/lena_photo_qa.py`
13. `pipeline/lena_production_job.py`
14. `pipeline/posting_manager.py`
15. `pipeline/publisher/instagram_queue_bridge.py`
16. `pipeline/publisher/instagram_graph_adapter.py`
17. `tools/lena_preflight.py`

Read task-specific code after this layer, not before it.

### Layer 4 - folder-native agent doctrine

Read the folder-native slices that define how this repo now wants concerns
organized:

18. relevant subsystem `AGENT.md`
19. relevant subsystem `RULES.md`
20. relevant subsystem `CURRENT_STATE.md`

At minimum, read the matching docs for whichever subsystem the task touches.

## Required fixed boot report

Before work starts, the chat must produce a short boot report using these
exact headings. Keep it concise and pointer-based. Do not turn the report
into a copied history dump.

### CURRENT HEAD

State the current commit if verified from git. If not verified, say so.

### RECENT COMMITS

List the recent `git log --oneline -8` output or summarize it faithfully.

### CURRENT REPO PATH

State the exact repo path being operated on.

### CURRENT BRANCH

State the current branch if verified from git. If not verified, say so.

### REPO STATUS

Summarize dirty tracked files, untracked files of interest, and whether the
tree is noisy enough to require extra caution.

### PRIMARY OBJECTIVE

One short paragraph tying the user's task back to the autonomous-loop goal.

### CURRENT LIVE PATH

One ordered chain from entrypoint through generation/gating/publish surfaces,
with pointers to owning files.

### CURRENT BLOCKERS

Flat bullets for the real blockers, distinguishing technical vs policy/freeze.

### CURRENT PUBLISH FREEZE STATUS

State whether the freeze is active, what it forbids, and what evidence would
be required before it can be lifted.

### LATEST COMPLETED STEP

Point to the latest completed milestone/checkpoint from continuity files.

### NEXT APPROVED STEP

State the next step only if continuity explicitly says one is approved.
Otherwise say none is pre-approved.

### OPEN ARCHITECTURE DECISIONS

List unresolved structural choices, especially duplicate/parallel systems.

### UNTRACKED / DIRTY FILES OF INTEREST

Call out files that materially affect the current task or continuity, without
treating the whole dirty pile as yours to clean.

### EXPLICIT WRITE SCOPE

List the exact files, if any, the current task intends to modify. If the
session is read-only, say so.

### HARD PROHIBITIONS

Flat bullets only. This must include any current no-publish, no-provider,
no-`.env`, no-render, or no-queue-mutation rules relevant to the task.

### CONTRADICTIONS FOUND

List any contradictions between docs, code, manifests, or continuity. If none
were found, say none yet.

### FILES READ

List the actual files read during boot so the session can be audited.

## Required evidence discipline

The chat must separate these categories explicitly:

- **Directly verified from code**
- **Directly verified from continuity docs**
- **Historical only / not trusted until rechecked**
- **Inference**

This repo has enough drift and parallel surfaces that unstated inference is
dangerous.

## Multi-agent coordination

Claude and Codex may work in this repo simultaneously.

Before every write:

- run `git status --short`
- identify exact owned paths
- treat all other modified/untracked files as owned by another agent or out
  of scope
- do not touch overlapping files
- use exact path staging only
- never silently reconcile concurrent overlapping changes

Suspension or silence from another agent is not implicit authorization to
take over its lane.

## Existing-system discovery rule

Before proposing or building a new subsystem, search for existing code, state,
policies, historical implementations, observability surfaces, and
superseded-but-reusable infrastructure first.

Never create a duplicate subsystem until the repo has been searched for
existing metrics, learning, history, reuse policy, publisher infrastructure,
operator-console tooling, and related state.

## Commands to use during warm-up

Preferred command sequence for a fresh session:

```powershell
Get-Location
git branch --show-current
git log --oneline -8
git status --short
Get-Content -Raw "pipeline/change_notes/NEXT_SESSION_START.md"
Get-Content -Raw "pipeline/knowledge/content_bot/AUTHORITATIVE_SURFACES.md"
Get-Content -Raw "pipeline/knowledge/content_bot/QUARANTINED_SURFACES.md"
Get-Content -Raw "pipeline/knowledge/content_bot/REPO_MAP.md"
Get-Content -Raw "pipeline/knowledge/content_bot/LIVE_PATHS.md"
Get-Content -Raw "pipeline/knowledge/content_bot/CURRENT_PROOF_STATUS.md"
Get-Content -Raw "pipeline/identity/lena_identity.py"
Get-Content -Raw "pipeline/prompting/lena_prompt_brain.py"
Get-Content -Raw "pipeline/qa/lena_photo_qa.py"
Get-Content -Raw "pipeline/lena_production_job.py"
Get-Content -Raw "pipeline/posting_manager.py"
Get-Content -Raw "pipeline/publisher/instagram_queue_bridge.py"
Get-Content -Raw "pipeline/publisher/instagram_graph_adapter.py"
Get-Content -Raw "tools/lena_preflight.py"
```

Use `rg` after this for task-specific follow-up, not as a substitute for the
base warm-up.

## Anti-patterns this protocol is meant to stop

- Trusting chat memory over repo files
- Assuming a suspended or parallel agent has handed off a file implicitly
- Trusting chat memory over `NEXT_SESSION_START.md`
- Assuming the newest-looking script in `tools/` is the live one
- Confusing a historical proof with the current canonical path
- Treating an untracked utility as integrated production behavior
- Focusing on one subproblem while losing the autonomous-loop objective
- Proposing publisher changes without understanding the freeze or architecture
  fork
- Treating docs as enough without reading the owning modules

## Recommended operating rule

For any non-trivial request, the first meaningful assistant update should
state:

1. that it is orienting on continuity + authoritative surfaces first
2. which files it is reading to verify live-path truth
3. that it will summarize the current architecture before changing anything

That keeps each session grounded in repo evidence instead of conversational
momentum.
