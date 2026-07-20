"""Default-allow seed corpus.

Pre-labelled safe shapes so the ledger is non-vacuous on first run: the first
agent ``npm install`` after ``riskshape init`` is already auto-approved because
the seed marks it safe with enough samples to clear ``min_samples``.

These are human-designated safe labels (curated by the RiskShape author at
init time — the operator opts into the corpus by running ``riskshape init``).
Not a learned model; just a warm-start.
"""

from __future__ import annotations

from .ledger import Ledger
from .shape import ActionShape, normalize

# Each entry: (tool_name, tool_input, n_safe_labels, note)
# n_safe_labels seeds enough observations so min_samples is satisfied for the
# common safe shapes — that's what makes the 1st agent `npm install` instant.
_SEED: list[tuple[str, dict, int, str]] = [
    ("Bash", {"command": "git status"}, 5, "seed: safe vcs-readonly"),
    ("Bash", {"command": "git diff"}, 5, "seed: safe vcs-readonly"),
    ("Bash", {"command": "git log"}, 4, "seed: safe vcs-readonly"),
    ("Bash", {"command": "ls"}, 5, "seed: safe shell-readonly"),
    ("Bash", {"command": "pwd"}, 5, "seed: safe shell-readonly"),
    ("Bash", {"command": "npm install"}, 5, "seed: safe build-install"),
    ("Bash", {"command": "pytest"}, 5, "seed: safe shell-readonly"),
    ("Read", {"file_path": "."}, 4, "seed: safe fs-read"),
]


def seed_shapes() -> list[tuple[ActionShape, int, str]]:
    """Materialize the seed corpus into ActionShapes + repeat counts + notes."""
    out: list[tuple[ActionShape, int, str]] = []
    for tool_name, tool_input, n, note in _SEED:
        shape = normalize(tool_name, tool_input)
        out.append((shape, n, note))
    return out


def seed(ledger: Ledger) -> int:
    """Write the seed corpus into the ledger. Returns the number of labels written."""
    written = 0
    for shape, n, note in seed_shapes():
        for _ in range(n):
            ledger.record_label(shape, "safe", note=note)
            written += 1
    return written


def seed_summary() -> list[tuple[str, str, int]]:
    """A human-readable summary of what init seeds (tool, signature, count)."""
    return [(s.tool_name, s.signature, n) for s, n, _ in seed_shapes()]


__all__ = ["seed", "seed_shapes", "seed_summary"]
