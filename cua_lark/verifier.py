"""Three-channel assertion engine.

A single assertion can run via any of:

- **VLM** (always available, costs tokens) — ask Claude whether a claim about
  the current screen is true. Robust to UI noise; sufficient for most QA.
- **CDP** (deterministic, requires Electron debug port) — query the live DOM
  via Chrome DevTools Protocol. Exact and cheap.
- **OCR** (planned) — local Tesseract / RapidOCR fallback for offline runs.

The DSL routes assertions to the channel with the least cost that can answer
the question. Users can force a channel by calling the verifier directly.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Literal

from anthropic import Anthropic

from .cdp import CDPError, CDPSession
from .perception import capture_b64

log = logging.getLogger(__name__)

Channel = Literal["vlm", "cdp", "ocr"]


@dataclass
class AssertionResult:
    name: str
    passed: bool
    channel: Channel
    detail: str = ""
    screenshot: str | None = None


_VERIFY_SYSTEM = """You are the verification component of a GUI testing harness.
Given a screenshot and a yes/no claim about what is visible, respond with a
single JSON object — no prose, no code fences:

  {"passed": <true|false>, "reason": "<one short sentence>"}

Be conservative. Only answer true if the claim is plainly visible in the
screenshot. Do not infer beyond what the pixels show."""


def _extract_json(text: str) -> dict:
    """Pull a JSON object out of an LLM response, tolerating code fences."""
    text = text.strip()
    if text.startswith("```"):
        # strip ```json ... ``` or ``` ... ```
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError(f"No JSON object in: {text!r}")
    return json.loads(text[start : end + 1])


class VlmVerifier:
    """Semantic assertion via Claude vision."""

    def __init__(self, client: Anthropic | None = None, model: str = "claude-sonnet-4-6"):
        self.client = client or Anthropic()
        self.model = model

    def assert_visible(self, claim: str, screenshot_b64: str | None = None) -> AssertionResult:
        b64 = screenshot_b64 if screenshot_b64 is not None else capture_b64()[0]
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=300,
            system=_VERIFY_SYSTEM,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": f"Claim: {claim}"},
                ],
            }],
        )
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        try:
            obj = _extract_json(text)
            passed = bool(obj.get("passed"))
            reason = str(obj.get("reason", ""))[:240]
        except Exception as exc:  # noqa: BLE001 — surface parse failures as test failures
            passed, reason = False, f"verifier output unparsable ({exc}): {text[:200]}"
        return AssertionResult(name=claim, passed=passed, channel="vlm", detail=reason)


class CdpVerifier:
    """Structured assertions against the live Electron DOM."""

    def __init__(self, session: CDPSession):
        self.session = session

    def assert_text(self, selector: str, contains: str) -> AssertionResult:
        name = f"text({selector!r}) contains {contains!r}"
        try:
            actual = self.session.query_selector_text(selector) or ""
        except CDPError as exc:
            return AssertionResult(name=name, passed=False, channel="cdp", detail=str(exc))
        return AssertionResult(
            name=name,
            passed=contains in actual,
            channel="cdp",
            detail=f"actual: {actual[:120]!r}",
        )

    def assert_any_text(self, selector: str, contains: str) -> AssertionResult:
        name = f"any({selector!r}) contains {contains!r}"
        try:
            texts = self.session.query_selector_all_texts(selector)
        except CDPError as exc:
            return AssertionResult(name=name, passed=False, channel="cdp", detail=str(exc))
        return AssertionResult(
            name=name,
            passed=any(contains in t for t in texts),
            channel="cdp",
            detail=f"n_elements={len(texts)}",
        )

    def assert_visible_text(self, contains: str) -> AssertionResult:
        name = f"body contains {contains!r}"
        try:
            body = self.session.visible_text()
        except CDPError as exc:
            return AssertionResult(name=name, passed=False, channel="cdp", detail=str(exc))
        return AssertionResult(name=name, passed=contains in body, channel="cdp")
