"""Cursor adapter — translate a Cursor tool-call event into a canonical ActionShape (m3, v0.2.0).

Cursor's tool-call surface differs from Claude Code's hook payload (different
field names, different tool-name casing). This adapter normalizes a Cursor event
into the same :class:`riskshape.shape.ActionShape` the Claude Code hook already
produces, so one local ledger grades decisions across both frameworks.
"""

from __future__ import annotations

from typing import Any

from ..shape import ActionShape, normalize

# Map Cursor tool names to the canonical RiskShape tool names the normalizer
# already understands. Unknown names fall through to the normalizer's generic
# path (stable JSON signature + "unknown" scope) so a future Cursor tool still
# gets a stable key without an adapter update.
_CURSOR_TOOL_ALIASES = {
    "RunCommand": "Bash",
    "run_command": "Bash",
    "EditFile": "Edit",
    "edit_file": "Edit",
    "WriteFile": "Write",
    "write_file": "Write",
    "ReadFile": "Read",
    "read_file": "Read",
    "CodebaseSearch": "Grep",
    "codebase_search": "Grep",
    "FileSearch": "Glob",
    "file_search": "Glob",
}


def _extract_params(event: dict[str, Any]) -> dict[str, Any]:
    """Pull the tool params out of a Cursor event across its common shapes."""
    params = (
        event.get("params")
        or event.get("input")
        or event.get("arguments")
        or event.get("tool_input")
        or {}
    )
    if not isinstance(params, dict):
        return {"value": params}
    # Cursor uses camelCase keys (filePath, notebookPath) where the normalizer reads
    # snake_case (file_path, notebook_path). Map the known aliases through so an
    # fs-tool event gets a real signature instead of an empty one.
    aliases = {
        "filePath": "file_path",
        "fileName": "file_path",
        "notebookPath": "notebook_path",
        "cmd": "command",
    }
    return {aliases.get(k, k): v for k, v in params.items()}


def normalize_cursor_event(event: dict[str, Any]) -> ActionShape:
    """Normalize a Cursor tool-call event into a canonical ActionShape."""
    raw_name = (
        event.get("tool_name")
        or event.get("tool")
        or event.get("method")
        or event.get("name")
        or "Unknown"
    )
    name = _CURSOR_TOOL_ALIASES.get(str(raw_name), str(raw_name))
    params = _extract_params(event)
    # Cursor's RunCommand carries the command under "command"; EditFile under
    # "filePath"/"path". The normalizer already reads tool_input.command /
    # tool_input.file_path, so pass params straight through.
    return normalize(name, params)


__all__ = ["normalize_cursor_event"]
