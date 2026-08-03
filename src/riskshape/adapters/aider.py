"""Aider adapter — translate an Aider tool-call event into a canonical ActionShape (m3, v0.2.0).

Aider exposes a flatter tool-call shape (often ``{"tool": "bash", "args": {...}}``
or ``{"command_name": "run", "args": "npm install"}``). This adapter maps it onto
the same :class:`riskshape.shape.ActionShape` the normalizer produces, so one
local ledger grades decisions across Aider and Claude Code.
"""

from __future__ import annotations

from typing import Any

from ..shape import ActionShape, normalize

_AIDER_TOOL_ALIASES = {
    "bash": "Bash",
    "run": "Bash",
    "cmd": "Bash",
    "editor": "Edit",
    "edit": "Edit",
    "write": "Write",
    "read": "Read",
    "grep": "Grep",
    "glob": "Glob",
}


def normalize_aider_event(event: dict[str, Any]) -> ActionShape:
    """Normalize an Aider tool-call event into a canonical ActionShape."""
    raw_name = (
        event.get("tool")
        or event.get("command_name")
        or event.get("name")
        or event.get("tool_name")
        or "Unknown"
    )
    name = _AIDER_TOOL_ALIASES.get(str(raw_name).lower(), str(raw_name))
    args = event.get("args") or event.get("arguments") or event.get("input") or {}

    # Aider's bash tool often carries the command as a bare string under args
    # ("npm install") rather than a dict. Coerce to the {"command": ...} shape
    # the normalizer expects for Bash.
    if isinstance(args, str):
        params = {"command": args}
    elif isinstance(args, dict):
        # Aider's run/bash: {"command": "..."}; editor: {"path"/"file_path": "..."}
        params = dict(args)
        if "command" not in params and "file_path" not in params and "path" not in params:
            # bare positional under "args"/"value"
            pos = params.get("args") or params.get("value") or params.get("command_str")
            if isinstance(pos, str):
                params = {"command": pos}
    else:
        params = {"value": str(args)}

    return normalize(name, params)


__all__ = ["normalize_aider_event"]
