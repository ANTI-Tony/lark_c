"""``cua-lark`` command-line entry point.

    cua-lark run "打开飞书,点击第一个聊天"
    cua-lark run "open the first chat in Feishu" --max-steps 10 --model claude-sonnet-4-6
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:  # dotenv is optional at runtime
    pass

from rich.console import Console
from rich.panel import Panel

from .agent import Agent
from .trajectory import Trajectory

console = Console()


def cmd_report(args: argparse.Namespace) -> int:
    from .report import render_index, render_run

    target: Path = args.path
    if target.is_file() or (target / "trajectory.json").exists():
        out = render_run(target if target.is_dir() else target.parent)
        console.print(f"[green]wrote[/green] {out}")
        return 0

    if not target.is_dir():
        console.print(f"[red]not a directory:[/red] {target}")
        return 2

    rendered = []
    for run_dir in sorted(p for p in target.iterdir() if p.is_dir()):
        if (run_dir / "trajectory.json").exists():
            try:
                rendered.append(render_run(run_dir))
            except Exception as exc:  # noqa: BLE001
                console.print(f"[yellow]skipping {run_dir}: {exc}[/yellow]")
    index = render_index(target)
    console.print(f"[green]wrote {len(rendered)} reports + index:[/green] {index}")
    return 0


def cmd_test(args: argparse.Namespace) -> int:
    from .runner import discover, render_summary, run_one

    cases = discover(args.path)
    if not cases:
        console.print(f"[yellow]No @cua_test cases discovered under {args.path}[/yellow]")
        return 1

    console.print(Panel.fit(
        f"[bold]discovered:[/bold] {len(cases)} test case(s)\n"
        f"[bold]path:[/bold]       {args.path}\n"
        f"[bold]CDP:[/bold]        {'disabled' if args.no_cdp else 'auto'}\n"
        f"[bold]runs dir:[/bold]   {args.runs_dir}",
        title="CUA-Lark · test",
        border_style="cyan",
    ))

    selected = cases
    if args.tag:
        selected = [c for c in cases if args.tag in c.tags]
        if not selected:
            console.print(f"[yellow]No tests matched tag {args.tag!r}[/yellow]")
            return 1

    reports = []
    for case in selected:
        console.print(f"\n[cyan]→ {case.name}[/cyan]" + (f" [dim]{list(case.tags)}[/dim]" if case.tags else ""))
        report = run_one(case, runs_root=args.runs_dir, use_cdp=not args.no_cdp)
        reports.append(report)

    console.print()
    render_summary(reports)
    return 0 if all(r.passed for r in reports) else 1


def cmd_run(args: argparse.Namespace) -> int:
    instruction = args.instruction.strip()
    if not instruction:
        console.print("[red]instruction is empty[/red]")
        return 2

    traj = Trajectory.new(instruction, root=args.runs_dir)
    console.print(Panel.fit(
        f"[bold]instruction:[/bold] {instruction}\n"
        f"[bold]run dir:[/bold]     {traj.run_dir}\n"
        f"[bold]model:[/bold]       {args.model or 'default'}\n"
        f"[bold]max_steps:[/bold]   {args.max_steps or 'default'}",
        title="CUA-Lark",
        border_style="cyan",
    ))

    agent = Agent(model=args.model, max_steps=args.max_steps, trajectory=traj)
    try:
        summary = agent.run(instruction)
    except KeyboardInterrupt:
        console.print("\n[yellow]interrupted by user[/yellow]")
        traj.save(final_text="", status="interrupted")
        return 130
    except Exception as exc:  # noqa: BLE001 — top-level crash boundary
        console.print(f"[red]agent crashed:[/red] {exc}")
        traj.save(final_text=str(exc), status="crashed")
        raise

    style = "green" if summary["status"] == "completed" else "yellow"
    console.print(Panel.fit(
        f"[bold]status:[/bold]   {summary['status']}\n"
        f"[bold]steps:[/bold]    {summary['steps_used']}\n"
        f"[bold]final:[/bold]    {summary['final_text'] or '(no final text)'}\n"
        f"[bold]log:[/bold]      {traj.run_dir / 'trajectory.json'}",
        title="Result",
        border_style=style,
    ))
    return 0 if summary["status"] == "completed" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cua-lark",
        description="Vision-driven Computer-Use Agent for Feishu desktop QA testing.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run one natural-language instruction.")
    run.add_argument("instruction", help="Natural-language task, in English or Chinese.")
    run.add_argument("--model", default=None, help="Override Claude model ID.")
    run.add_argument("--max-steps", type=int, default=None, help="Hard cap on agent steps.")
    run.add_argument(
        "--runs-dir",
        default="runs",
        type=Path,
        help="Directory under which per-run artifacts are written (default: ./runs).",
    )
    run.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging.")
    run.set_defaults(func=cmd_run)

    test = sub.add_parser("test", help="Run @cua_test cases discovered in a path.")
    test.add_argument("path", type=Path, help="File or directory containing test cases.")
    test.add_argument(
        "--no-cdp",
        action="store_true",
        help="Skip CDP session; assertions fall back to the VLM channel only.",
    )
    test.add_argument("--tag", default=None, help="Only run cases registered with this tag.")
    test.add_argument(
        "--runs-dir",
        default="runs",
        type=Path,
        help="Directory under which per-run artifacts are written (default: ./runs).",
    )
    test.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging.")
    test.set_defaults(func=cmd_test)

    report = sub.add_parser(
        "report",
        help="Generate a self-contained HTML report from a runs/ directory or a single run.",
    )
    report.add_argument(
        "path",
        type=Path,
        help="Either a single run dir (containing trajectory.json) or a runs/ root.",
    )
    report.add_argument("--verbose", "-v", action="store_true", help="Enable debug logging.")
    report.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
