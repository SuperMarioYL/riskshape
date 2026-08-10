# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
