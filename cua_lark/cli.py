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
