"""Replay explicit synthetic labels in an isolated ledger; execute no actions."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from riskshape import Config, Grader, Ledger, normalize
with TemporaryDirectory(prefix="riskshape-demo-") as folder:
    config=Config(db_path=str(Path(folder)/"ledger.db"),tau=0.85,min_samples=3)
    ledger=Ledger(config.db_path); ledger.init_schema()
    grader=Grader(ledger,config)
    shape=normalize("Bash",{"command":"make build"})
    def show(label, shape):
        decision=grader.decide(shape)
        print(json.dumps({"stage":label,"shape":shape.signature,"scope":shape.capability_scope,"safe":decision.grade.safe,"unsafe":decision.grade.unsafe,"decision":decision.outcome.value}))
    show("unseen",shape)
    for _ in range(3): ledger.record_label(shape,"safe",note="synthetic example label")
    show("three safe labels",shape)
    ledger.record_label(shape,"unsafe",note="synthetic example label")
    show("one unsafe label added",shape)
    privileged=normalize("Bash",{"command":"sudo make build"})
    for _ in range(3): ledger.record_label(privileged,"safe",note="synthetic example label")
    show("privileged despite labels",privileged)
print("Scope: empirical label arithmetic; no commands executed or approval hooks installed.")
