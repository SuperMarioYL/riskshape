"""Shape normalizer — the core primitive.

Turns a raw agent tool-call (tool_name + tool_input) into a stable canonical
``ActionShape`` key. The capability_scope is DERIVED here from tool_name +
tool_input, NOT read from PreToolUse stdin — there is no ``args`` or
``capability`` key in the Claude Code hook payload.

Exact-shape match only (v0.1 scope): the 50th ``npm install`` matches the 1st
because the normalized signature is byte-identical. Cross-shape generalization
(similar-shape inference) is explicitly out of scope.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from typing import Any

# Tool names Claude Code emits. We accept case-insensitive variants so a
# future framework with a different casing still normalizes to the same shape.
_BASH_TOOLS = frozenset({"bash", "Bash", "execute_bash", "shell"})
_EDIT_TOOLS = frozenset({"edit", "Edit", "str_replace_editor"})
_WRITE_TOOLS = frozenset({"write", "Write", "create_file", "file_editor"})
_READ_TOOLS = frozenset({"read", "Read", "view_file", "cat"})
_NOTE_TOOLS = frozenset({"notebookedit", "NotebookEdit", "notebook_edit"})
_GLOB_TOOLS = frozenset({"glob", "Glob", "list_files"})
_GREP_TOOLS = frozenset({"grep", "Grep", "ripgrep"})


@dataclass(frozen=True)
class ActionShape:
    """A canonical, comparable agent action-shape.

    ``key`` is the stable hash used as the ledger's join key. ``signature`` is
    the human-readable command/path the operator sees in ``riskshape ledger``.
    ``capability_scope`` is the derived capability class (drives the
    privileged-set check).
    """

    tool_name: str
    signature: str
    capability_scope: str

    @property
    def key(self) -> str:
        h = hashlib.sha256(f"{self.tool_name}|{self.signature}".encode("utf-8"))
        return h.hexdigest()[:16]

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.tool_name}:{self.signature}"


# --- bash command normalization + capability derivation ---------------------

# Recursive delete via short flags: matches any `rm` invocation whose flag
# tokens include a recursive flag (-r/-R, alone or combined like -rf/-fr/-rv/-Rv)
# in ANY position and ANY order — including SEPARATE tokens (`rm -f -r`). The
# `(?:\s+\S+)*` scan makes detection order-independent so force-before-recursive
# (`rm -f -r`) is caught just like recursive-before-force (`rm -r -f`), closing
# the separate-flag bypass the single-token regexes below used to miss.
_RM_RECURSIVE_SHORT = re.compile(
    r"\brm\b(?:\s+\S+)*\s+-[a-zA-Z]*[rR][a-zA-Z]*\b"
)
# GNU long-form recursive delete (`rm --recursive`, with or without --force) is
# just as destructive as `-rf` but the short-flag regex above misses the long
# form — without this the compliance invariant (destructive shapes ALWAYS
# escalate) can be bypassed.
_RM_RECURSIVE_LONG = re.compile(r"\brm\s+(?:\S+\s+)*--recursive\b")
_GIT_PUSH_FORCE = re.compile(
    r"\bgit\s+push\s+(?:.+\s)?(?:--force|-f\b|--force-with-lease|\+\w)"
)
# Pipe to a shell interpreter — the curl|bash one-liner. The shell name need
# not sit immediately after `|`: real one-liners put an absolute path
# (`curl x | /bin/bash`), an env/exec/command/sudo prefix (`| sudo bash`,
# `| env bash`, `| /usr/bin/env bash`), or both between the pipe and the
# interpreter. All of those forms must escalate as network-egress-pipe
# (privileged) — a curl|bash ALWAYS escalates, even at grade 1.0.
_PIPE_TO_SHELL = re.compile(
    r"\|\s*(?:/[\w/.-]*)?\s*(?:(?:env|exec|command|sudo)\s+)*(?:bash|sh|zsh|dash|ksh)\b"
)
_CURL_WGET = re.compile(r"\b(?:curl|wget)\b")
# dd writing to a block device via of= (with OR without if=) is destructive, as
# is dd reading from a device (if=), mkfs on any device, and a shell redirect
# onto /dev/sd*. The `of=/dev/` branch closes the bypass where `dd of=/dev/sda`
# (no if=, no shell redirect) escaped detection and fell through to shell-exec.
_DD_MKFS = re.compile(
    r"\b(?:dd\s+if=|dd\s+.*?of=/dev/|mkfs(?:\.\w+)?\b|>\s*/dev/sd)"
)
# Recursive chmod is destructive: catch -R (alone or combined like -Rv/-vR) AND
# --recursive, scanning all flag-token positions so order/separate-token forms
# (`chmod -v -R .`) are caught just like `chmod -Rv .` — mirrors the rm fix.
_CHMOD_RECURSIVE = re.compile(
    r"\bchmod\b(?:\s+\S+)*\s+(?:-[a-zA-Z]*R[a-zA-Z]*|--recursive)\b"
)
_SUDO = re.compile(r"\bsudo\b")

_READONLY_CMDS = re.compile(
    r"^\s*(?:git\s+(?:status|diff|log|show|branch|remote|ls-files)|"
    r"ls|pwd|cat|head|tail|echo|env|printenv|which|type|file|stat|wc|"
    r"pytest|npm\s+(?:test|run\s+\w+)|pnpm\s+\w+|yarn\s+\w+|"
    r"python\s+-m\s+pytest|cargo\s+test|go\s+test)\b"
)
_SAFE_BUILD_CMDS = re.compile(
    r"^\s*(?:npm\s+install(?:\s+.*)?|pnpm\s+install|yarn\s+install|"
    r"pip\s+install(?:\s+.*)?|uv\s+(?:pip\s+)?install|cargo\s+build|"
    r"go\s+build|make)\b"
)


def _normalize_bash_command(command: str) -> str:
    """Canonicalize whitespace so ``npm  install`` == ``npm install``.

    We deliberately do NOT normalize argument order or strip flags —
    exact-shape match means the operator's repeated command must match itself.
    Only whitespace variance (the most common copy-paste drift) is collapsed.
    """
    if command is None:
        return ""
    # Collapse runs of whitespace to a single space, strip ends.
    collapsed = re.sub(r"\s+", " ", command.strip())
    return collapsed


def _derive_bash_capability(command: str) -> str:
    """Derive the capability scope from a Bash command string.

    Privileged scopes (see config.DEFAULT_PRIVILEGED_SCOPES) are the ones the
    compliance mode never auto-promotes:
      - fs-destructive: rm -rf, dd, mkfs, chmod -R on system paths
      - vcs-destructive: git push --force / +refspec
      - network-egress-pipe: curl/wget piped to a shell
      - shell-privileged: any sudo-bearing command

    Non-privileged scopes (escalate-when-novel, auto-approve-when-safe):
      - shell-readonly / build-install / shell-exec / network-egress / fs-read
    """
    if not command:
        return "shell-exec"
    if _RM_RECURSIVE_SHORT.search(command) or _RM_RECURSIVE_LONG.search(command):
        return "fs-destructive"
    if _GIT_PUSH_FORCE.search(command):
        return "vcs-destructive"
    if _PIPE_TO_SHELL.search(command) and _CURL_WGET.search(command):
        return "network-egress-pipe"
    if _DD_MKFS.search(command):
        return "fs-destructive"
    if _CHMOD_RECURSIVE.search(command):
        return "fs-destructive"
    if _PIPE_TO_SHELL.search(command):
        # Pipe to shell without a known egress fetcher — still treat as
        # privileged: shelling out piped input is the irreversible pattern.
        return "network-egress-pipe"
    if _CURL_WGET.search(command):
        return "network-egress"
    if _SUDO.search(command):
        return "shell-privileged"
    # Compound commands (control operators) can't be promised readonly — a
    # `echo x && rm` is not a readonly shape even though it starts with echo.
    if any(op in command for op in ("&&", "||", ";", "|")):
        return "shell-exec"
    if _READONLY_CMDS.match(command):
        return "shell-readonly"
    if _SAFE_BUILD_CMDS.match(command):
        return "build-install"
    return "shell-exec"


def _signature_for_fs_tool(tool_input: dict, key: str = "file_path") -> str:
    val = tool_input.get(key) or tool_input.get("path") or tool_input.get("notebook_path")
    if not val:
        return ""
    # Normalize the path so the same file normalizes across calls (the convergence
    # guarantee): collapse "./", redundant ".." segments and repeated slashes via
    # os.path.normpath, then strip a trailing separator. Keeping the path otherwise
    # as-given avoids a false collapse between distinct same-named files in
    # different directories when cwd is unknown.
    return os.path.normpath(str(val)).rstrip("/")


def _signature_for_search_tool(tool_input: dict) -> str:
    pattern = tool_input.get("pattern") or tool_input.get("query") or tool_input.get("path")
    return str(pattern or "")


def _fallback_signature(tool_input: dict) -> str:
    """Stable signature for an unknown tool: sorted JSON of its input."""
    try:
        return json.dumps(tool_input, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(tool_input)


def normalize(tool_name: str, tool_input: dict[str, Any] | None) -> ActionShape:
    """Normalize a raw tool-call into a canonical ``ActionShape``.

    ``tool_input`` is the dict of the tool's real params as emitted by the
    agent framework (e.g. ``tool_input.command`` for Bash,
    ``tool_input.file_path`` / ``tool_input.content`` for Edit/Write). There
    is NO ``args`` or ``capability`` key in stdin — capability_scope is
    derived here.
    """
    tool_input = tool_input or {}
    name = (tool_name or "").strip()
    low = name.lower()

    if low in {t.lower() for t in _BASH_TOOLS}:
        command = str(tool_input.get("command") or tool_input.get("cmd") or "")
        sig = _normalize_bash_command(command)
        cap = _derive_bash_capability(sig)
        return ActionShape(tool_name="Bash", signature=sig, capability_scope=cap)

    if low in {t.lower() for t in _EDIT_TOOLS}:
        sig = _signature_for_fs_tool(tool_input)
        return ActionShape(tool_name="Edit", signature=sig, capability_scope="fs-write")
    if low in {t.lower() for t in _WRITE_TOOLS}:
        sig = _signature_for_fs_tool(tool_input)
        return ActionShape(tool_name="Write", signature=sig, capability_scope="fs-write")
    if low in {t.lower() for t in _READ_TOOLS}:
        sig = _signature_for_fs_tool(tool_input)
        return ActionShape(tool_name="Read", signature=sig, capability_scope="fs-read")
    if low in {t.lower() for t in _NOTE_TOOLS}:
        sig = _signature_for_fs_tool(tool_input, key="notebook_path")
        return ActionShape(
            tool_name="NotebookEdit", signature=sig, capability_scope="fs-write"
        )
    if low in {t.lower() for t in _GLOB_TOOLS}:
        sig = _signature_for_search_tool(tool_input)
        return ActionShape(tool_name="Glob", signature=sig, capability_scope="fs-read")
    if low in {t.lower() for t in _GREP_TOOLS}:
        sig = _signature_for_search_tool(tool_input)
        return ActionShape(tool_name="Grep", signature=sig, capability_scope="fs-read")

    # Unknown / future tool: keep the original name, derive a stable signature.
    sig = _fallback_signature(tool_input)
    return ActionShape(tool_name=name or "Unknown", signature=sig, capability_scope="unknown")


def normalize_from_hook_payload(payload: dict[str, Any]) -> ActionShape:
    """Convenience: normalize straight from a Claude Code hook stdin payload."""
    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {"value": tool_input}
    return normalize(tool_name, tool_input)


def parse_argv_signature(argv: list[str]) -> tuple[str, dict]:
    """Reconstruct a tool_input dict from CLI argv for ``riskshape record``.

    For Bash shapes the operator passes the command as a single quoted arg:
    ``riskshape record --tool Bash "npm install" safe``. For Edit/Write the
    operator passes the file path. This helper turns the positional args into
    the minimal tool_input the normalizer needs to reproduce the same key.
    """
    if not argv:
        return "Bash", {"command": ""}
    joined = " ".join(argv)
    # Heuristic: if it looks like a shell command (has spaces or shell tokens,
    # or starts with a flag like -rf/--force) treat as Bash command; else treat
    # as a file path for fs tools. Note: a hyphenated FILENAME (my-file.txt)
    # does not start with "-", so it reads as a Read shape — using "-" in joined
    # (substring) here misclassified every hyphenated filename as a Bash shape.
    if (
        any(tok in joined for tok in (" ", "|", "&&", ";", "$"))
        or joined.startswith("-")
        or len(argv) > 1
    ):
        return "Bash", {"command": joined}
    return "Read", {"file_path": joined}


__all__ = [
    "ActionShape",
    "normalize",
    "normalize_from_hook_payload",
    "parse_argv_signature",
]
