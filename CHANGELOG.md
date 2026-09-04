# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.0] - 2026-09-04

### Fixed

Two fixes closing a version-drift gap and a remote-code-execution bypass that
let a destructive / irreversible shape escape escalation to the human,
breaking the compliance invariant that such shapes ALWAYS escalate, even at
grade 1.0.

- **`web/site.json` had no `content_version` field**: the live Pages site
  carried no version surface at all (the site was last refreshed at v0.2.0)
  while `VERSION`, `__version__`, `pyproject.toml`, `riskshape --version`,
  and the CHANGELOG head all read 0.4.0. A `content_version` key (bare
  `0.5.0`, matching the `VERSION` file format) was added and a
  single-source-of-truth lockstep test (`tests/test_version.py`) now asserts
  all five version surfaces agree — it FAILS on the v0.4.0 tag where
  `content_version` was absent, proving the drift was real.
- **`curl|python3`, `curl|ruby`, `curl|node`, `curl|perl`**: the
  `_PIPE_TO_SHELL` detector now matches non-shell script interpreters
  (`python`/`python3`/`ruby`/`node`/`perl`, with the same optional absolute
  path and `env`/`exec`/`command`/`sudo` prefix handling the shell branch
  already had), not only `bash`/`sh`/`zsh`/`dash`/`ksh`. Piping a remote fetch
  to any interpreter that executes it runs arbitrary remote code, the same
  irreversibility as `curl|bash`, so these forms now classify as
  `network-egress-pipe` (privileged) and escalate regardless of accumulated
  safe labels. Previously they fell through to the non-privileged
  `network-egress` scope and auto-approved after 3 safe labels, breaking the
  invariant that a `curl|<interpreter>` ALWAYS escalates. Regression tests
  in `tests/test_v050.py`.

## [0.4.0] - 2026-08-25

### Fixed

Four fixes closing bypasses that let destructive / irreversible /
unconfigured shapes escape escalation to the human, breaking the compliance
invariant that they ALWAYS escalate, even at grade 1.0.

- **curl|/bin/bash, curl|sudo bash, curl|env bash**: the `_PIPE_TO_SHELL`
  detector now matches an absolute shell path (`curl x | /bin/bash`) and an
  `env`/`exec`/`command`/`sudo` prefix between the pipe and the interpreter
  (`| sudo bash`, `| env bash`, `| /usr/bin/env bash`), not only a shell name
  sitting immediately after `|`. Previously these one-liners fell through to
  the non-privileged `network-egress` scope and auto-approved after 3 safe
  labels, breaking the invariant that a curl|bash ALWAYS escalates.
- **PreToolUse hook hard-deny on an unconfigured/transient ledger**:
  `evaluate` now schema-initializes the default ledger (mirroring
  `mcp_server._ledger`), and `run_pretooluse` wraps `evaluate` in a
  try/except that fails OPEN to `ask` (escalate) with a stderr note.
  Previously an unconfigured or transiently-unreadable ledger raised
  `OperationalError` that propagated uncaught, exited non-zero with no
  hook-protocol JSON, and blocked every tool — contradicting the module's
  "escalation is ask, not deny" invariant.
- **`riskshape record <hyphenated-file>` misclassification**:
  `parse_argv_signature` (the `record` fallback when no `--tool` is given)
  now treats a single token as a Bash command only when it starts with `-`
  (a real flag like `-rf`), not when it merely contains `-`. Previously
  every hyphenated filename (`my-file.txt`, `app-config.json`) misclassified
  as a Bash shape, so that file's grade never converged and a spurious Bash
  shape appeared in the ledger.
- **`riskshape init --force` diluting unsafe labels**: `init --force` now
  calls `Ledger.reset()` before seeding, so it replaces the corpus instead of
  appending seed labels on top of operator labels. Previously `--force` on a
  populated ledger inflated every seed shape's safe count and could flip an
  operator-marked-unsafe shape back to `auto_approve` (5 safe + 1 unsafe →
  10 safe + 1 unsafe, p_safe 0.833 → 0.909 ≥ tau), silently reversing an
  explicit safety decision.

## [0.3.0] - 2026-08-11

### Fixed

Five destructive-command detector bypasses that let destructive shapes fall
through to the non-privileged `shell-exec` scope (and so become auto-eligible
once enough safe labels accumulate), breaking the compliance invariant that
destructive shapes ALWAYS escalate, even at grade 1.0.

- **sudo**: `shell-privileged` — the scope returned for any `sudo`-bearing
  command — is now a member of the default privileged scope set, so a command
  like `sudo rm /etc/passwd` always escalates to the human regardless of how
  many safe labels it has accumulated.
- **rm**: recursive `rm` is now detected order-independently across short
  flags, so separate-flag forms such as `rm -f -r` (force before recursive)
  and `rm -fv -r` classify as `fs-destructive` just like the single-token
  `rm -rf`. Previously only same-token `-rf`/`-fr` and the `--recursive` long
  form were caught.
- **chmod**: recursive `chmod` now also matches the GNU long form
  (`--recursive`) and combined flags (`-Rv`, `-vR`) — not only the exact `-R`
  token — so every recursive `chmod` escalates as `fs-destructive`.
- **dd**: `dd` writing to a block device via `of=/dev/...` (with or without
  `if=`) is now detected as `fs-destructive`, closing the bypass where
  `dd of=/dev/sda` escaped detection because the only matched form was
  `dd if=`.
- **git push**: the `+`-prefixed refspec force-push syntax
  (`git push origin +main`) is now detected as `vcs-destructive`, matching the
  existing `--force` / `-f` / `--force-with-lease` detection. The `+` prefix
  rewrites remote history (a non-fast-forward update), so it is functionally
  equivalent to `--force`.
