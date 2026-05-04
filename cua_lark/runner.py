"""Discover, execute, and report on @cua_test cases."""

from __future__ import annotations

import importlib.util
import json
import logging
import sys
import time
import traceback
from contextlib import ExitStack
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .agent import Agent
from .cdp import CDPError, feishu_session
from .dsl import TestCase, TestContext, TestReport, registered_tests
from .trajectory import Trajectory
from .verifier import VlmVerifier

log = logging.getLogger(__name__)
console = Console()


def discover(path: Path) -> list[TestCase]:
    """Import every Python file under ``path`` so @cua_test decorators run."""
    if path.is_file():
        files = [path]
    else:
        files = sorted(p for p in path.rglob("*.py") if not p.name.startswith("_"))

    for f in files:
        spec = importlib.util.spec_from_file_location(f"_cua_lark_test_{f.stem}", f)
        if spec is None or spec.loader is None:
            log.warning("could not load %s", f)
            continue
        mod = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception:
            log.error("failed importing %s:\n%s", f, traceback.format_exc())
    return registered_tests()


def run_one(case: TestCase, runs_root: Path, use_cdp: bool = True) -> TestReport:
    """Execute one test case end-to-end."""
    started_at = datetime.now().isoformat(timespec="seconds")
    traj = Trajectory.new(instruction=case.name, root=runs_root)
    agent = Agent(trajectory=traj)
    vlm = VlmVerifier(client=agent.client, model=agent.model)

    error = ""
    with ExitStack() as stack:
        cdp_session = None
        if use_cdp:
            try:
                cdp_session = stack.enter_context(feishu_session())
            except CDPError as exc:
                log.warning("CDP unavailable for %r: %s", case.name, exc)

        ctx = TestContext(name=case.name, trajectory=traj, agent=agent, vlm=vlm, cdp=cdp_session)

        t0 = time.monotonic()
        try:
            case.func(ctx)
        except Exception as exc:  # noqa: BLE001 — capture so the report still gets written
            error = f"{type(exc).__name__}: {exc}"
            log.exception("test %r raised", case.name)
        duration = time.monotonic() - t0

    passed = error == "" and ctx.passed
    report = TestReport(
        case=case,
        started_at=started_at,
        duration_s=duration,
        passed=passed,
        assertions=list(ctx.assertions),
        trajectory_dir=traj.run_dir,
        error=error,
    )
    _persist_report(report, ctx)
    return report


def _persist_report(report: TestReport, ctx: TestContext) -> None:
    payload = {
        "case": {"name": report.case.name, "tags": list(report.case.tags)},
        "started_at": report.started_at,
        "duration_s": round(report.duration_s, 3),
        "passed": report.passed,
        "error": report.error,
        "assertions": [asdict(a) for a in report.assertions],
        "steps": ctx.steps,
    }
    out = report.trajectory_dir / "test_report.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def render_summary(reports: list[TestReport]) -> None:
    table = Table(title="CUA-Lark · test summary")
    table.add_column("test", overflow="fold")
    table.add_column("status", justify="center")
    table.add_column("asserts", justify="right")
    table.add_column("duration", justify="right")
    table.add_column("trajectory", overflow="fold")

    for r in reports:
        marker = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        n_pass = sum(a.passed for a in r.assertions)
        n_total = len(r.assertions)
        table.add_row(
            r.case.name,
            marker,
            f"{n_pass}/{n_total}" if n_total else "—",
            f"{r.duration_s:.1f}s",
            str(r.trajectory_dir),
        )
    console.print(table)

    n_pass = sum(r.passed for r in reports)
    style = "green" if n_pass == len(reports) else "yellow"
    console.print(f"[{style}]passed: {n_pass}/{len(reports)}[/{style}]")
