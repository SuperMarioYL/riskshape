"""Multi-framework tool-call adapters (m3, v0.2.0).

Each adapter translates one agent framework's tool-call event into the canonical
:class:`riskshape.shape.ActionShape` the Claude Code hook already consumes, so a
single local consent ledger grades decisions across frameworks — the multi-framework
portability moat deferred from v0.1.

OpenHands stays deferred (out of one-version scope).
"""

from __future__ import annotations

from .aider import normalize_aider_event
from .cursor import normalize_cursor_event

__all__ = ["normalize_cursor_event", "normalize_aider_event"]
