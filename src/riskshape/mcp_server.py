"""``riskshape mcp serve`` — expose the consent ledger as an MCP server (m3, v0.2.0).

Any MCP-aware agent (not just Claude Code's PreToolUse/PostToolUse hook) can query a
shape's risk grade, ask for an auto-approve/escalate decision, and record a
human-designated outcome label — all backed by the same local sqlite ledger and the
same empirical grader as the hook path. The local-ledger design (no egress, no
daemon) is preserved, so this adds multi-framework reach without giving up the
on-prem property.

The tool handlers (:func:`grade_tool`, :func:`decide_tool`, :func:`record_tool`,
:func:`ledger_tool`) are plain functions so they are unit-testable without the
``mcp`` package installed. :func:`build_server` lazily imports ``mcp`` and wires
those handlers as MCP tools; :func:`serve` runs the stdio server.
"""

from __future__ import annotations

from typing import Any

from .config import Config
from .grader import Grader
from .ledger import Ledger
from .shape import normalize


def _ledger(cfg: Config | None = None) -> Ledger:
    cfg = cfg or Config.load()
    ledger = Ledger(cfg.db_path)
    ledger.init_schema()
    return ledger


def _grader(cfg: Config | None = None) -> Grader:
    cfg = cfg or Config.load()
    return Grader(_ledger(cfg), cfg)


def grade_tool(tool_name: str, tool_input: dict[str, Any], cfg: Config | None = None) -> dict[str, Any]:
    """Return the empirical risk grade for one shape (no side effects)."""
    shape = normalize(tool_name, tool_input)
    g = _grader(cfg).grade(shape)
    return {
        "shape": str(shape),
        "key": shape.key,
        "scope": shape.capability_scope,
        "safe": g.safe,
        "unsafe": g.unsafe,
        "total": g.total,
        "p_safe": round(g.p_safe, 3),
        "seen": g.seen,
    }


def decide_tool(tool_name: str, tool_input: dict[str, Any], cfg: Config | None = None) -> dict[str, Any]:
    """Return the auto_approve/escalate decision for one shape (no side effects)."""
    shape = normalize(tool_name, tool_input)
    d = _grader(cfg).decide(shape)
    return {
        "shape": str(shape),
        "key": shape.key,
        "scope": shape.capability_scope,
        "outcome": d.outcome.value,
        "reason": d.reason,
        "privileged": d.privileged,
        "safe": d.grade.safe,
        "unsafe": d.grade.unsafe,
        "total": d.grade.total,
        "p_safe": round(d.grade.p_safe, 3),
        "seen": d.grade.seen,
    }


def record_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    outcome: str,
    session_id: str | None = None,
    note: str | None = None,
    cfg: Config | None = None,
) -> dict[str, Any]:
    """Record one human-designated outcome label for a shape; returns the row id."""
    if outcome not in ("safe", "unsafe"):
        raise ValueError(f"outcome must be 'safe' or 'unsafe', got {outcome!r}")
    cfg = cfg or Config.load()
    shape = normalize(tool_name, tool_input)
    ledger = _ledger(cfg)
    rowid = ledger.record_label(shape, outcome, session_id=session_id, note=note)
    return {"recorded": rowid, "shape": str(shape), "key": shape.key, "outcome": outcome}


def ledger_tool(cfg: Config | None = None) -> dict[str, Any]:
    """Snapshot the accumulated per-shape grades + decisions."""
    cfg = cfg or Config.load()
    ledger = _ledger(cfg)
    grader = Grader(ledger, cfg)
    shapes = []
    for s in ledger.list_shapes():
        from .shape import ActionShape  # local import avoids a cycle at import time
        d = grader.decide(ActionShape(s.tool_name, s.signature, s.capability))
        shapes.append(
            {
                "tool": s.tool_name,
                "signature": s.signature,
                "key": s.shape_key,
                "scope": s.capability,
                "safe": s.safe,
                "unsafe": s.unsafe,
                "total": s.total,
                "p_safe": round(s.p_safe, 3),
                "decision": d.outcome.value,
            }
        )
    shapes.sort(key=lambda r: r["safe"] + r["unsafe"], reverse=True)
    return {"db": cfg.db_path, "tau": cfg.tau, "min_samples": cfg.min_samples, "shapes": shapes}


# --- MCP wiring (lazy: only needs `mcp` installed when actually serving) ---


def build_server():
    """Build the FastMCP server. Lazily imports ``mcp`` (an optional dep at runtime)."""
    from mcp.server.fastmcp import FastMCP  # type: ignore

    mcp = FastMCP("riskshape")

    @mcp.tool()
    def grade(tool_name: str, tool_input: dict) -> dict:
        """Empirical risk grade for a shape (P(safe), safe/unsafe counts, scope)."""
        return grade_tool(tool_name, tool_input)

    @mcp.tool()
    def decide(tool_name: str, tool_input: dict) -> dict:
        """auto_approve/escalate decision for a shape (privileged shapes always escalate)."""
        return decide_tool(tool_name, tool_input)

    @mcp.tool()
    def record(tool_name: str, tool_input: dict, outcome: str, session_id: str = "", note: str = "") -> dict:
        """Record a human-designated outcome label ('safe' or 'unsafe') for a shape."""
        return record_tool(
            tool_name,
            tool_input,
            outcome,
            session_id=session_id or None,
            note=note or None,
        )

    @mcp.tool()
    def ledger() -> dict:
        """Snapshot of accumulated per-shape grades + decisions."""
        return ledger_tool()

    return mcp


def serve() -> int:
    """Run the MCP stdio server. Returns 0 on clean shutdown."""
    build_server().run()
    return 0


__all__ = [
    "grade_tool",
    "decide_tool",
    "record_tool",
    "ledger_tool",
    "build_server",
    "serve",
]
