# Issue #26 — Wire UITestAgentHarness to ui-testing/SKILL.md

## Summary

`UITestAgentHarness` previously had **0 skills** configured (per AWS console).
The skill file `app/ui-test-agent/skills/ui-testing/SKILL.md` already existed
in the repo with substantial domain knowledge but was never wired in.

This issue wires the harness to that skill **programmatically** via
`update_harness(skills=[...])` using the `git` source variant.

## API discovery findings

These extend AGENTS.md §3.2 (candidate addition for §3.2.5 in a follow-up
doc PR — kept out of this PR to preserve "one logical change per PR"):

### `UpdateHarness skills.member` shape (boto3 introspection)

```
skills: list of structure
skills.member:
    path: string                        # local container path
    s3: structure
        uri: string (required)          # S3-hosted bundle
    git: structure
        url: string (required)          # repo URL
        path: string                    # sub-path within repo
        auth: structure
            credentialArn: string
            username: string
    required: []
```

Each list item picks **one** of `path` / `s3` / `git`. The required structure
is `[]` at top level — but inside `git` and `s3`, the `url` / `uri` fields
are required.

### Three sources, three trade-offs

| Source | Pros | Cons | When to use |
|---|---|---|---|
| `path` | Fastest startup; no network | Needs Container (#21) or volume | Production with Container |
| `s3` | Versioned bundles; access control via S3 IAM | Extra deploy step; bucket cost | Distributing to many harnesses |
| `git` | Lives with code; git history; no deploy step | Per-session network fetch | Public repo, fast iteration, small skills |

This issue uses **`git`** because:
- The skill file already lives with the code (no separate deploy)
- This repo is PUBLIC (no auth needed)
- The skill is small (~50 lines markdown; network fetch is negligible)
- Decouples #26 from #21 (Container) — skill wiring lands first

When #21 (Container mode) lands, the skill bundling can switch to `path`
(if startup latency matters) without changing the skill content.

### `skills` is plain list-of-structure (no `optionalValue` wrapper)

Consistent with AGENTS.md §3.2.1 type-driven rule: only complex structure
fields use `optionalValue`. `skills` is `list of structure` — pass directly:

```python
control.update_harness(
    harnessId=...,
    skills=[{"git": {"url": "...", "path": "..."}}],   # ✅ plain list
    clientToken=secrets.token_hex(20),
)
```

NOT:

```python
skills={"optionalValue": [...]}    # ❌ would fail validation
```

## Live verification

### Apply (first run)

```
$ python agentcore/scripts/wire_skills.py
boto3 1.43.18 OK
Region:  us-east-1
Account: <ACCOUNT_ID>
Mode:    APPLY

=== UITestAgentHarness ===
  arn:    arn:aws:bedrock-agentcore:us-east-1:<ACCOUNT_ID>:harness/UITestAgentHarness-<ID>
  status: READY
  → drift detected:
      current  (0 skill(s)): []
      desired (1 skill(s)): [('git', 'https://github.com/timwukp/Harness-agentic-AI-agent-best-practices-and-use-case', 'app/ui-test-agent/skills/ui-testing', ())]
  ✓ update_harness HTTP 200
  status=UPDATING (waiting 5s)
  status=UPDATING (waiting 5s)
  ✓ status=READY

✓ All applicable updates applied successfully
```

### Idempotent re-run

```
$ python agentcore/scripts/wire_skills.py
boto3 1.43.18 OK
Mode:    APPLY

=== UITestAgentHarness ===
  arn:    ...harness/UITestAgentHarness-<ID>
  status: READY
  ✓ skills already match desired (1 skill(s), no update)
    - git: https://github.com/timwukp/Harness-agentic-AI-agent-best-practices-and-use-case:app/ui-test-agent/skills/ui-testing

✓ No changes needed (idempotent re-run safe)
```

### Live `get_harness` evidence

```json
{
  "status": "READY",
  "skills": [
    {
      "git": {
        "url": "https://github.com/timwukp/Harness-agentic-AI-agent-best-practices-and-use-case",
        "path": "app/ui-test-agent/skills/ui-testing"
      }
    }
  ]
}
```

The AWS console (Bedrock AgentCore → Harness → UITestAgentHarness → Skills
section) shows the same configuration — no longer "0".

## Acceptance criteria status

| Criterion | Status | Notes |
|---|---|---|
| SKILL.md reviewed and content quality verified | ✅ | Already covers all 6 sections (methodology / interaction patterns / what to check / severity / failure patterns / report + edge cases). No gaps required filling. |
| Skill wired into harness | ✅ | Via `git` source (decouples from #21) |
| Console Skills section shows ≥ 1 skill path | ✅ | live verified |
| Idempotent script | ✅ | re-run is no-op (no API mutations) |
| VERIFICATION doc with payload + evidence | ✅ | this file |
| System prompt is shorter than current | ⏳ | **Deferred** — current systemPrompt is already 269 chars (only role definition, no methodology). This issue ADDS skill context rather than replacing prompt content. Token-saving prompt trim is a future optimization once the skill is verified to be loaded correctly during agent invocations. |
| Functional test: agent reasoning trace references skill | ⏳ | requires test invocation post-merge |
| Token usage per session ↓ | ⏳ | requires multi-session measurement post-merge |

## Methodology dogfooding

This issue is the **third issue** to apply the v0.2.2 methodology trio in full:

1. **Issue body** (Phase 1 audit, batch-updated): had Repo context section,
   AGENTS.md §3.2.1 reference, sibling issue links, hypothesis markers
2. **Implementation** followed the change-discipline.md 5-step loop:
   - **Discover** — boto3 schema introspection (the 3-source variants table)
   - **Triage** — P0, no blocker dependencies (the issue body's "soft dep on
     #21" was wrong: `git` source decouples this entirely)
   - **Group** — 1 logical change (script + verification + harness wire)
   - **Fix** — `wire_skills.py` + this verification
   - **Review** — this PR
3. **Pattern reuse** — script structure modeled on `tighten_harness_config.py`
   (PR #47): version check, name discovery, idempotent comparison,
   `redact()` helper, `--dry-run` mode, `secrets.token_hex(20)` clientToken
4. **AGENTS.md gotcha consumed** — used §3.2.3 (clientToken length) from
   day 1 without rediscovery (vs. PR #47 which discovered it the hard way)

This is also a **methodology improvement validation**: the issue body's
"soft dep on #21" hypothesis was discharged by `git` source discovery.
The issue audit's Suggested approach + ⚠️ hypothesis markers worked
exactly as designed — implementer is invited to deviate with reason.

## Out of Scope (filed as candidate follow-ups)

- **AGENTS.md §3.2.5 enrichment** — `skills.member` 3-source structure
  belongs in AGENTS.md institutional memory; separate doc PR (similar
  to how PR #49 enriched after PR #47)
- **System prompt trim** — current prompt is already minimal; aggressive
  trim is a future optimization once skill loading is verified live
- **Switch to `path` source** — when #21 (Container) lands and startup
  latency justifies it
- **Bug-Fix Agent skill** — issue **#27** (parallel work)

## Risk

**Low.** Read-modify-write on one harness via public, versioned API.
Idempotent — safe to re-run. Mutation has already happened in production;
this PR codifies the operation as a maintainable script and documents
the API discoveries.

If `git` fetch at session start ever fails (e.g. repo deletion, network
issues), agent falls back to no skill (system prompt only) — no crash.
Rollback: edit `DESIRED.UITestAgentHarness.skills` to `[]` and re-run.
