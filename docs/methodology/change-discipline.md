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
4. **Live-test on AWS** for any code touching AWS APIs. ⚠️ **Mandatory.** Required:
   - Apply the change against your AWS account (the actual API call, not just `--dry-run`)
   - Re-run the script to confirm idempotency (no API mutations on second run)
   - Confirm target state via `get_*` / `list_*` / `describe_*` API calls
   - Capture redacted evidence for the PR description's Verification section

   Doc-only PRs are exempt. If the change is genuinely too risky to test
   live (e.g. destructive operation on shared infrastructure), document
   the explicit rationale in the PR description and propose an alternative
   verification path. Deferring "verification will happen post-merge" is
   not acceptable — that creates the PR #50 / #46 latent-bug pattern.

5. **Open PR** using the PR template. Title mirrors the issue.
6. PR description includes `Closes #N` so GitHub auto-closes the
   issue on merge.

**Don't:**
- Bundle unrelated changes "while you're in there"
- Open a PR before the issue exists (except trivial typos and
  security hotfixes — see "When to deviate" below)
- Reuse a branch for a second issue
- Open a PR for AWS-touching code without live verification (see Step 4 above)

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
- Each PR in the stack still passes its own acceptance criteria
- The stack is small (≤ 5 PRs); larger stacks become ungovernable

**This repo has not yet needed a stack.** All v0.2.1 audit work
(PRs #3-#16) and v0.2.2 harness configuration so far (PRs #39, #40,
#42) was filed as parallel independent PRs because no two issues
had a hard sequential dependency.

For an example of stacked PRs done well, see the dora-metrics-platform
phase 1–6 install-friction stack
([`docs/test-reports/phase6-rollup.md`](https://github.com/timwukp/dora-metrics-platform/blob/main/docs/test-reports/phase6-rollup.md)),
where each phase needed the previous phase's changes to be testable:

| PR | Base | Why this depended on the previous |
|---:|---|---|
| #34 | `main` | Doc + script fixes — prerequisite for everything |
| #35 | #34 branch | Kustomize overlays — needed phase 1's variable resolution |
| #36 | #35 branch | Alembic migrations — needed phase 2's Postgres |
| #37 | #36 branch | Fargate detection — needed phase 3's lifespan |
| #38 | #37 branch | Helm chart — packaging on top of phase 4 |

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

This repo doesn't have an active `discussion`-labeled issue yet
(the label is reserved for future architectural questions; current
work is well-scoped feature/bug/docs issues). When one is opened,
this template applies.

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
- [ ] Concrete check 1
- [ ] Concrete check 2

## Priority
P0 / P1 / P2 / P3 — and why.

## Effort
Small (1 file, < 50 lines) / Medium (1 doc, 1 area) / Large (multi-file)

## Out of Scope
What this issue explicitly does NOT cover.
```

Examples in this repo: every issue from #2 onwards. See
`docs/DEVELOPMENT_WORKFLOW.md` for the canonical version.

### Pull request

```markdown
## Summary
Closes #N

One paragraph: what was wrong, what this PR changes.

## Changes
- `path/to/file1`: did X
- `path/to/file2`: did Y

## Verification
How a reviewer can confirm the change works:
- [ ] **Live-tested on AWS BEFORE this PR was opened** — apply +
      idempotent re-run + `get_*`/`list_*` verify path. Doc-only
      PRs are exempt; if AWS-touching code is here without live
      verification, explain why in the PR description (not
      acceptable: "verification post-merge").
- [ ] Local check: `cmd to run`
- [ ] Screenshot / output (redacted per AGENTS.md §5)
- [ ] Re-run of CI

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
- `docs/agents-md` (PR #42; predates the explicit `issue-N` convention but follows the type prefix)
- `docs/issue-43-change-discipline` (this PR)

For stacked PRs (the exception above), use a phase-prefixed name:
`phase1/docs-scripts-fixes`, `phase2/kustomize-overlays`, etc.

### Commits

[Conventional Commits](https://www.conventionalcommits.org/) format
is the project standard:

```
<type>(<optional scope>): <short summary>

<optional body>

<optional footer with Refs / Closes>
```

Examples (from this repo's actual history):

- `fix(readme): correct test count badge to 35 (#4)`
- `docs(architecture): add §6 Code Interpreter section (#8)`
- `feat(memory): rewrite attach_memory.py as programmatic + idempotent (#24)`
- `docs: add AGENTS.md with institutional memory for AI agents (#41)`

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
| **Opening a PR for AWS-touching code without live verification** | **Untested code merges; bugs surface only in production. PR #50 deferred verification on the `clientToken` fix because the script's idempotent short-circuit hid the failing path. Always live-test the actual path the change is fixing — apply + idempotent re-run + `get_*` verify — BEFORE opening the PR.** |

---

## Worked example: the v0.2.1 documentation audit

This repo's first systematic application of this discipline was the
v0.2.1 audit — a documentation-and-state sync that uncovered 8
distinct problems. Critically, it shows the **default case**: 8
parallel independent PRs with no stacking required.

**Discover (Step 1):** A read-through of README, PROJECT_STATE,
ARCHITECTURE, BEST_PRACTICES, DESIGN_UI_TEST_AGENT, and the actual
`main.py` source turned up 8 distinct categories of drift —
out-of-date badges, missing architecture sections, missing best-
practice sections in two languages, missing design doc sections,
and absence of a methodology doc itself.

**Triage (Step 2):** All 8 were P1 or P2 (visible drift, plus one
P0 meta-issue to add the methodology doc itself before tackling
the rest).

**Group (Step 3):** The 8 findings became 8 issues:

| Issue | PR | Title | Priority |
|---|---|---|---|
| #2 | #3 | Add development workflow guide (this methodology) | P0 |
| #4 | #5 | README badges out of sync (32→35, 96.9%→94.3%) | P1 |
| #6 | #7 | PROJECT_STATE.md sync, dedup Priority 4 | P1 |
| #8 | #9 | ARCHITECTURE.md add §6 Code Interpreter, §10.2 Eval Runner, §13 A2A | P2 |
| #10 | #11 | BEST_PRACTICES.md (EN + zh-TW) Browser features section | P2 |
| #12 | #13 | DESIGN_UI_TEST_AGENT + app/ui-test-agent/README sync | P2 |
| #14 | #15 | PRODUCTION_HARDENING.md design playbook | P3 |
| #16 | #17 | v0.2.1 release (VERSION + CHANGELOG + tag) | P1 |

**Fix (Step 4):** 8 individual PRs, each from `main`, each
independently mergeable, each ≤ 200 lines. No stacking needed
because no two issues had a hard sequential dependency — issue
#10's two languages had to land together but that's *one* issue,
not two PRs. (These were doc-only PRs, so Step 4's live-test
requirement was exempt — see Step 4 above.)

**Review (Step 5):** Each PR merged in priority order (P0 first,
then P1, then P2, then P3). Branches auto-deleted on merge.

**Result:** All 8 issues closed; v0.2.1 tagged. This is documented
in `CHANGELOG.md` and the v0.2.1 release notes.

**What we did NOT do:**

- ❌ One PR titled "Sync all docs"
  - Would be 2,000+ lines across 8 files. Unreviewable.
- ❌ 8 stacked PRs
  - No sequential dependency between them; stacking would have
    blocked parallel review and made each PR's base unstable.
- ✅ 8 parallel PRs, each from `main`, merged in priority order.

---

## When to deviate

This workflow is the default, not a law. Reasonable exceptions:

- **Trivial typo:** Fix in a small PR without filing an issue.
- **Security hotfix:** Open the PR immediately; file the issue
  afterward for tracking. Do not wait for triage. Live verification
  may be deferred only if delaying the fix is more dangerous than
  shipping unverified — document the rationale.
- **Cohesive feature with unavoidable cross-cutting changes:** A
  single feature PR can touch multiple files if they form one
  logical unit. The test is whether a reviewer can hold the whole
  change in their head.
- **Mass renames or codebase-wide refactors:** Sometimes one big
  PR is correct (e.g. renaming a class used in 50 files). Make the
  PR description loud about what changed and why a split would be
  worse.
- **Dual-source learning:** PR #42 added `AGENTS.md` (the artifact)
  and `docs/methodology/agent-onboarding.md` (the rationale) in
  one PR because they're tightly coupled — the artifact only makes
  sense with the methodology, and the methodology doc references
  the artifact.

If you deviate, say so in the PR description and explain why.
**Step 4 live-test is NOT a deviation candidate** — if it can't be
done, document the alternative verification path with the same rigor.

---

## How this interacts with the rest of the methodology

| Concern | Document |
|---|---|
| Repo invariants and topology that don't change per PR | [`AGENTS.md`](../../AGENTS.md) |
| How to make any repo legible to AI agents | [`agent-onboarding.md`](agent-onboarding.md) |
| **How to land changes in this repo (this doc)** | `change-discipline.md` |
| Practical PR/issue templates and naming conventions | [`docs/DEVELOPMENT_WORKFLOW.md`](../DEVELOPMENT_WORKFLOW.md) |

Order of consultation when planning a change:

1. **`AGENTS.md`** — does my change violate an invariant? (e.g.,
   exposing AWS account IDs, downgrading `boto3` below 1.43.18)
2. **Open `discussion` issues** — is there an unresolved decision
   in this area? (currently none active)
3. **`change-discipline.md`** (this doc) — is this a stack-eligible
   sequential change, or just one parallel issue?
4. **`docs/DEVELOPMENT_WORKFLOW.md`** — what does the issue / PR
   template look like for this repo?
5. **The PR template itself** — what does a reviewer need from me
   to approve?

---

## Maintenance

This document and the templates only work if they stay accurate.

- **Update when reality drifts.** If we adopt P0/P1/P2/P3 GitHub
  labels (currently triage-only), if we add commitlint, if the
  stacked-PR pattern stops being a hypothetical — update this doc
  in the same PR that makes the change.
- **Update the worked example when a better one exists.** The
  v0.2.1 audit is a good "default case" example today; if a future
  iteration produces a cleaner illustration, swap it in.
- **Don't let `DEVELOPMENT_WORKFLOW.md` and this doc drift.** They
  must agree on templates, naming, and process. If you change one,
  check the other in the same PR.
- **Anti-patterns observed in practice are signals to update the
  templates**, not nag in PR reviews. The template is the cheapest
  enforcement mechanism. (Step 4 live-test was added in PR #N after
  PR #50 demonstrated the gap.)

---

## Origin and bidirectional inspiration

This methodology has a bidirectional lineage:

1. **Originally written here** as
   [`docs/DEVELOPMENT_WORKFLOW.md`](../DEVELOPMENT_WORKFLOW.md)
   in PR #3 (v0.2.1 audit, May 2026) to support the 8-issue audit
   that produced v0.2.1.

2. **Adapted and matured** in
   [`timwukp/dora-metrics-platform/docs/methodology/change-discipline.md`](https://github.com/timwukp/dora-metrics-platform/blob/main/docs/methodology/change-discipline.md)
   — the dora-metrics-platform team applied our workflow to a
   different repo and added: stacked PRs (with the phase 1–6
   worked example), an explicit consultation-order section, and
   a maintenance discipline.

3. **Adopted back here** as this file (PR #44, May 2026), with the
   matured pattern integrated and the worked example swapped to
   our v0.2.1 audit (the parallel-PR default case) since this repo
   has not yet needed a stacked PR.

4. **Step 4 live-test mandate added** here (PR #N, June 2026) after
   PR #50 demonstrated the gap. The methodology continues to evolve
   as gaps surface.

The pattern keeps maturing as it travels between repos. If you
take it to a third repo, do the same: adapt the worked example,
keep the abstract structure, attribute the lineage.

Adopt, adapt, or ignore. The core idea — *issue → fix → PR, one
logical change at a time, with the methodology itself versioned
and dogfooded* — is the durable bit; the specific section names
and structure are not.
