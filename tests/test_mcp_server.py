"""Tests for the v0.2 MCP server tool handlers + multi-framework adapters."""

from __future__ import annotations

import pytest

from riskshape.adapters import normalize_aider_event, normalize_cursor_event
from riskshape.config import Config
from riskshape.mcp_server import decide_tool, grade_tool, ledger_tool, record_tool
from riskshape.shape import normalize


@pytest.fixture
def cfg(tmp_path):
    return Config(db_path=str(tmp_path / "mcp.db"))


class TestMcpHandlers:
    def test_grade_unseen_shape(self, cfg):
        g = grade_tool("Bash", {"command": "npm install"}, cfg=cfg)
        assert g["seen"] is False
        assert g["safe"] == 0 and g["unsafe"] == 0
        assert g["scope"] == "build-install"

    def test_record_then_grade(self, cfg):
        for _ in range(3):
            record_tool("Bash", {"command": "npm install"}, "safe", cfg=cfg)
        g = grade_tool("Bash", {"command": "npm install"}, cfg=cfg)
        assert g["seen"] is True
        assert g["safe"] == 3
        assert g["p_safe"] == 1.0

    def test_decide_privileged_always_escalates(self, cfg):
        record_tool("Bash", {"command": "rm -rf /x"}, "safe", cfg=cfg)
        d = decide_tool("Bash", {"command": "rm -rf /x"}, cfg=cfg)
        assert d["outcome"] == "escalate"
        assert d["privileged"] is True

    def test_decide_converged_safe_shape_auto_approves(self, cfg):
        for _ in range(4):
            record_tool("Bash", {"command": "npm install"}, "safe", cfg=cfg)
        d = decide_tool("Bash", {"command": "npm install"}, cfg=cfg)
        assert d["outcome"] == "auto_approve"

    def test_record_rejects_bad_outcome(self, cfg):
        with pytest.raises(ValueError):
            record_tool("Bash", {"command": "ls"}, "maybe", cfg=cfg)

    def test_ledger_snapshot(self, cfg):
        record_tool("Bash", {"command": "ls"}, "safe", cfg=cfg)
        snap = ledger_tool(cfg=cfg)
        assert snap["tau"] == cfg.tau
        assert any(s["tool"] == "Bash" for s in snap["shapes"])

    def test_build_server_is_constructible(self):
        # build_server lazily imports mcp; only exercise when the dep is installed
        # (it is in the v0.2 dev/test env since mcp is now a core dep).
        mcp = pytest.importorskip("mcp")
        from riskshape.mcp_server import build_server

        server = build_server()
        assert server is not None


class TestAdapters:
    def test_cursor_run_command_normalizes_to_bash(self):
        s = normalize_cursor_event({"tool_name": "RunCommand", "params": {"command": "npm install"}})
        assert s.tool_name == "Bash"
        assert s.signature == "npm install"
        assert s.capability_scope == "build-install"

    def test_cursor_edit_file_uses_filepath(self):
        s = normalize_cursor_event({"tool": "EditFile", "params": {"filePath": "/repo/app.py"}})
        assert s.tool_name == "Edit"
        assert s.capability_scope == "fs-write"
        assert s.signature == "/repo/app.py"

    def test_aider_bash_string_args(self):
        s = normalize_aider_event({"tool": "bash", "args": "git status"})
        assert s.tool_name == "Bash"
        assert s.signature == "git status"
        assert s.capability_scope == "shell-readonly"

    def test_aider_run_command_dict_args(self):
        s = normalize_aider_event({"command_name": "run", "args": {"command": "npm install"}})
        assert s.tool_name == "Bash"
        assert s.signature == "npm install"

    def test_adapter_matches_hook_normalizer(self):
        a = normalize_cursor_event({"tool_name": "Bash", "params": {"command": "npm install"}})
        b = normalize("Bash", {"command": "npm install"})
        assert a.key == b.key
