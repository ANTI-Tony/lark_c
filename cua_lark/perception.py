"""Screen capture and encoding.

Responsible for producing images the Planner can reason about, and for
surfacing the display metadata the Executor needs to scale coordinates
back from Claude-space (physical pixels) to PyAutoGUI-space (logical pixels).
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass

import pyautogui
from PIL import Image


# Claude Computer Use recommends capping the image width at roughly 1280 px
# to keep token counts sane without losing UI detail. Above this we downscale.
MAX_WIDTH = 1280


@dataclass(frozen=True)
class DisplayInfo:
    """Captured display geometry.

    ``physical_*`` is the screenshot resolution (Retina = 2× on modern Macs).
    ``logical_*`` is the coordinate space PyAutoGUI uses.
    ``scale`` = physical / logical; Executor divides click coords by this.
    """

    physical_width: int
    physical_height: int
    logical_width: int
    logical_height: int
    scale: float

    @property
    def as_claude_dims(self) -> tuple[int, int]:
        """Dimensions we advertise to Claude's computer tool."""
        return self.physical_width, self.physical_height


def probe_display() -> DisplayInfo:
    """Measure the screen once; cheap but not free, call at startup."""
    logical_w, logical_h = pyautogui.size()
    img = pyautogui.screenshot()
    physical_w, physical_h = img.size
    scale = physical_w / logical_w if logical_w else 1.0
    return DisplayInfo(
        physical_width=physical_w,
        physical_height=physical_h,
        logical_width=logical_w,
        logical_height=logical_h,
        scale=scale,
    )


def capture() -> Image.Image:
    """Return a PIL image of the full primary display."""
    return pyautogui.screenshot()


def capture_b64(resize: bool = True) -> tuple[str, tuple[int, int]]:
    """Capture the screen and return (base64 PNG, (width, height)).

    When ``resize`` is True and the screenshot exceeds ``MAX_WIDTH``, we
    downscale preserving aspect ratio. Claude sees the resized dimensions,
    so callers must advertise the returned size (not the original) to the
    computer tool, and scale the returned coordinates back up before
    executing them.
    """
    img = capture()
    w, h = img.size
    if resize and w > MAX_WIDTH:
        ratio = MAX_WIDTH / w
        new_size = (MAX_WIDTH, int(h * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        w, h = new_size

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    b64 = base64.standard_b64encode(buf.getvalue()).decode("ascii")
    return b64, (w, h)
