# Methodology: Change Discipline

How to land changes in this repository: issue granularity, PR sizing,
branch naming, anti-patterns. The companion to
[`agent-onboarding.md`](agent-onboarding.md), which covers
*context durability*. This document covers *change discipline* —
the two together form the agentic dev kit for this repo.

This document is **descriptive of how the repo is run**, not a
suggestion. The practical contract for this specific repo lives at
[`docs/DEVELOPMENT_WORKFLOW.md`](../DEVELOPMENT_WORKFLOW.md). This
file describes the abstract pattern, applicable to any repo.

> **Lineage:** This doc was originally inspired by this repo's
> [`docs/DEVELOPMENT_WORKFLOW.md`](../DEVELOPMENT_WORKFLOW.md)
> (PR #3), then matured in
> [`timwukp/dora-metrics-platform/docs/methodology/change-discipline.md`](https://github.com/timwukp/dora-metrics-platform/blob/main/docs/methodology/change-discipline.md),
> and is now adopted back here as the abstract methodology layer.
> See "Origin" at the bottom for full attribution.

---

## Why this discipline

We use **issue → fix → PR**, one logical change at a time, instead of
monolithic "big bang" PRs.

| Monolithic PR (avoid) | Iterative PRs (this repo) |
|---|---|
| 50 files changed, 30 unrelated concerns | One concern per PR |
| Reviewer must context-switch mid-review | Reviewer focuses on one thing |
| Hard to revert one bad change without losing the rest | Revert = single `git revert` |
| Issue history is implicit ("see commits") | Each fix has an explicit issue with a paper trail |
| Bus factor: only the author knows what's in there | Anyone can pick up any open issue |

**This applies even when you find many problems at once.** Audit
broadly, then file each finding as a separate issue. Don't try to
fix everything in one PR just because you discovered everything in
one read-through.

---

## The 5-step loop

```
┌──────────┐   ┌────────┐   ┌──────┐   ┌─────┐   ┌────────┐
│ DISCOVER │──▶│ TRIAGE │──▶│ GROUP│──▶│ FIX │──▶│ REVIEW │
└──────────┘   └────────┘   └──────┘   └─────┘   └────────┘
     ▲                                                │
     └────────────────── repeat ──────────────────────┘
```

### Step 1: Discover (audit broadly)

Before fixing anything, list **all** problems you can find:

- Read existing docs and code
- Compare claims (README badges, status tables) against reality
  (test logs, commit history)
- Find inconsistencies between files (doc says X, code does Y)
- Note out-of-date references and stale TODOs

**Output:** A flat list of all findings, no prioritization yet.

### Step 2: Triage

Apply this scale:

| Level | Meaning | Example |
|---|---|---|
| **P0** | Meta — blocks other work | Add DEVELOPMENT_WORKFLOW.md before doing 7 follow-up fixes (this repo's PR #3) |
| **P1** | Bug or contradiction visible to users | README badge shows 32 tests but body says 35 (PR #5) |
| **P2** | Drift between code and docs | Architecture doc missing sections for tools that exist in code (PR #9) |
| **P3** | Future improvement, not currently broken | Production hardening design plan (PR #15) |

This repo currently does **not** use `P0`/`P1`/`P2`/`P3` GitHub
labels. The scale is a triage tool, not a labeling requirement.
Use it in your head; record the priority in the issue body.

Also consider **relevance**: does fixing X unblock Y? If yes, X is
higher priority regardless of severity.

### Step 3: Group findings into issues

**One issue = one logical change with one acceptance criterion.**

Heuristics:

- ✅ Two badges + a paragraph all referencing the same out-of-date
  number → **one issue** (one logical fact). Example: PR #5 fixed
  tests-passed + pass-rate badges + body claim simultaneously.
- ✅ Three missing sections in the same doc → **one issue** (one
  doc, one purpose). Example: PR #9 added §6 Code Interpreter,
  §10.2 Eval Runner, §13 A2A to ARCHITECTURE.md.
- ❌ "Fix all docs" → split into per-doc or per-concern issues
  (this is what v0.2.1's 8 issues did; see worked example below)
- ❌ "Add Code Interpreter section + fix unrelated typo" → split

**Rule of thumb:** If you can't write a single sentence describing
what "done" looks like, the issue is too big.

### Step 4: Fix one issue at a time

For each issue:

1. **Branch** from `main` using the naming convention below.
2. **Commit** with focused messages. Reference the issue.
3. **Push** the branch.
4. **Comprehensive test on AWS** for any code touching AWS APIs.
   ⚠️ **Mandatory.** TWO levels required, both BEFORE the PR is opened:

   **4a. API-level live test:**
   - Apply the change against your AWS account (the actual API call, not just `--dry-run`)
   - Re-run the script to confirm idempotency (no API mutations on second run)
   - Confirm target state via `get_*` / `list_*` / `describe_*` API calls
   - Capture redacted evidence

   **4b. Functional / end-to-end test:**
   - Invoke the feature in target state (real harness invocation, real session)
   - Observe and verify runtime behavior matches expectations:
     - Memory wire → invoke agent in 2nd session, verify it recalls prior state
     - Skill wire → invoke agent, verify reasoning trace references skill methodology
     - Config tighten → invoke agent under new constraints, verify no regression
     - Observability → trigger event, verify metric / log appears within expected window
     - Inline function → trigger condition, verify pause + resume works
   - Capture redacted trace / output / metric evidence

   Both 4a AND 4b in the PR description's Verification section AND in
   `agentcore/scripts/VERIFICATION_issue_<N>.md`.

   **Doc-only PRs are exempt from both 4a and 4b.**

   **"Deferred to post-merge" is NEVER acceptable** — that creates
   the PR #50 / #46 latent-bug pattern AND the PR #51/#54/#55 untested-
   feature pattern. Cost ($0.30-$1 per invocation) is NEVER a valid
   reason to skip 4b. If 4b genuinely cannot be tested pre-merge
   (e.g. requires the same PR's content to be on `main` first):
   - **Split the work** into a prerequisite PR (lands first) + main PR
     (lands after the prereq is on main, so 4b can run)
   - This is the only acceptable "alternative path" — and it still
     requires both tests, just across two PRs

5. **Open PR** using the PR template. Title mirrors the issue.
6. PR description includes `Closes #N` so GitHub auto-closes the
   issue on merge.

**Don't:**
- Bundle unrelated changes "while you're in there"
- Open a PR before the issue exists (except trivial typos and
  security hotfixes — see "When to deviate" below)
- Reuse a branch for a second issue
- Open a PR for AWS-touching code without BOTH 4a AND 4b verification
- Defer 4b "to save money" — comprehensive testing is non-negotiable
- Defer 4b "to post-merge" — split into prereq + main PR instead

### Step 5: Review and iterate

- Wait for review before starting the next issue, *or* push the
  current PR before context-switching so the work is durable.
- Apply review feedback as new commits to the same branch — don't
  force-push during active review.
- Squash on merge if commits are noisy; keep them if each commit
  tells a coherent step.
- After merge, **delete the branch** (the merge commit retains the
  history; this repo has `delete_branch_on_merge` enabled at the
  repo level, so this happens automatically).

---

## Stacked PRs (the exception, not the default)

When N issues are sequentially dependent and would block each other
if filed as parallel PRs, a **stacked PR** is acceptable:

```
main ◀── PR #N+1: feature A ◀── PR #N+2: feature B (base = #N+1) ◀── PR #N+3 …
```

Each PR's base is the previous PR's branch, not `main`. Merge in
order; retarget downstream PRs to `main` after each merge.

**Use this only when:**
- The work cannot be split into truly independent issues
- Each PR in the stack still passes its own acceptance criteria (including 4a + 4b)
- The stack is small (≤ 5 PRs); larger stacks become ungovernable

**This repo has not yet needed a stack.** All v0.2.1 audit work
(PRs #3-#16) and v0.2.2 harness configuration so far (PRs #39, #40,
#42) was filed as parallel independent PRs because no two issues
had a hard sequential dependency.

For an example of stacked PRs done well, see the dora-metrics-platform
phase 1–6 install-friction stack
([`docs/test-reports/phase6-rollup.md`](https://github.com/timwukp/dora-metrics-platform/blob/main/docs/test-reports/phase6-rollup.md)).

A common reason to use a 2-PR stack now: when 4b functional testing
requires content from the same change to be on `main` first (e.g.
git-source skills referencing a SKILL.md added in the same change).
Split into "prereq PR (content)" → merge → "main PR (wire + 4b test
against now-on-main content)".

If your work doesn't have this kind of hard sequential dependency,
default to filing parallel issues with one PR each, not a stack.

---

## Templates

The canonical templates for this repo live in
[`docs/DEVELOPMENT_WORKFLOW.md`](../DEVELOPMENT_WORKFLOW.md). The
structures below are the abstract contract — three templates that
cover the three issue/PR types this methodology distinguishes.

### Issue: discussion (architectural)

For decisions where the path isn't yet clear. Use the GitHub
`discussion` label. The "Working assumptions" section is the single
biggest improvement over a normal issue — without it, a reader
can't tell which side of the comparison table you're on.

```markdown
## Context
What's the situation, in 1–2 paragraphs.

## Working assumptions (read this first)
The maintainer's priors. State preferences explicitly:
- "Maintainer leans toward X over Y because Z."
- "Constraint A is hard; constraint B is soft."
- "Tool C is in scope; tool D is not."

## The architectural question
The actual decision, with a comparison table if multiple paths.
Be neutral *here* — the priors above already showed your hand.

## Why it's non-trivial for our setup
What's specific about this repo that makes the textbook answer wrong.

## Proposed direction
Best current guess; an anchor for discussion, not a decision.

## Open questions
Numbered list. What the next iteration resolves.

## Non-goals
What this issue is explicitly NOT about. Prevents scope creep.

## Repo context
Links to AGENTS.md, related code paths, prior PRs.
```

### Issue: bug or correctness (the default)

```markdown
## Problem
What is wrong, missing, or inconsistent. One paragraph.

## Evidence
- File:line references
- Commit SHAs
- Error logs / screenshots
- Quoted text from the offending file(s)

## Proposed Solution
Bullet list of changes intended.

## Acceptance Criteria

For AWS-touching changes — mandatory before opening PR (per Step 4):
- [ ] **(4a) API-level live test passes** — apply + idempotent re-run + state verification
- [ ] **(4b) Functional / E2E test passes** — invoke the feature; observe runtime behavior matches expectations
- [ ] Both tested BEFORE opening the PR; evidence in `agentcore/scripts/VERIFICATION_issue_<N>.md`

Issue-specific criteria (concrete behavior checks):
- [ ] Concrete check 1 (e.g. "harness console shows X")
- [ ] Concrete check 2 (e.g. "agent reasoning trace references Y from the wired skill")

## Priority
P0 / P1 / P2 / P3 — and why.

## Effort
Small (1 file, < 50 lines) / Medium (1 doc, 1 area) / Large (multi-file)

## Out of Scope
What this issue explicitly does NOT cover.
```

### Pull request

```markdown
## Summary
Closes #N

One paragraph: what was wrong, what this PR changes.

## Changes
- `path/to/file1`: did X
- `path/to/file2`: did Y

## Verification
For AWS-touching PRs (NOT exempt for doc-only):

- [ ] **(4a) API-level live test passed BEFORE this PR was opened** — apply +
      idempotent re-run + `get_*`/`list_*` verify path. Evidence in this PR
      AND in `agentcore/scripts/VERIFICATION_issue_<N>.md`.
- [ ] **(4b) Functional / E2E test passed BEFORE this PR was opened** —
      invoked the feature in target state, observed runtime behavior.
      Examples:
      - Memory wire → 2nd-session recall verified
      - Skill wire → reasoning trace references skill content
      - Config tighten → no regression on golden tests
      - Observability → metric/log appeared within expected window
      Evidence (redacted trace / output / metric snapshot) in PR description
      AND in VERIFICATION_issue_<N>.md.
- [ ] Local check: `cmd to run`
- [ ] Re-run of CI

Doc-only PRs are exempt from 4a and 4b — explain in PR description.

## Out of Scope
What this PR does NOT change, but the issue mentioned.
Link to follow-up issue.

## Risk
Low / Medium / High — what could break if this is wrong.
```

---

## Naming conventions

### Branches

```
<type>/issue-<number>-<kebab-short-desc>
```

| Type | Use for |
|---|---|
| `fix` | Bug or correctness fix |
| `docs` | Documentation only |
| `feat` | New feature or capability |
| `refactor` | Code change with no behaviour change |
| `chore` | Build, dependencies, tooling |
| `test` | Tests only |

Examples (this repo's actual branches):

- `docs/issue-2-development-workflow` (PR #3)
- `fix/issue-4-readme-badges` (PR #5)
- `feat/issue-24-memory-uitestagent` (PR #40)
- `docs/agents-md` (PR #42)

For stacked PRs (the exception above), use a phase-prefixed name:
`phase1/docs-scripts-fixes`, `phase2/kustomize-overlays`, etc.

### Commits

[Conventional Commits](https://www.conventionalcommits.org/) format
is the project standard.

### Pull request titles

Same format as commit messages. The PR title is what shows up in
`git log` after squash-merge, so it matters.

---

## Anti-patterns to avoid

| Anti-pattern | Why it's bad |
|---|---|
| Big-bang PR with 30 unrelated changes | Unreviewable; can't revert one thing |
| Issue with no acceptance criteria | "Done" is a moving target |
| Branch named `update`, `temp`, `wip`, `main2` | Useless in `git log`; conflicts with parallel work |
| PR description "see commits" | Reviewer shouldn't have to reverse-engineer intent |
| Closing an issue without a merged PR | Loses traceability; future-you can't find the fix |
| Force-pushing during active review | Invalidates reviewer's in-progress comments |
| Mixing formatting changes with logic changes | Diff becomes unreadable; do formatting separately |
| Creating issue + PR simultaneously without thinking | Skips triage; you might be solving the wrong problem |
| Using stacked PRs when issues are actually independent | Manufactures sequential dependency; blocks parallel review |
| Ignoring `AGENTS.md` invariants in a PR | Re-litigates settled decisions; wastes reviewer time |
| Re-discovering facts already in `AGENTS.md` §3 | Wastes time; signal to update AGENTS.md if information was unfindable |
| **Opening a PR for AWS-touching code without API-level live test (4a)** | **Untested API path merges; bugs surface only in production. PR #50 deferred verification on the `clientToken` fix because the script's idempotent short-circuit hid the failing path.** |
| **Claiming a feature done after API-level test only — deferring functional verification (4b)** | **Stored API state ≠ working feature. Memory wired ≠ memory recalls. Skill referenced ≠ skill loads. PR #51/#54/#55 all merged with deferred 4b — leaving runtime behavior unverified. Always invoke and observe.** |
| **Splitting the "real test" into a separate post-merge issue** | **If the test is needed to verify the feature, it's part of the feature. Same PR or a prerequisite PR — never a follow-up. "We'll test it later" is how features ship broken.** |

---

## Worked example: the v0.2.1 documentation audit

(Same as before — 8 parallel doc-only PRs, all exempt from 4a/4b
because they were documentation only.)

The full table and rationale stays the same.

---

## When to deviate

This workflow is the default, not a law. Reasonable exceptions:

- **Trivial typo:** Fix in a small PR without filing an issue.
- **Security hotfix:** Open the PR immediately; file the issue
  afterward for tracking. Do not wait for triage. 4a + 4b verification
  may be deferred only if delaying the fix is more dangerous than
  shipping unverified — document the rationale + commit to immediate
  post-merge verification.
- **Cohesive feature with unavoidable cross-cutting changes:** A
  single feature PR can touch multiple files if they form one
  logical unit.
- **Mass renames or codebase-wide refactors:** Sometimes one big
  PR is correct.
- **Dual-source learning:** PR #42 added `AGENTS.md` (the artifact)
  and `docs/methodology/agent-onboarding.md` (the rationale) in
  one PR because they're tightly coupled.

If you deviate, say so in the PR description and explain why.

**Step 4 (4a + 4b) is NOT a deviation candidate.** If 4b genuinely
cannot be tested pre-merge (e.g. depends on same-PR content reaching
main), split into prereq + main PR. "We'll test post-merge" or "cost
is too high" is never an acceptable rationale.

---

## How this interacts with the rest of the methodology

| Concern | Document |
|---|---|
| Repo invariants and topology that don't change per PR | [`AGENTS.md`](../../AGENTS.md) |
| How to make any repo legible to AI agents | [`agent-onboarding.md`](agent-onboarding.md) |
| **How to land changes in this repo (this doc)** | `change-discipline.md` |
| Practical PR/issue templates and naming conventions | [`docs/DEVELOPMENT_WORKFLOW.md`](../DEVELOPMENT_WORKFLOW.md) |

Order of consultation when planning a change:

1. **`AGENTS.md`** — does my change violate an invariant?
2. **Open `discussion` issues** — is there an unresolved decision
   in this area?
3. **`change-discipline.md`** (this doc) — is this a stack-eligible
   sequential change, or just one parallel issue? Does my 4b plan
   require a 2-PR stack?
4. **`docs/DEVELOPMENT_WORKFLOW.md`** — what does the issue / PR
   template look like for this repo?
5. **The PR template itself** — both 4a and 4b checkboxes ticked
   with evidence?

---

## Maintenance

This document and the templates only work if they stay accurate.

- **Update when reality drifts.** New invariants, new gotchas, new
  patterns — update in the same PR as the change that produces them.
- **Update the worked example when a better one exists.**
- **Don't let `DEVELOPMENT_WORKFLOW.md` and this doc drift.** If you
  change one, change the other in the same PR.
- **Anti-patterns observed in practice are signals to update the
  templates.** Step 4 live-test (4a) was added in PR #53 after PR #50
  demonstrated the gap. Step 4b functional-test was added in this PR
  after PRs #51/#54/#55 demonstrated the next gap.

---

## Origin and bidirectional inspiration

This methodology has a bidirectional lineage:

1. **Originally written here** as
   [`docs/DEVELOPMENT_WORKFLOW.md`](../DEVELOPMENT_WORKFLOW.md)
   in PR #3 (v0.2.1 audit, May 2026).

2. **Adapted and matured** in
   [`timwukp/dora-metrics-platform/docs/methodology/change-discipline.md`](https://github.com/timwukp/dora-metrics-platform/blob/main/docs/methodology/change-discipline.md).

3. **Adopted back here** as this file (PR #44, May 2026).

4. **Step 4 API-level live-test mandate added** (PR #53, June 2026)
   after PR #50 demonstrated that "deferred verification post-merge"
   creates latent bugs.

5. **Step 4 expanded to 4a + 4b functional-test mandate** (PR #N,
   June 2026) after PRs #51/#54/#55 demonstrated that API-level
   passing ≠ feature working. Maintainer's standard: comprehensive
   testing before PR, no deferrals.

The pattern keeps maturing as gaps surface.

Adopt, adapt, or ignore. The core idea — *issue → fix → PR, one
logical change at a time, comprehensively tested, methodology
versioned and dogfooded* — is the durable bit.
