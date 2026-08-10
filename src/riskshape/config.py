"""Configuration for RiskShape.

All knobs have environment-variable overrides so the same binary works for the
local dev ledger, the demo (temp db), and a CI run.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Privileged capability scopes are NEVER auto-promoted, even at grade 1.0.
# This is the compliance-mode guarantee: destructive/irreversible shapes and
# egress-to-shell pipes always escalate to the human. ``shell-privileged`` is
# included so any sudo-bearing shape (e.g. ``sudo rm /etc/passwd``) escalates
# regardless of how many safe labels it has accumulated — the normalizer
# returns this scope for every command matching \bsudo\b.
DEFAULT_PRIVILEGED_SCOPES: frozenset[str] = frozenset(
    {
        "fs-destructive",
        "vcs-destructive",
        "network-egress-pipe",
        "shell-privileged",
    }
)


def _default_db_path() -> str:
    """~/.riskshape/ledger.db, overridable via RISKSHAPE_DB."""
    override = os.environ.get("RISKSHAPE_DB")
    if override:
        return override
    home = os.path.expanduser("~")
    return str(Path(home) / ".riskshape" / "ledger.db")


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Config:
    """Runtime configuration (pure data, no I/O).

    Construct via :meth:`load` so environment overrides are applied; the plain
    defaults below are the fallbacks when an env var is absent.
    """

    db_path: str = ""
    # Risk grade threshold above which a non-privileged, well-evidenced shape
    # is auto-approved. tau=0.85 means ">=85% of observed outcomes were safe".
    tau: float = 0.85
    # Minimum labelled observations before the grade can authorize auto-approve.
    # Shapes with fewer samples escalate regardless of p_safe — protects against
    # one-shot luck masquerading as a safe shape.
    min_samples: int = 3
    privileged_scopes: frozenset[str] = field(
        default_factory=lambda: DEFAULT_PRIVILEGED_SCOPES
    )

    @classmethod
    def load(cls) -> "Config":
        """Build a Config with environment overrides applied."""
        return cls(
            db_path=_default_db_path(),
            tau=_env_float("RISKSHAPE_TAU", 0.85),
            min_samples=_env_int("RISKSHAPE_MIN_SAMPLES", 3),
            privileged_scopes=DEFAULT_PRIVILEGED_SCOPES,
        )

    def is_privileged(self, capability_scope: str) -> bool:
        return capability_scope in self.privileged_scopes
