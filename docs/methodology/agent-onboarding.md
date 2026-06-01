# Methodology: Agent-Ready Repository Pattern

A reusable pattern for making a repository legible to any AI coding
agent — Claude Code, Cursor, Codex, Aider, GitHub Copilot, or
whatever comes next — without re-explaining context every session.

This document describes the *method*, not the specific contents of
this repository. It is intended to be copied or referenced when
setting up any new repository, or retrofitted onto existing ones.

> **Sibling doc:** [`change-discipline.md`](change-discipline.md) —
> the change-landing methodology (issue granularity, PR sizing, anti-
> patterns, stacked PRs). The two together form the agentic dev kit.

> **In this repo:** the methodology is implemented via [`AGENTS.md`](../../AGENTS.md)
> at root, [`docs/DEVELOPMENT_WORKFLOW.md`](../DEVELOPMENT_WORKFLOW.md) for
> the issue → fix → PR loop, [`change-discipline.md`](change-discipline.md)
> for the abstract change methodology, and (optionally) GitHub issues
> with the `discussion` label for architectural questions. See "Origin"
> at the bottom for source attribution.

---

## The problem

When you collaborate with an AI coding agent across multiple
sessions, or hand the repo to a *different* agent, you typically
end up re-explaining the same things every time:

- "Don't expose this endpoint, it's trial-mode only"
- "Use `--platform linux/arm64`, AgentCore Runtime requires arm64"
- "We use Bedrock, not Anthropic direct"
- "boto3 1.42.x doesn't have Harness ops; use 1.43.18+"

Each session starts cold. The agent reads the code and infers what
it can, but **invariants and external constraints are not in the
code** — they live in the maintainer's head, in Slack, in old
issues, or worse, only in the maintainer's memory of a past
conversation.

Same problem applies to GitHub issues: an issue titled "should we
do X or Y?" is meaningful when you remember the conversation that
led to it. Six months later, or to a new contributor, it reads as
neutral options when in fact you already had a strong preference.

---

## The pattern

Two artifacts, kept in lockstep:

```
┌─ Repo root ──────────────────────────────────────┐
│                                                  │
│  AGENTS.md  ◄── invariants, topology, dev loop   │
│                 (read by every agent on entry)   │
│                                                  │
│  GitHub issues with `discussion` label           │
│       │                                          │
│       └── each contains:                         │
│           1. Context                             │
│           2. Working assumptions  ◄── your prior │
│           3. Open questions                      │
│           4. Repo context (links to AGENTS.md,   │
│              SECURITY.md, related code paths)    │
│                                                  │
└──────────────────────────────────────────────────┘
```

**`AGENTS.md`** is the repo-wide entry point. It captures things
that don't belong in any specific issue because they apply to
*everything*: invariants, deployment topology, dev loop, doc index.

**Discussion issues** are the per-decision entry points. Each one is
self-contained — a future agent (or human) reading it cold should
get full context without further explanation.

The two cross-link: AGENTS.md points at the doc index and the
"open issues with `discussion` label" filter; each discussion issue
links back to AGENTS.md in its "Repo context" section.

> **In this repo:** AGENTS.md exists at root and is cross-linked from
> README. The `discussion` label is reserved for future architectural
> questions; the `enhancement` / `bug` / `documentation` labels cover
> regular feature / fix work, which uses the `docs/DEVELOPMENT_WORKFLOW.md`
> issue → fix → PR loop instead. Apply `discussion` when you want
> input *before* committing to a direction.

---

## What goes in `AGENTS.md`

`AGENTS.md` is a convention starting to converge across agent
tooling. OpenAI Codex, Cursor, Aider, and Claude Code all surface
or auto-read it. Treat it as the file every new collaborator —
human or AI — reads first.

Recommended sections (in this order):

### 1. What this project is — 3-5 sentences

Just enough that an agent landing here knows what they're looking
at. Link out to README for details. Don't duplicate.

### 2. Invariants — the most important section

A table of repo-wide constraints, each with a one-line *why*. Format:

```markdown
| # | Invariant | Why |
|---|---|---|
| 1 | Repository stays PUBLIC, no account IDs/secrets in git. | Maintainer's policy, repo is reference material for others. |
| 2 | Demo PR #1 stays open, do not merge. | Live demo of CI/CD pipeline; merging breaks it. |
| 3 | boto3 ≥ 1.43.18 required for harness ops. | Earlier versions silently lack the API. |
```

Invariants are things that are **not derivable from the code**.
"Use TypeScript" doesn't belong here — `tsconfig.json` says that.
"`harness_*` runtimes are managed by the harness API" *does* belong here — nothing in
the code enforces it; it's an AWS-side constraint with concrete consequences.

Each invariant needs a *why*, not just a rule. Future-you (and
agents) need the *why* to judge edge cases.

### 3. Deployment topology

What the actual running system looks like. Include:

- Environments and their differences (trial vs prod, staging vs prod)
- Where things run (cluster names if non-sensitive, region, account
  kind without exposing IDs)
- Storage / database / queue topology
- How configuration differs between environments

Don't include account IDs, cluster ARNs, internal hostnames, or
anything that would be a finding if the repo went public.

### 4. Local development loop

The exact commands a contributor runs while iterating. Test, lint,
build, render manifests, run the stack. If CI does it, document the
local equivalent so the contributor doesn't push to find out.

Include any non-obvious environment quirks (Apple Silicon needing
`--platform linux/arm64`, Node version pinning, secrets needed
to run tests, AWS CLI version pin).

### 5. How decisions are recorded

Tell the agent where to find the *why* behind code that doesn't
explain itself. Three common choices:

- ADRs (`docs/adr/NNN-*.md`) — heavyweight, formal
- GitHub issues with a `discussion` label — lightweight, distributed
- Phase test reports / build logs — narrative, time-stamped

Pick one or two and say so. The point is that the agent knows
*where to look* before making a change in an area with prior
context.

> **In this repo:** GitHub issues with structured Problem / Evidence /
> Acceptance Criteria template (`docs/DEVELOPMENT_WORKFLOW.md`) cover
> feature work. Reserve the `discussion` label for genuinely
> architectural decisions where the path isn't yet clear.
> The change-landing discipline itself is documented in
> [`change-discipline.md`](change-discipline.md).

### 6. Communication conventions

How the maintainer wants to be talked to. Examples:

- "Be terse"
- "Pin claims to file paths and line numbers"
- "When uncertain, ask one question and stop"
- "Match scope to ask — don't bundle unrelated cleanup"

These are the things you currently have to repeat every session.
Write them down once.

### 7. Doc index

A table of "if you're looking for X, read Y." This is the agent's
map. Keep it under 10 rows — if it grows past that, the docs
themselves are too sprawling.

### 8. For agents specifically

A short final section addressing AI agents directly. What to do on
arrival, what to skim, what NOT to do (don't invent context, don't
write planning docs unless asked, don't auto-format the codebase).

---

## What goes in a `discussion` issue

The pattern, applied to a single architectural decision:

```markdown
## Context
What's the situation today, in 1-2 paragraphs.

## Working assumptions (read this first)
The maintainer's priors. State preferences explicitly:
- "Maintainer leans toward X over Y because Z."
- "Constraint A is hard; constraint B is soft."
- "Tool C is in scope; tool D is not."

## The architectural question
The actual decision, with a comparison table if there are multiple
paths. Be neutral *here* — the priors above already showed your hand.

## Why it's non-trivial for our setup
What's specific about this repo that makes the textbook answer wrong.

## Proposed direction
The maintainer's current best guess. Not a decision — an anchor for
discussion.

## Open questions
Numbered list. These are what the next iteration will resolve.

## Non-goals
What this issue explicitly is NOT about. Prevents scope creep.

## Repo context
Links to AGENTS.md, SECURITY.md, related code files, and any prior
test reports or PRs that produced the current state.
```

The "Working assumptions" section is the single biggest improvement
over a normal issue. Without it, a future agent reads the comparison
table and can't tell which side you're on. With it, they can either
proceed in your direction or push back with a reason.

The "Repo context" section is what makes the issue **self-contained**.
A new agent reading the issue cold should be able to follow the
links and have full context to act, without asking the maintainer
for anything.

> **Discussion vs feature issue (this repo's heuristic):**
> - **Feature issue** (use `enhancement` / `bug` / `documentation` label):
>   You already know *what* to do. The issue defines acceptance criteria.
>   Example: "feat(memory): configure 4-strategy Memory on UITestAgentHarness".
> - **Discussion issue** (use `discussion` label): You don't yet know
>   the right answer. The issue exposes the tradeoffs and your priors,
>   collects input, and converges on a direction. Often spawns one or
>   more feature issues afterwards.

---

## When to apply this pattern

**Always:** A new repo with a non-trivial deployment story or
security baseline. AGENTS.md is cheap to write and pays back the
first time you switch agents or onboard a contributor.

**Retrofit:** An existing repo where you find yourself
re-explaining the same things every session. The cost is one
afternoon; the savings compound.

**Skip:** A throwaway script, a personal scratchpad, a repo with
zero invariants beyond "the code". AGENTS.md adds noise if it has
nothing to say.

---

## Maintenance

The pattern only works if the artifacts stay accurate. A stale
`AGENTS.md` is worse than no `AGENTS.md` because it confidently
misleads.

A practical rhythm:

1. **Add to AGENTS.md the moment you correct an agent.** If you
   say "no, don't do that, we always X" — that's an invariant.
   Write it down before the next session starts.
2. **Open a discussion issue when an open question would be
   useful to anyone other than you.** If you're undecided about
   architecture, write it up. Future-you is grateful.
3. **Review AGENTS.md whenever the deployment topology changes.**
   New environment, new dependency, new constraint — update the
   doc in the same PR.
4. **Close discussion issues when the decision is made.** The
   issue becomes the historical record of *why*. Reference it from
   the commit that implements the decision.
5. **Add new gotchas to AGENTS.md §3 (hard-learned facts) as you
   discover them.** This is how the repo's collective memory grows.

---

## What this is not

- **Not a substitute for ADRs** if your team uses them. AGENTS.md
  is the entry-point summary; ADRs are the deep dives. The two
  coexist.
- **Not a replacement for code comments.** Comments explain code;
  AGENTS.md explains the *system around* the code.
- **Not a planning doc.** Don't dump in-progress thoughts or task
  lists here. Use the conversation, a plan, or a draft PR.
- **Not for secrets, credentials, or anything that shouldn't be in
  git.** Account IDs, internal hostnames, Slack channel names, and
  similar lightly-sensitive data are best left out — even on a
  PRIVATE repo, branches get mirrored to forks and AI agents read
  the file into their context.

---

## Origin and attribution

This methodology is **adapted from**:

> [`timwukp/dora-metrics-platform/docs/methodology/agent-onboarding.md`](https://github.com/timwukp/dora-metrics-platform/blob/main/docs/methodology/agent-onboarding.md)

Originally extracted from observing the same context being
re-explained across multiple agent sessions on the
`dora-metrics-platform` project. This file is a near-verbatim
adaptation with project-specific examples updated for the AgentCore
context (boto3 versions, harness gotchas, etc.).

In this repo, the first applications are:

- This file: `docs/methodology/agent-onboarding.md`
- The repo's [`AGENTS.md`](../../AGENTS.md) — capturing AWS Bedrock
  AgentCore SDK / API gotchas as institutional memory (PR #42)
- The repo's [`docs/DEVELOPMENT_WORKFLOW.md`](../DEVELOPMENT_WORKFLOW.md)
  — the issue → fix → PR loop used in v0.2.1 audit (PR #3) and
  ongoing v0.2.2 harness configuration work
- Sibling methodology: [`change-discipline.md`](change-discipline.md)
  — added in PR #43 alongside this file's cross-link update

Adopt, adapt, or ignore. The core idea — *make context durable so
agents don't need to be re-onboarded* — is the durable bit; the
specific section names and structure are not.
