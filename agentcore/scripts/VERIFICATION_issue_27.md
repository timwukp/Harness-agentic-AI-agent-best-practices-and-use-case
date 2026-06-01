# Issue #27 — BugFixAgent skill: create + wire

## Summary

`BugFixAgentHarness` previously had **0 skills** configured. Unlike #26 (UI Test
Agent) where the SKILL.md already existed, this issue required:

1. **Writing** `app/ui-test-agent/skills/bug-fixing/SKILL.md` with substantive content
2. **Extending** `agentcore/scripts/wire_skills.py` to wire both harnesses

Single PR for both because the wire references the skill file's path — they
must land together for runtime fetch to succeed (post-merge, when SKILL.md is on `main`).

## API discovery findings

(Continuing the rhythm: PR #47 → PR #49 doc PR; PR #51 + PR #54 + this PR → next doc PR
that lifts these into AGENTS.md §3.2.5 + §3.8.)

### `git` source has NO branch field

Schema introspection (per AGENTS.md §7.1):

```
skills.member.git: structure
    url: string         (required)
    path: string        (optional — sub-path within repo)
    auth: structure
        credentialArn: string
        username: string
required: ['url']
```

No `branch` field. AgentCore fetches from the repo's default branch (`main`)
at session start. Implications:

- **SKILL.md must be on main before the harness can actually load it.**
  The `update_harness` API call itself doesn't fetch — it just stores the
  reference. Validation happens only at session start.
- **Pre-merge live test verifies the API path but NOT content reachability.**
  Since this branch's SKILL.md isn't yet on main, a fetch right now would
  404. After merge, fetch will succeed.
- **No regression risk during the gap** — current state is `skills=[]`
  (no skill loads). After live-test stores the reference but before merge,
  any agent invocation would attempt fetch, fail, fall back to no-skill.
  Same as current state.

### Wire-by-update_harness shape (already known from PR #51, reaffirmed)

```python
control.update_harness(
    harnessId=harness_id,
    skills=[                              # plain list — no optionalValue wrapper
        {
            "git": {                       # one of: path / s3 / git (UNION)
                "url": "https://github.com/...",
                "path": "app/ui-test-agent/skills/bug-fixing",
            }
        }
    ],
    clientToken=secrets.token_hex(20),    # AGENTS.md §3.2.3
)
```

## SKILL.md content overview

The skill is **substantive** (not placeholder), designed to guide agent
reasoning. Six sections per the issue body:

| Section | Length | Highlights |
|---|---|---|
| Methodology | ~25 lines | 5-step sequence: read failure → identify cause → minimal patch → run tests → propose PR. Distinguishes surface / logic / infrastructure bugs at step 2. |
| Patch generation rules | ~20 lines | Smallest diff, no opportunistic refactoring, unified-diff with 3 lines context, preserve existing style, one logical change per PR |
| Severity-aware fixes | ~15 lines (table) | CRITICAL → rollback (don't fix forward under pressure); HIGH → standard fix + escalate sensitive; MEDIUM → standard; LOW → defer or trivial |
| Common patterns | ~12 lines (table) | Bug-type → fix locus → typical LOC. Includes "React hydration flash" as the not-a-bug case. |
| When to ask for human approval | ~15 lines | 5 explicit triggers (auth/payment/deletion paths, refactor, >50 LOC, new dependency, modified failing tests, disabled guards). Pre-#33 fallback: draft PR + @maintainer mention. |
| Anti-patterns | ~25 lines (table) | 10 specific patterns — including "trust the prompt-injected source snippet" (use GitHub MCP post-#30) and "modify the agent's own code" |

Plus a **structured output format** at the end — JSON the orchestrator parses
to decide approval routing (`needs_human_approval=true/false`). Bridges this
skill to issue #33's `request_pr_approval` inline function.

## Configuration

### Why same `app/ui-test-agent/skills/` directory

The directory naming is a bit awkward (`bug-fixing` lives inside `ui-test-agent`'s
folder), but:
- Preserves existing `skills/` structure that the issue body explicitly named
- Both skills are project-internal artifacts (not separate repos)
- Reflects the relationship: BugFix Agent is a downstream of UI Test Agent in the pipeline

### Single script, two harnesses

`wire_skills.py` `DESIRED` now has both entries:

```python
DESIRED = {
    "UITestAgentHarness": {
        "skills": [{"git": {"url": REPO_URL, "path": "app/ui-test-agent/skills/ui-testing"}}]
    },
    "BugFixAgentHarness": {
        "skills": [{"git": {"url": REPO_URL, "path": "app/ui-test-agent/skills/bug-fixing"}}]
    },
}
```

One source of truth for skill wiring across the project. Adding a future
3rd harness is a 5-line edit.

## Live verification (mandatory per change-discipline.md Step 4)

### Apply

```
$ python agentcore/scripts/wire_skills.py
boto3 1.43.18 OK
Mode:    APPLY

=== UITestAgentHarness ===
  arn:    arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:harness/UITestAgentHarness-<ID>
  status: READY
  ✓ skills already match desired (1 skill(s), no update)
    - git: https://github.com/timwukp/Harness-agentic-AI-agent-best-practices-and-use-case:app/ui-test-agent/skills/ui-testing

=== BugFixAgentHarness ===
  arn:    arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:harness/BugFixAgentHarness-<ID>
  status: READY
  → drift detected:
      current  (0 skill(s)): []
      desired (1 skill(s)): [('git', 'https://github.com/timwukp/Harness-agentic-AI-agent-best-practices-and-use-case', 'app/ui-test-agent/skills/bug-fixing', ())]
  ✓ update_harness HTTP 200
    status=UPDATING (waiting 5s)
    status=UPDATING (waiting 5s)
  ✓ status=READY

✓ All applicable updates applied successfully
```

PR #51's UITestAgentHarness state is preserved (idempotent — same script verified
two harnesses' state in one run).

### Idempotent re-run

```
=== UITestAgentHarness ===
  ✓ skills already match desired (1 skill(s), no update)

=== BugFixAgentHarness ===
  ✓ skills already match desired (1 skill(s), no update)

✓ No changes needed (idempotent re-run safe)
```

Zero API mutations on second run for either harness.

### Live `get_harness` final state

```json
// UITestAgentHarness
{
  "skills": [{"git": {"url": "...", "path": "app/ui-test-agent/skills/ui-testing"}}]
}

// BugFixAgentHarness
{
  "skills": [{"git": {"url": "...", "path": "app/ui-test-agent/skills/bug-fixing"}}]
}
```

Both harnesses now have skills configured in the AgentCore console.

## Acceptance criteria status

| Criterion | Status | Notes |
|---|---|---|
| `app/ui-test-agent/skills/bug-fixing/SKILL.md` exists with all 6 sections | ✅ | this PR |
| BugFixAgentHarness Skills section shows ≥ 1 skill path | ✅ | live verified |
| Idempotent script | ✅ | re-run is no-op for both harnesses |
| **Live-test on AWS BEFORE this PR** (per Step 4) | ✅ | done in this branch BEFORE PR open; evidence above |
| System prompt is shorter | ⏳ | **deferred** — current prompt is short already; trim is post-merge once skill is verified loading |
| **Functional test:** agent's output references methodology from skill | ⏳ | **deferred** — needs SKILL.md on main + test invocation; impossible pre-merge per "no branch field" finding |
| Generated diff still produces correct fix on demo bug | ⏳ | **deferred** — requires e2e_pipeline.py test post-merge |

## Methodology dogfooding

This is the **second forward-implementation PR under PR #53's mandatory live-test rule** (after PR #54 BugFix Memory).

1. **Schema introspection (§7.1) at Step 0** revealed the no-branch-field detail —
   directly informed the "alternative verification path" rationale for content fetch
2. **Live APPLY** confirmed both harnesses get processed correctly, idempotency preserved
3. **Pattern reuse** — extending the existing `wire_skills.py` script (single source
   of truth for skill wiring) rather than writing a sibling. The DESIRED dict pattern
   scales to N harnesses cleanly.
4. **AGENTS.md §3.2.1** (skills is plain list-of-struct, no wrapper) consumed cleanly
5. **AGENTS.md §3.2.3** (clientToken length) consumed cleanly — no rediscovery cost
6. **Alternative verification path** documented explicitly in PR description AND
   acceptance criteria — per change-discipline.md "When to deviate" guidance.
   The git-no-branch limitation is a real impediment to pre-merge content-reachability
   testing; documenting why and what's deferred is the rule-compliant move.

## Out of Scope (filed as candidate follow-ups)

- **AGENTS.md §3.2.5 enrichment** — `skills.member` 3-source UNION + no-branch-field
  discovery (from PR #51 + this PR)
- **AGENTS.md §3.8 enrichment** — `CreateMemory.memoryStrategies` UNION + reflection-prefix
  (from PR #54)
- These two could land in ONE follow-up doc PR (~50 lines added)
- **Functional test** post-merge: invoke BugFixAgent on demo bug, verify reasoning
  trace references skill methodology
- **System prompt trim** — once skill loading is verified live
- **Switch to `path` source** when #21 lands and startup latency matters

## Risk

**Low.** Two-file change (skill content + 1-section script extend). Idempotent.
Rollback = `DESIRED["BugFixAgentHarness"]["skills"] = []` and re-run. Skill
content failure mode is "fall back to system prompt only" — same as current state.

If anything goes wrong post-merge:
1. `update_harness(harnessId=BugFix, skills=[])` to detach (set DESIRED to `[]` and re-run)
2. Open follow-up issue with diagnosis
