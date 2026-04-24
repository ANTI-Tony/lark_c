"""Hello-world smoke test against the live Feishu desktop client.

Prerequisites:
- Feishu desktop client is installed and launched (logged in).
- ANTHROPIC_API_KEY is set (in env or .env).
- On macOS, your terminal has Screen Recording + Accessibility permissions.

Run::

    python examples/hello_feishu.py

This drives five single-step actions back-to-back, which is the M1 exit
criterion. It does not assert on results yet — M2 will layer the verifier
on top.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a plain script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from cua_lark.agent import Agent
from cua_lark.trajectory import Trajectory


SMOKE_INSTRUCTIONS = [
    "Bring the Feishu (Lark) desktop app to the foreground. If it's not running, stop and report that.",
    "In Feishu, click on the Messages / IM tab in the left sidebar.",
    "Open the first chat in the conversation list.",
    "Click the message input box at the bottom of the chat.",
    "Type 'hello from CUA-Lark' into the input box, but do NOT press Enter.",
]


def main() -> int:
    print("CUA-Lark · Feishu smoke test (M1)")
    print("-" * 60)
    passed, failed = 0, 0
    for i, instruction in enumerate(SMOKE_INSTRUCTIONS, 1):
        print(f"\n[{i}/{len(SMOKE_INSTRUCTIONS)}] {instruction}")
        traj = Trajectory.new(instruction, root="runs")
        agent = Agent(trajectory=traj, max_steps=8)
        result = agent.run(instruction)
        ok = result["status"] == "completed"
        passed += int(ok)
        failed += int(not ok)
        marker = "✓" if ok else "✗"
        print(f"    {marker} status={result['status']} steps={result['steps_used']}")
        print(f"      summary: {result['final_text'][:120]}")
        print(f"      log:     {traj.run_dir}")

    print("\n" + "=" * 60)
    print(f"passed: {passed}/{passed + failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
