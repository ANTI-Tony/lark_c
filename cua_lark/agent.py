"""Claude Computer Use agent loop — the engine of CUA-Lark.

The loop is deliberately small:

    initial screenshot
        │
        ▼
    send (instruction, image) → Claude
        │
        ▼
    for each tool_use block:
        Executor.dispatch(...)
        take fresh screenshot
        append tool_result
        │
        ▼
    until stop_reason == "end_turn" or step budget exhausted

Everything else (DSL, verification, reporting) builds on top of this.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from anthropic import Anthropic

from .executor import Executor
from .perception import capture_b64, probe_display
from .trajectory import Trajectory

log = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"
# Claude Sonnet 4.6 / Opus 4.6+ require the 2025-11-24 contract.
# Older models (Sonnet 4.5, Haiku 4.5, Sonnet 3.7, ...) use computer_20250124
# with the computer-use-2025-01-24 beta header — but we don't target those.
BETA_HEADER = "computer-use-2025-11-24"
TOOL_TYPE = "computer_20251124"

SYSTEM_PROMPT = """You are CUA-Lark, a GUI testing agent driving the Feishu (Lark) desktop client.

Operating rules:
- Ground every action in the most recent screenshot. Never guess coordinates.
- Prefer one atomic action per tool call (one click, one keypress, one short type).
- After an action that may change state, inspect the next screenshot before the next action.
- If Feishu is not in the foreground, bring it forward (click its dock icon or use app-switcher) before interacting.
- When the user's goal is complete, produce a one-sentence summary and stop (end_turn).
- If the goal is blocked (wrong app, modal, missing permission), explain the blocker and stop."""


def _block_to_dict(block: Any) -> dict[str, Any]:
    """Convert an SDK content block into a plain dict we can feed back in."""
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    if isinstance(block, dict):
        return block
    raise TypeError(f"Cannot serialize content block of type {type(block)!r}")


class Agent:
    """One-shot agent runner. Construct, call :meth:`run`, inspect trajectory."""

    def __init__(
        self,
        model: str | None = None,
        max_steps: int | None = None,
        trajectory: Trajectory | None = None,
        client: Anthropic | None = None,
    ):
        self.client = client or Anthropic()
        self.model = model or os.getenv("CUA_LARK_MODEL", DEFAULT_MODEL)
        self.max_steps = max_steps or int(os.getenv("CUA_LARK_MAX_STEPS", "20"))
        self.trajectory = trajectory

        display = probe_display()
        # A dry-run screenshot tells us the final (possibly resized) dims that
        # Claude will see. We use the same dims in the tool definition so the
        # model's coordinates and our Executor agree on the frame of reference.
        _, (claude_w, claude_h) = capture_b64()
        self.claude_dims = (claude_w, claude_h)
        # Executor scale maps Claude-space → PyAutoGUI logical-space.
        self.executor = Executor(scale=claude_w / display.logical_width)

        log.debug(
            "Agent ready: model=%s, display=%sx%s logical, %sx%s claude, scale=%.3f",
            self.model,
            display.logical_width,
            display.logical_height,
            claude_w,
            claude_h,
            self.executor.scale,
        )

    # ---- main loop -------------------------------------------------------

    def run(self, instruction: str) -> dict[str, Any]:
        """Execute one instruction. Returns a summary dict."""
        initial_b64, _ = capture_b64()
        if self.trajectory:
            self.trajectory.save_screenshot(initial_b64)

        messages: list[dict[str, Any]] = [{
            "role": "user",
            "content": [
                {"type": "text", "text": instruction},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": initial_b64,
                    },
                },
            ],
        }]

        tools = [{
            "type": TOOL_TYPE,
            "name": "computer",
            "display_width_px": self.claude_dims[0],
            "display_height_px": self.claude_dims[1],
            "display_number": 1,
        }]

        final_text = ""
        stop_reason = None
        steps_used = 0

        for step in range(1, self.max_steps + 1):
            steps_used = step
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                tools=tools,
                messages=messages,
                betas=[BETA_HEADER],
            )
            stop_reason = resp.stop_reason

            serialized = [_block_to_dict(b) for b in resp.content]
            messages.append({"role": "assistant", "content": serialized})

            text_chunks = [b.text for b in resp.content if b.type == "text"]
            if text_chunks:
                final_text = "\n".join(text_chunks)
            if self.trajectory:
                self.trajectory.log_assistant(step, final_text, stop_reason)

            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            if stop_reason == "end_turn" or not tool_uses:
                break

            tool_results = []
            for tu in tool_uses:
                tool_input = dict(tu.input) if hasattr(tu, "input") else {}
                result = self.executor.dispatch(tool_input)

                after_b64, _ = capture_b64()
                after_filename = None
                if self.trajectory:
                    after_filename = self.trajectory.save_screenshot(after_b64)
                    self.trajectory.log_action(step, tu.id, tool_input, result, after_filename)

                blocks: list[dict[str, Any]] = []
                if not result.ok:
                    blocks.append({"type": "text", "text": f"Action failed: {result.detail}"})
                blocks.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": after_b64,
                    },
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": blocks,
                    "is_error": not result.ok,
                })

            messages.append({"role": "user", "content": tool_results})
        else:
            log.warning("Agent exhausted step budget (%d) without end_turn", self.max_steps)

        status = "completed" if stop_reason == "end_turn" else "step_budget_exhausted"
        if self.trajectory:
            self.trajectory.save(final_text=final_text, status=status)

        return {
            "final_text": final_text,
            "stop_reason": stop_reason,
            "status": status,
            "steps_used": steps_used,
        }
