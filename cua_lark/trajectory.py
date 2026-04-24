"""Per-run artifact logging: screenshots + structured step log."""

from __future__ import annotations

import base64
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .executor import ActionResult


class Trajectory:
    """A flat, append-only log of everything a single agent run did.

    Layout::

        runs/20260425_120501/
            shot_000.png      # initial screenshot
            shot_001.png      # after step 1 action
            ...
            trajectory.json   # structured log, cross-references shot_NNN.png
    """

    def __init__(self, run_dir: Path, instruction: str):
        self.run_dir = run_dir
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.instruction = instruction
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.steps: list[dict[str, Any]] = []
        self._shot_counter = 0

    @classmethod
    def new(cls, instruction: str, root: Path | str = "runs") -> "Trajectory":
        root = Path(root)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return cls(run_dir=root / ts, instruction=instruction)

    # ---- logging primitives ----------------------------------------------

    def save_screenshot(self, b64: str) -> str:
        filename = f"shot_{self._shot_counter:03d}.png"
        (self.run_dir / filename).write_bytes(base64.standard_b64decode(b64))
        self._shot_counter += 1
        return filename

    def log_assistant(self, step: int, text: str, stop_reason: str | None) -> None:
        self.steps.append({
            "step": step,
            "kind": "assistant",
            "text": text,
            "stop_reason": stop_reason,
        })

    def log_action(
        self,
        step: int,
        tool_use_id: str,
        tool_input: dict[str, Any],
        result: ActionResult,
        after_screenshot: str | None,
    ) -> None:
        self.steps.append({
            "step": step,
            "kind": "action",
            "tool_use_id": tool_use_id,
            "input": tool_input,
            "result": asdict(result),
            "screenshot_after": after_screenshot,
        })

    # ---- finalize ---------------------------------------------------------

    def save(self, final_text: str = "", status: str = "completed") -> Path:
        path = self.run_dir / "trajectory.json"
        payload = {
            "started_at": self.started_at,
            "ended_at": datetime.now().isoformat(timespec="seconds"),
            "instruction": self.instruction,
            "status": status,
            "final_text": final_text,
            "steps": self.steps,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
