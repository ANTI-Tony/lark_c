"""PyAutoGUI wrapper that turns Claude tool-use payloads into real OS events.

All coordinates entering this module are in *Claude-space* — the pixel space
of whatever screenshot we showed the model. We scale them back to PyAutoGUI's
logical space before dispatching.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import pyautogui

# Flicking the mouse to any screen corner aborts — prevents a runaway loop
# from locking the user out of their machine.
pyautogui.FAILSAFE = True
# Small pause between PyAutoGUI primitives; the agent loop adds more on top.
pyautogui.PAUSE = 0.05


# Map Claude / human key names to PyAutoGUI names. PyAutoGUI is picky.
_KEY_ALIASES = {
    "cmd": "command",
    "super": "command",
    "win": "win",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "option",
    "option": "option",
    "shift": "shift",
    "return": "enter",
    "enter": "enter",
    "esc": "escape",
    "escape": "escape",
    "del": "delete",
    "delete": "delete",
    "backspace": "backspace",
    "space": "space",
    "tab": "tab",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "page_up": "pageup",
    "page_down": "pagedown",
    "home": "home",
    "end": "end",
}


def _map_key(token: str) -> str:
    t = token.strip().lower()
    return _KEY_ALIASES.get(t, t)


def parse_key_combo(combo: str) -> list[str]:
    """Split ``cmd+shift+t`` into PyAutoGUI-friendly tokens."""
    return [_map_key(p) for p in combo.replace(" ", "").split("+") if p]


@dataclass
class ActionResult:
    """Outcome of a single action dispatch."""

    action: str
    ok: bool
    detail: str = ""
    latency_ms: int = 0


class Executor:
    """Dispatches Claude computer-tool actions as PyAutoGUI calls.

    ``scale`` scales from Claude-space down to logical space. Pass the
    value from ``perception.DisplayInfo.scale`` — but if the screenshot
    we sent Claude was resized, multiply by ``(resized_w / physical_w)``
    so the round trip cancels out. The Agent does that math before
    constructing the Executor.
    """

    def __init__(self, scale: float = 1.0, min_action_gap_ms: int = 120):
        self.scale = scale
        self.min_action_gap_ms = min_action_gap_ms
        self._last_action_at: float = 0.0

    # ---- internal helpers -------------------------------------------------

    def _throttle(self) -> None:
        elapsed_ms = (time.monotonic() - self._last_action_at) * 1000
        if elapsed_ms < self.min_action_gap_ms:
            time.sleep((self.min_action_gap_ms - elapsed_ms) / 1000)
        self._last_action_at = time.monotonic()

    def _to_logical(self, coord: tuple[int, int] | list[int]) -> tuple[int, int]:
        x, y = coord
        return int(round(x / self.scale)), int(round(y / self.scale))

    # ---- primitives -------------------------------------------------------

    def move(self, coord):
        self._throttle()
        x, y = self._to_logical(coord)
        pyautogui.moveTo(x, y, duration=0.1)

    def click(self, coord, button: str = "left", clicks: int = 1):
        self._throttle()
        x, y = self._to_logical(coord)
        pyautogui.click(x, y, clicks=clicks, button=button, interval=0.08)

    def double_click(self, coord):
        self.click(coord, clicks=2)

    def right_click(self, coord):
        self.click(coord, button="right")

    def middle_click(self, coord):
        self.click(coord, button="middle")

    def drag(self, start, end, button: str = "left"):
        self._throttle()
        sx, sy = self._to_logical(start)
        ex, ey = self._to_logical(end)
        pyautogui.moveTo(sx, sy)
        pyautogui.dragTo(ex, ey, duration=0.35, button=button)

    def type_text(self, text: str):
        self._throttle()
        # ``typewrite`` only handles ASCII. Fall back to ``write`` semantics
        # via the clipboard for non-ASCII so Chinese characters work.
        if text.isascii():
            pyautogui.typewrite(text, interval=0.015)
        else:
            self._paste_unicode(text)

    def _paste_unicode(self, text: str) -> None:
        # macOS-friendly clipboard paste. We keep the dependency surface small
        # by shelling out to ``pbcopy`` rather than adding pyperclip.
        import subprocess
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
        pyautogui.hotkey("command", "v")

    def key(self, combo: str):
        self._throttle()
        keys = parse_key_combo(combo)
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)

    def scroll(self, clicks: int, coord=None):
        self._throttle()
        if coord is not None:
            x, y = self._to_logical(coord)
            pyautogui.moveTo(x, y)
        pyautogui.scroll(clicks)

    def wait(self, seconds: float):
        time.sleep(max(0.0, min(seconds, 10.0)))

    # ---- top-level dispatch ----------------------------------------------

    def dispatch(self, tool_input: dict[str, Any]) -> ActionResult:
        """Run one Claude computer-tool call. Returns an ActionResult."""
        action = tool_input.get("action", "")
        start = time.monotonic()
        try:
            self._run(action, tool_input)
            ok, detail = True, ""
        except Exception as exc:  # noqa: BLE001 — report every failure upstream
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        latency_ms = int((time.monotonic() - start) * 1000)
        return ActionResult(action=action, ok=ok, detail=detail, latency_ms=latency_ms)

    def _run(self, action: str, ti: dict[str, Any]) -> None:
        coord = ti.get("coordinate")
        text = ti.get("text")

        if action == "screenshot":
            # Handled by the Agent loop; nothing to execute at the OS level.
            return
        if action == "mouse_move":
            self.move(coord)
        elif action == "left_click":
            self.click(coord or pyautogui.position())
        elif action == "right_click":
            self.right_click(coord or pyautogui.position())
        elif action == "middle_click":
            self.middle_click(coord or pyautogui.position())
        elif action == "double_click":
            self.double_click(coord or pyautogui.position())
        elif action == "triple_click":
            self.click(coord or pyautogui.position(), clicks=3)
        elif action == "left_click_drag":
            start = ti.get("start_coordinate") or pyautogui.position()
            end = coord
            self.drag(start, end)
        elif action == "type":
            self.type_text(text or "")
        elif action == "key":
            self.key(text or "")
        elif action == "hold_key":
            duration = float(ti.get("duration", 1.0))
            keys = parse_key_combo(text or "")
            for k in keys:
                pyautogui.keyDown(k)
            time.sleep(duration)
            for k in reversed(keys):
                pyautogui.keyUp(k)
        elif action == "scroll":
            direction = ti.get("scroll_direction", "down")
            amount = int(ti.get("scroll_amount", 3))
            signed = amount if direction == "up" else -amount
            self.scroll(signed, coord)
        elif action == "wait":
            self.wait(float(ti.get("duration", 1.0)))
        elif action == "cursor_position":
            # No-op; the Agent will report the position in its own log.
            return
        else:
            raise ValueError(f"Unsupported action: {action!r}")
