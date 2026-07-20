"""Tests for the sqlite ledger."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from riskshape.config import Config
from riskshape.ledger import Ledger, ShapeStats
from riskshape.seed_corpus import seed
from riskshape.shape import ActionShape, normalize


@pytest.fixture
def tmp_ledger(tmp_path, monkeypatch) -> Ledger:
    db = tmp_path / "ledger.db"
    monkeypatch.setenv("RISKSHAPE_DB", str(db))
    ledger = Ledger(str(db))
    ledger.init_schema()
    return ledger


def _bash(cmd: str) -> ActionShape:
    return normalize("Bash", {"command": cmd})


class TestLifecycle:
    def test_init_creates_schema_and_is_idempotent(self, tmp_path):
        db = str(tmp_path / "ledger.db")
        ledger = Ledger(db)
        assert not ledger.is_initialized()
        ledger.init_schema()
        assert ledger.is_initialized()
        # second call is a no-op (idempotent)
        ledger.init_schema()
        assert ledger.is_initialized()

    def test_init_creates_parent_dirs(self, tmp_path):
        db = str(tmp_path / "nested" / "deep" / "ledger.db")
        ledger = Ledger(db)
        ledger.init_schema()
        assert Path(db).exists()

    def test_uninitialized_db_path_reports_false(self, tmp_path):
        ledger = Ledger(str(tmp_path / "nope.db"))
        assert not ledger.is_initialized()


class TestRecordLabel:
    def test_record_safe_and_unsafe(self, tmp_ledger):
        s = _bash("npm install")
        rid = tmp_ledger.record_label(s, "safe", session_id="s1")
        assert rid >= 1
        tmp_ledger.record_label(s, "unsafe", note="broke build")
        stats = tmp_ledger.stats_for(s.key)
        assert stats.safe == 1
        assert stats.unsafe == 1
        assert stats.total == 2
        assert stats.p_safe == 0.5

    def test_record_rejects_invalid_outcome(self, tmp_ledger):
        s = _bash("ls")
        with pytest.raises(ValueError):
            tmp_ledger.record_label(s, "maybe")

    def test_record_persists_across_connections(self, tmp_path):
        db = str(tmp_path / "ledger.db")
        l1 = Ledger(db)
        l1.init_schema()
        s = _bash("pytest")
        l1.record_label(s, "safe")
        # New connection object, same file
        l2 = Ledger(db)
        stats = l2.stats_for(s.key)
        assert stats is not None
        assert stats.safe == 1


class TestCounts:
    def test_count_by_outcome(self, tmp_ledger):
        s = _bash("git status")
        for _ in range(3):
            tmp_ledger.record_label(s, "safe")
        tmp_ledger.record_label(s, "unsafe")
        assert tmp_ledger.count(s.key) == 4
        assert tmp_ledger.count(s.key, "safe") == 3
        assert tmp_ledger.count(s.key, "unsafe") == 1

    def test_count_unseen_shape_is_zero(self, tmp_ledger):
        assert tmp_ledger.count("nonexistent_key", "safe") == 0

    def test_stats_for_unseen_shape_is_none(self, tmp_ledger):
        assert tmp_ledger.stats_for("nonexistent") is None


class TestListing:
    def test_list_shapes_aggregates_correctly(self, tmp_ledger):
        a = _bash("npm install")
        b = _bash("pytest")
        c = _bash("rm -rf x")
        for _ in range(2):
            tmp_ledger.record_label(a, "safe")
        tmp_ledger.record_label(b, "safe")
        tmp_ledger.record_label(c, "unsafe")
        shapes = tmp_ledger.list_shapes()
        assert len(shapes) == 3
        keys = {s.shape_key for s in shapes}
        assert {a.key, b.key, c.key} <= keys
        # Each ShapeStats aggregates its own shape
        a_stats = next(s for s in shapes if s.shape_key == a.key)
        assert a_stats.safe == 2 and a_stats.unsafe == 0
        c_stats = next(s for s in shapes if s.shape_key == c.key)
        assert c_stats.safe == 0 and c_stats.unsafe == 1

    def test_list_labels_returns_rows_newest_first(self, tmp_ledger):
        s = _bash("ls")
        for _ in range(5):
            tmp_ledger.record_label(s, "safe")
        rows = tmp_ledger.list_labels(limit=3)
        assert len(rows) == 3
        assert rows[0].id > rows[-1].id  # newest first

    def test_empty_ledger_lists_are_empty(self, tmp_ledger):
        assert tmp_ledger.list_shapes() == []
        assert tmp_ledger.list_labels() == []


class TestSeed:
    def test_seed_writes_default_allow_corpus(self, tmp_ledger):
        n = seed(tmp_ledger)
        assert n > 0
        shapes = tmp_ledger.list_shapes()
        sigs = {s.signature for s in shapes}
        # The three shapes named in the plan must be present and labelled safe
        assert "npm install" in sigs
        assert "git status" in sigs
        assert "pytest" in sigs
        npm = next(s for s in shapes if s.signature == "npm install")
        assert npm.safe >= 3  # enough to clear min_samples
        assert npm.unsafe == 0

    def test_seed_is_idempotent_safe(self, tmp_ledger):
        seed(tmp_ledger)
        before = len(tmp_ledger.list_labels())
        # Seeding again just appends more safe labels (init --force semantics)
        seed(tmp_ledger)
        after = len(tmp_ledger.list_labels())
        assert after == before * 2


class TestReset:
    def test_reset_clears_labels_keeps_schema(self, tmp_ledger):
        s = _bash("ls")
        tmp_ledger.record_label(s, "safe")
        assert tmp_ledger.count(s.key) == 1
        tmp_ledger.reset()
        assert tmp_ledger.count(s.key) == 0
        # Schema still intact -> can record again
        tmp_ledger.record_label(s, "unsafe")
        assert tmp_ledger.count(s.key, "unsafe") == 1


class TestStats:
    def test_p_safe_properties(self):
        s = ShapeStats("k", "Bash", "x", "shell-exec", safe=7, unsafe=3)
        assert s.total == 10
        assert s.p_safe == 0.7
        assert s.seen is True

    def test_unseen_stats_not_seen(self):
        s = ShapeStats("k", "Bash", "x", "shell-exec", safe=0, unsafe=0)
        assert s.total == 0
        assert s.p_safe == 0.0
        assert s.seen is False
