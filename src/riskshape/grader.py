"""Empirical per-shape risk grader.

P(safe|shape) = safe(shape) / (safe(shape) + unsafe(shape))

Decision:
    auto_approve  if grade >= tau AND total >= min_samples AND not privileged
    escalate      if shape unseen OR grade < tau OR total < min_samples OR privileged

The privileged-set check is the compliance-mode invariant: destructive /
irreversible shapes (rm -rf, git push --force, curl|bash) escalate to the
human ALWAYS, even at grade 1.0. That is the guarantee the enterprise-GRC
outer circle pays for, and the reason v0.1 scope forbids auto-promoting them.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .config import Config
from .ledger import Ledger, ShapeStats
from .shape import ActionShape


class Outcome(str, Enum):
    AUTO_APPROVE = "auto_approve"
    ESCALATE = "escalate"


@dataclass(frozen=True)
class RiskGrade:
    """The empirical grade for one shape."""

    shape: ActionShape
    safe: int
    unsafe: int
    seen: bool
    p_safe: float

    @property
    def total(self) -> int:
        return self.safe + self.unsafe


@dataclass(frozen=True)
class Decision:
    outcome: Outcome
    grade: RiskGrade
    privileged: bool
    reason: str

    @property
    def is_auto_approve(self) -> bool:
        return self.outcome is Outcome.AUTO_APPROVE


class Grader:
    """Empirical per-shape grader wired to a ledger + config."""

    def __init__(self, ledger: Ledger, config: Config | None = None) -> None:
        self.ledger = ledger
        self.config = config or Config.load()

    # -- grade -------------------------------------------------------------

    def grade(self, shape: ActionShape) -> RiskGrade:
        stats = self.ledger.stats_for(shape.key)
        if stats is None or not stats.seen:
            return RiskGrade(
                shape=shape, safe=0, unsafe=0, seen=False, p_safe=0.0
            )
        return RiskGrade(
            shape=shape,
            safe=stats.safe,
            unsafe=stats.unsafe,
            seen=True,
            p_safe=stats.p_safe,
        )

    # -- decide ------------------------------------------------------------

    def decide(self, shape: ActionShape) -> Decision:
        grade = self.grade(shape)
        privileged = self.config.is_privileged(shape.capability_scope)

        if privileged:
            return Decision(
                outcome=Outcome.ESCALATE,
                grade=grade,
                privileged=True,
                reason=(
                    f"privileged scope '{shape.capability_scope}' — "
                    "compliance mode never auto-promotes"
                ),
            )

        if not grade.seen:
            return Decision(
                outcome=Outcome.ESCALATE,
                grade=grade,
                privileged=False,
                reason="shape unseen — no outcome labels yet",
            )

        if grade.total < self.config.min_samples:
            return Decision(
                outcome=Outcome.ESCALATE,
                grade=grade,
                privileged=False,
                reason=(
                    f"insufficient evidence: {grade.total} label(s) "
                    f"< min_samples={self.config.min_samples}"
                ),
            )

        if grade.p_safe >= self.config.tau:
            return Decision(
                outcome=Outcome.AUTO_APPROVE,
                grade=grade,
                privileged=False,
                reason=(
                    f"P(safe)={grade.p_safe:.3f} >= tau={self.config.tau} "
                    f"({grade.safe}/{grade.total} safe)"
                ),
            )

        return Decision(
            outcome=Outcome.ESCALATE,
            grade=grade,
            privileged=False,
            reason=(
                f"P(safe)={grade.p_safe:.3f} < tau={self.config.tau} "
                f"({grade.safe}/{grade.total} safe)"
            ),
        )


__all__ = ["Grader", "RiskGrade", "Decision", "Outcome"]
