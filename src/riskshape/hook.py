"""Claude Code hook wiring (m2).

Two hook entry points:
  - PreToolUse  -> ``riskshape check``  : normalize -> grade -> decide.
  - PostToolUse -> ``riskshape label``  : observe + prompt the human to label.

PreToolUse emits the Claude Code hook protocol JSON to stdout:
  {"hookSpecificOutput": {
       "hookEventName": "PreToolUse",
       "permissionDecision": "allow" | "ask",
       "permissionDecisionReason": "..."
  }}

"allow" bypasses the permission prompt (auto-approve). "ask" forces the human
prompt (escalate). A concise human-readable line is also written to stderr —
Claude Code surfaces hook stderr to the operator, which is the feedback loop
that makes the ledger learn.

This module contains no I/O of its own beyond reading stdin / writing the two
streams; the hook subcommands in cli.py call into ``run_pretooluse`` /
``run_posttooluse`` so they are unit-testable without spawning a subprocess.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, TextIO

from .config import Config
from .grader import Decision, Grader, Outcome
from .ledger import Ledger
from .shape import ActionShape, normalize_from_hook_payload


# Permission decision values understood by Claude Code PreToolUse hooks.
PERM_ALLOW = "allow"
PERM_ASK = "ask"


@dataclass(frozen=True)
class HookResult:
    """Result of evaluating a hook payload."""

    decision: Decision
    shape: ActionShape
    payload_outcome: str  # "auto_approve" | "escalate"
    json_payload: str  # the stdout hook-protocol JSON
    stderr_line: str  # the human-readable stderr summary

    @property
    def permission_decision(self) -> str:
        return PERM_ALLOW if self.payload_outcome == "auto_approve" else PERM_ASK


def _build_stdout(shape: ActionShape, decision: Decision) -> str:
    perm = PERM_ALLOW if decision.is_auto_approve else PERM_ASK
    payload = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": perm,
            "permissionDecisionReason": (
                f"RiskShape: {decision.reason} "
                f"[shape={shape.tool_name}:{shape.signature} scope={shape.capability_scope}]"
            ),
        }
    }
    return json.dumps(payload, separators=(",", ":"))


def _build_stderr(shape: ActionShape, decision: Decision) -> str:
    tag = "AUTO-APPROVE" if decision.is_auto_approve else "ESCALATE"
    grade = decision.grade
    if not grade.seen:
        evidence = "unseen"
    else:
        evidence = f"P(safe)={grade.p_safe:.3f} {grade.safe}/{grade.total}"
    sig = shape.signature or "(empty)"
    if len(sig) > 60:
        sig = sig[:57] + "..."
    return (
        f"[riskshape] {tag}  {shape.tool_name}: {sig}  "
        f"({evidence}, scope={shape.capability_scope})"
    )


def evaluate(payload: dict[str, Any], grader: Grader | None = None) -> HookResult:
    """Evaluate a PreToolUse payload and return a HookResult (no stream I/O).

    When no ``grader`` is supplied (the live hook path) the default ledger is
    schema-initialized here — mirroring ``mcp_server._ledger`` — so a
    cold/unconfigured ledger (no db file, no labels table) does not crash the
    hook with OperationalError. Transient errors init_schema cannot fix
    (corrupt db, permission denied) are caught in ``run_pretooluse``.
    """
    shape = normalize_from_hook_payload(payload)
    if grader is None:
        ledger = Ledger(Config.load().db_path)
        ledger.init_schema()
        grader = Grader(ledger)
    decision = grader.decide(shape)
    payload_outcome = (
        "auto_approve" if decision.is_auto_approve else "escalate"
    )
    return HookResult(
        decision=decision,
        shape=shape,
        payload_outcome=payload_outcome,
        json_payload=_build_stdout(shape, decision),
        stderr_line=_build_stderr(shape, decision),
    )


def run_pretooluse(
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """PreToolUse hook entry. Reads one JSON object from stdin.

    Returns the process exit code. Exit 0 in all hook-decision cases (the
    decision is conveyed via the stdout JSON); a non-zero exit would block
    the tool which we never do unilaterally — escalation is ``ask``, not deny.
    """
    raw = stdin.read()
    if not raw.strip():
        # No payload (e.g. dry-run with no stdin) — fail-open to the normal
        # Claude Code permission flow by emitting nothing.
        stderr.write("[riskshape] no PreToolUse payload on stdin — skipping\n")
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        stderr.write(f"[riskshape] invalid hook JSON: {exc}\n")
        return 0
    if not isinstance(payload, dict):
        stderr.write("[riskshape] hook payload is not a JSON object — skipping\n")
        return 0

    try:
        result = evaluate(payload)
    except Exception as exc:
        # A ledger problem init_schema could not fix (corrupt db, permission
        # denied, disk full) must NEVER hard-deny — escalation is ``ask``, not
        # deny. Fail OPEN to PERM_ASK with a stderr note so the operator still
        # sees the tool fire instead of every tool being blocked.
        stderr.write(f"[riskshape] ledger unavailable, escalating: {exc}\n")
        stdout.write(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": PERM_ASK,
                        "permissionDecisionReason": (
                            f"RiskShape: ledger error ({type(exc).__name__}), "
                            "escalating to human"
                        ),
                    }
                },
                separators=(",", ":"),
            )
            + "\n"
        )
        stdout.flush()
        return 0
    stdout.write(result.json_payload + "\n")
    stdout.flush()
    stderr.write(result.stderr_line + "\n")
    stderr.flush()
    return 0


def run_posttooluse(
    stdin: TextIO = sys.stdin,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    """PostToolUse hook entry.

    PostToolUse cannot interactively prompt (no TTY in the hook context), so
    we surface a one-line label suggestion to stderr and tell the operator the
    exact ``riskshape record`` command to run. The operator's ``record``
    writes the human-designated label — never machine-inferred.
    """
    raw = stdin.read()
    if not raw.strip():
        return 0
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return 0
    if not isinstance(payload, dict):
        return 0

    shape = normalize_from_hook_payload(payload)
    sig = shape.signature or "(empty)"
    # Quote the signature so the suggested command round-trips through shlex.
    quoted = sig.replace("'", "'\"'\"'")
    suggestion = (
        f"[riskshape] label this action -> "
        f"riskshape record --tool {shape.tool_name} '{quoted}' safe|unsafe"
    )
    stderr.write(suggestion + "\n")
    stderr.flush()
    return 0


def emit_snippet(binary: str = "riskshape") -> str:
    """The 2-line ~/.claude/settings.json snippet printed by `riskshape init`."""
    return (
        '{\n'
        f'  "hooks": {{\n'
        f'    "PreToolUse":  [{{"matcher": ".*", "hooks": [{{"type": "command", "command": "{binary} check"}}]}}],\n'
        f'    "PostToolUse": [{{"matcher": ".*", "hooks": [{{"type": "command", "command": "{binary} label"}}]}}]\n'
        f'  }}\n'
        '}'
    )


__all__ = [
    "HookResult",
    "evaluate",
    "run_pretooluse",
    "run_posttooluse",
    "emit_snippet",
    "PERM_ALLOW",
    "PERM_ASK",
]
