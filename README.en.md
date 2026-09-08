[简体中文](./README.md) · [Website](https://riskshape.lei6393.com) · [GitHub](https://github.com/SuperMarioYL/riskshape)

<picture>
  <source media="(max-width: 600px) and (prefers-color-scheme: dark)" srcset="./assets/presentation/hero-mobile-dark.svg">
  <source media="(max-width: 600px)" srcset="./assets/presentation/hero-mobile-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="./assets/presentation/hero-dark.svg">
  <img src="./assets/presentation/hero-light.svg" width="960" alt="Hero diagram">
</picture>

# RiskShape

**Reuse explicit decisions for repeated agent actions**

RiskShape normalizes a tool call into an action shape, looks up recorded safe/unsafe labels in SQLite, and returns auto_approve or escalate according to its configured threshold.

## Why use it

Repeated permission prompts lose context when each decision starts from scratch. A local ledger makes prior labels visible, but only for the same normalized action shape; new or insufficiently labeled shapes still ask for review.

- **Inspect the evidence** — The grade reports safe/unsafe counts and the reason for its decision.
- **Keep a sample minimum** — A high label ratio alone does not approve a shape before min_samples is reached.
- **Escalate privileged scopes** — Recognized destructive, privileged-shell and pipe-to-shell scopes always escalate.

## Architecture

<picture>
  <source media="(max-width: 600px) and (prefers-color-scheme: dark)" srcset="./assets/presentation/architecture-mobile-dark.svg">
  <source media="(max-width: 600px)" srcset="./assets/presentation/architecture-mobile-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="./assets/presentation/architecture-dark.svg">
  <img src="./assets/presentation/architecture-light.svg" width="960" alt="Architecture diagram">
</picture>

shape.py derives a stable signature and capability scope from tool name and input. Ledger records labels and aggregates counts. Grader checks recognized privileged scopes, whether the shape has been seen, sample count and the safe-label fraction. Hook and MCP interfaces reuse that grader rather than maintaining separate rules.

| Component | Responsibility |
| --- | --- |
| `Tool input` | name and arguments |
| `Normalizer` | signature and derived scope |
| `SQLite ledger` | explicit outcome labels |
| `Grader` | threshold and escalation |
| `Hook / MCP` | decision and explanation |

## Install and quickstart

Python 3.10+ is supported; this source example uses a Python 3.12 virtual environment and uv.

```bash
git clone https://github.com/SuperMarioYL/riskshape.git
cd riskshape
uv venv --python 3.12
source .venv/bin/activate
uv pip install -e .
```

The script uses a fresh temporary SQLite ledger, fixed tau/min_samples and explicitly synthetic labels. It grades make build and sudo make build as strings without running them or installing a hook.

```bash
.venv/bin/python examples/presentation_demo.py
```

## Recorded demo

<picture>
  <source media="(max-width: 600px) and (prefers-color-scheme: dark)" srcset="./assets/presentation/process-mobile-dark.svg">
  <source media="(max-width: 600px)" srcset="./assets/presentation/process-mobile-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="./assets/presentation/process-dark.svg">
  <img src="./assets/presentation/process-light.svg" width="960" alt="Process diagram">
</picture>

Three safe labels approve the demo shape; one unsafe label returns it to escalation at tau=0.85.

```text
{"stage": "unseen", "shape": "make build", "scope": "build-install", "safe": 0, "unsafe": 0, "decision": "escalate"}
{"stage": "three safe labels", "shape": "make build", "scope": "build-install", "safe": 3, "unsafe": 0, "decision": "auto_approve"}
{"stage": "one unsafe label added", "shape": "make build", "scope": "build-install", "safe": 3, "unsafe": 1, "decision": "escalate"}
{"stage": "privileged despite labels", "shape": "sudo make build", "scope": "shell-privileged", "safe": 3, "unsafe": 0, "decision": "escalate"}
Scope: empirical label arithmetic; no commands executed or approval hooks installed.
```

The complete command and output are recorded in [docs/demo-results.json](./docs/demo-results.json). Inputs and reproduction code are included in the repository.

## Usage

grade explains one normalized shape; ledger lists labels and decisions. record --tool Bash "make build" safe adds an operator label to the selected database. converge replays its corpus in an isolated database; its default corpus is synthetic. hook-snippet prints integration configuration for inspection. riskshape mcp serve exposes the local MCP interface.

```bash
.venv/bin/riskshape grade --tool Bash "make build"
.venv/bin/riskshape ledger
.venv/bin/riskshape converge --json
.venv/bin/riskshape hook-snippet
```

## Configuration

RISKSHAPE_DB selects the SQLite path (default ~/.riskshape/ledger.db). RISKSHAPE_TAU defaults to 0.85 and RISKSHAPE_MIN_SAMPLES to 3. The decision requires enough labels and a safe fraction at or above tau, while recognized privileged scopes always escalate. init seeds default shapes; treat these as supplied labels rather than observations of your own commands.

## Integrations and responsibilities

<picture>
  <source media="(max-width: 600px) and (prefers-color-scheme: dark)" srcset="./assets/presentation/integrations-mobile-dark.svg">
  <source media="(max-width: 600px)" srcset="./assets/presentation/integrations-mobile-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="./assets/presentation/integrations-dark.svg">
  <img src="./assets/presentation/integrations-light.svg" width="960" alt="Integrations diagram">
</picture>

RiskShape recommends or emits a permission decision where a caller integrates it. It does not execute commands, prove they are safe, or install a sandbox. The safe-label fraction is an empirical property of the ledger, not a calibrated probability of future harm.

| Route | Implemented role |
| --- | --- |
| CLI | record / grade / ledger |
| Claude Code hooks | PreToolUse decision JSON |
| MCP | local grading and label tools |
| SQLite | persistent labels |
| JSON corpus | offline convergence replay |

## Limits and next steps

- Matching is based on normalized shape, not semantic equivalence or the current filesystem state.
- Capability detection is heuristic. The privileged-scope rule applies to recognized shapes, not every possible dangerous command.
- Synthetic label replay does not establish production safety, approval accuracy or compliance certification.

Implemented: normalization, SQLite labels, empirical grading, hook output, MCP tools and convergence replay. Future work should evaluate decisions on real operator-labeled workflows and improve shape handling. Cross-shape inference and enterprise compliance certification are not implemented.

## License and contributions

See [LICENSE](./LICENSE). When reporting an issue, include a minimal input, the command, and the observed output.
