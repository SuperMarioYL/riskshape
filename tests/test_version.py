"""Version lockstep test — every shipped version surface must agree.

Asserts the canonical version (the VERSION file) equals:
  - ``riskshape.__version__`` (src/riskshape/__init__.py)
  - ``web/site.json`` ``content_version``
  - the head ``## [x.y.z]`` version in CHANGELOG.md
  - the ``riskshape --version`` CLI output

A drift between any two surfaces is the dominant version-bug class. On the
shipped v0.4.0 tag ``web/site.json`` carried NO ``content_version`` field at
all (the site was last refreshed at v0.2.0), so the site.json assertion here
would have FAILED — proving the drift was real rather than cosmetic. The
v0.5.0 fix adds ``content_version`` and this test keeps it in lockstep.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from click.testing import CliRunner

from riskshape.cli import cli
from riskshape import __version__ as _init_version_attr

_ROOT = Path(__file__).resolve().parent.parent


def _version_file() -> str:
    return (_ROOT / "VERSION").read_text(encoding="utf-8").strip()


def _init_version() -> str:
    return _init_version_attr


def _site_content_version() -> str:
    site = json.loads((_ROOT / "web" / "site.json").read_text(encoding="utf-8"))
    return str(site.get("content_version", ""))


def _changelog_head_version() -> str:
    text = (_ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    m = re.search(r"##\s*\[([0-9.]+)\]", text)
    assert m, "no '## [x.y.z]' version header found in CHANGELOG.md"
    return m.group(1)


def _cli_version() -> str:
    result = CliRunner().invoke(cli, ["--version"])
    assert result.exit_code == 0, f"CLI --version failed: {result.output!r}"
    # click default format: "riskshape, version 0.5.0"
    m = re.search(r"(\d+\.\d+\.\d+)", result.output)
    assert m, f"could not parse version from CLI output: {result.output!r}"
    return m.group(1)


def test_version_lockstep():
    canonical = _version_file()
    surfaces = {
        "VERSION file": canonical,
        "__version__": _init_version(),
        "site.json content_version": _site_content_version(),
        "CHANGELOG head": _changelog_head_version(),
        "CLI --version": _cli_version(),
    }
    drifted = {name: val for name, val in surfaces.items() if val != canonical}
    assert not drifted, (
        f"version drift detected — canonical VERSION={canonical!r}, "
        f"mismatched surfaces: {drifted}"
    )
