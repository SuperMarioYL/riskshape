"""RiskShape — a risk-graded consent ledger for autonomous coding agents.

RiskShape learns which agent action-shapes are safe to auto-approve from your
past outcome labels, collapsing review from O(every-action) to O(anomaly).
"""

from .shape import ActionShape, normalize
from .ledger import Ledger
from .grader import Grader, Decision, Outcome, RiskGrade
from .config import Config

__version__ = "0.1.0"
__all__ = [
    "ActionShape",
    "normalize",
    "Ledger",
    "Grader",
    "Decision",
    "Outcome",
    "RiskGrade",
    "Config",
]
