# Development Workflow

> **Status:** Living document
> **Audience:** Anyone making changes to this repo (humans or AI agents)
> **Rule:** Read this before opening your first PR.

---

## Why this workflow

We use **issue → fix → PR**, one logical change at a time, instead of monolithic "big bang" PRs.

| Monolithic PR (avoid) | Iterative PRs (this repo) |
|---|---|
| 50 files changed, 30 unrelated concerns | One concern per PR |
| Reviewer must context-switch between issues mid-review | Reviewer focuses on one thing |
| Hard to revert one bad change without losing the rest | Revert = single `git revert` |
| Issue history is implicit ("see commits") | Each fix has an explicit issue with a paper trail |
| Bus factor: only the author knows what's in there | Anyone can pick up any open issue |

**This applies even when you find many problems at once.** Audit broadly, then file each finding as a separate issue. Don't try to fix everything in one PR just because you discovered everything in one read-through.

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
- Compare claims (README badges, status tables) against reality (test logs, commits)
- Find inconsistencies between files (e.g. doc says X, code does Y)
- Note out-of-date references and stale TODOs

**Output:** A flat list of all findings, no prioritization yet.

### Step 2: Triage (sort by priority)

Apply this scale:

| Level | Meaning | Example |
|---|---|---|
| **P0** | Meta / blocks other work | Add CONTRIBUTING.md before doing 6 contribution-style fixes |
| **P1** | Bug / contradiction visible to users | README badge says 32 tests but body says 35 |
| **P2** | Drift between code/doc reality | Architecture doc missing sections for tools that exist in code |
| **P3** | Future improvement, not currently broken | Production hardening design plan |

Also consider **relevance**: Does fixing X unblock Y? If yes, X is higher priority regardless of severity.

### Step 3: Group findings into issues

**One issue = one logical change with one acceptance criterion.**

Heuristics:

- ✅ Two badges and a paragraph that all reference the same out-of-date number → **one issue** (one logical fact)
- ✅ Three missing sections in the same doc → **one issue** (one doc, one purpose)
- ❌ "Fix all docs" → split into per-doc or per-concern issues
- ❌ "Add Code Interpreter section + fix unrelated typo" → split

**Rule of thumb:** If you can't write a single sentence describing what "done" looks like, the issue is too big.

### Step 4: Fix one issue at a time

For each issue:

1. **Branch** from `main`: `<type>/issue-<N>-<short-desc>`
   - `fix/issue-12-readme-badges`
   - `docs/issue-15-architecture-sections`
   - `feat/issue-20-container-deploy`
2. **Commit** with focused messages. Reference the issue: `fix: ... (#12)`
3. **Push** the branch
4. **Open PR** with title that mirrors the issue, body that uses the PR template (below)
5. PR description must include `Closes #N` so GitHub auto-closes the issue on merge

**Don't:**
- Bundle unrelated changes "while you're in there"
- Open a PR before the issue exists
- Reuse a branch for a second issue

### Step 5: Review and iterate

- Wait for review before starting the next issue (or at minimum, push current PR before context-switching)
- Apply review feedback as new commits to the same branch (don't force-push during review)
- Squash on merge if commits within the branch are noisy; keep them if each commit tells a coherent step
- After merge, delete the branch

---

## Templates

Copy-paste these when opening issues / PRs.

### Issue template

```markdown
## Problem

What is wrong, missing, or inconsistent. One paragraph.

## Evidence

- File path:line references
- Git commit SHAs that introduced or relate to the problem
- Screenshots if visual
- Quoted text from the offending file(s)

## Proposed Solution

Bullet list of changes you intend to make.

## Acceptance Criteria

- [ ] Concrete check 1
- [ ] Concrete check 2
- [ ] Concrete check 3

## Priority

P0 / P1 / P2 / P3 — and why.

## Effort

Small (1 file, < 50 lines) / Medium (1 doc, 1 area) / Large (multi-file)

## Out of Scope

What you are explicitly NOT doing in this issue. Helps prevent scope creep.
```

### PR template

```markdown
## Summary

Closes #N

One paragraph: what was wrong and what this PR changes.

## Changes

- `path/to/file1.md`: did X
- `path/to/file2.md`: did Y
- `path/to/file3.md`: removed Z

## Verification

How a reviewer can confirm the change works:

- [ ] Local check: `cmd to run`
- [ ] Screenshot / output
- [ ] Re-run of CI

## Out of Scope

What this PR does NOT change, but the original issue mentioned. Link to follow-up issue if any.

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

Examples:
- `fix/issue-12-readme-badges`
- `docs/issue-15-architecture-code-interpreter`
- `feat/issue-20-container-deploy`

### Commits

[Conventional Commits](https://www.conventionalcommits.org/) style:

```
<type>(<optional scope>): <short summary>

<optional body>

<optional footer with Refs / Closes>
```

Examples:
- `fix(readme): correct test count badge to 35 (#12)`
- `docs(architecture): add Code Interpreter section (#15)`
- `feat(deploy): switch UI Test Agent to Container mode (#20)`

### Pull request titles

Same format as commit messages. The PR title is what shows up in `git log` after squash-merge, so it matters.

---

## Anti-patterns to avoid

| Anti-pattern | Why it's bad |
|---|---|
| Big-bang PR with 30 unrelated changes | Unreviewable; can't revert one thing |
| Issue with no acceptance criteria | "Done" is a moving target |
| Branch named `update`, `temp`, `main2`, `wip` | Useless in `git log`, conflicts with parallel work |
| PR description "see commits" | Reviewer shouldn't have to reverse-engineer intent |
| Closing an issue without a merged PR | Loses traceability; future-you won't find the fix |
| Force-pushing during active review | Invalidates reviewer's in-progress comments |
| Mixing formatting changes with logic changes | Diff becomes unreadable; do formatting in a separate PR |
| Creating an issue and a PR simultaneously without thinking | Skips triage; you might be solving the wrong problem |

---

## Worked example: documentation audit

This repo's first systematic application of this workflow was an audit that uncovered seven distinct problems. Here's how they were grouped:

| Issue | Title | Priority | Why this priority |
|---|---|---|---|
| 1 | Add development workflow guide (this doc) | **P0** | Meta — establishes the methodology before applying it |
| 2 | README badges out of sync with verified test counts | **P1** | Visible front-page contradiction |
| 3 | PROJECT_STATE TODO checkboxes don't reflect completed work | **P1** | Internal state drift — misleads contributors |
| 4 | ARCHITECTURE.md missing dedicated sections for tools that exist in code | **P2** | Code/doc drift — claims vs reality |
| 5 | BEST_PRACTICES.md (EN + zh-TW) missing Browser feature sections | **P2** | Claims vs reality, two languages must stay in sync |
| 6 | DESIGN_UI_TEST_AGENT.md and app/ui-test-agent/README.md don't reflect current main.py | **P2** | Code/doc drift |
| 7 | Production hardening design doc (Container deploy, recording, profiles, etc.) | **P3** | Future work, design-only — no infra deploy in this PR |

**What we did NOT do:**
- ❌ Open one PR titled "Sync all docs and add hardening plan"
  - That PR would be 2,000+ lines across 8 files. Unreviewable.
- ❌ Open seven PRs in parallel
  - Reviewer fatigue + risk of merge conflicts between them.
- ✅ Open issues 1–7 first, then tackle them one PR at a time, sequentially, P0 first.

Each PR was small enough that a reviewer could load the entire context in their head and approve in under 10 minutes.

---

## When to deviate

This workflow is a default, not a law. Reasonable exceptions:

- **Trivial typo:** Fine to fix without an issue. Just commit to a small PR.
- **Security hotfix:** Don't wait. Open a PR immediately, file the issue afterward for tracking.
- **Cohesive feature with unavoidable cross-cutting changes:** A single feature PR can touch multiple files if they form one logical unit. The test is whether a reviewer can hold the whole change in their head.
- **Renames and mass refactors:** Sometimes one big PR is correct (e.g. renaming a class used in 50 files). Make the PR description loud about what changed.

If you deviate, say so in the PR description and explain why.

---

## Tooling notes

- **GitHub issues:** Use labels `bug`, `documentation`, `enhancement`, plus priority labels `P0`/`P1`/`P2`/`P3`
- **GitHub Actions:** CI must pass before merge
- **Branch protection:** `main` should require PR + review (configure in repo settings)
- **Commit signing:** Encouraged but not required

---

## Related

- [README.md](../README.md) — project overview
- [PROJECT_STATE.md](../PROJECT_STATE.md) — persistent project state
- [CHANGELOG.md](../CHANGELOG.md) — versioned change history

---

*This document is itself an example of the workflow it describes. See its issue and PR for the application of this process to its own creation.*
