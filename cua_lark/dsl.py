"""Decorator-based test DSL.

A test case is a function decorated with :func:`cua_test` that takes a
:class:`TestContext`. The context exposes ``do(instruction)`` to run the
agent and ``assert_*`` methods that accumulate :class:`AssertionResult` s::

    @cua_test("IM: send hello", "im")
    def test_send(ctx: TestContext):
        ctx.do("Bring Feishu to the foreground")
        ctx.do("Open the first chat")
        ctx.do("Type 'hello from CUA-Lark' in the input box")
        ctx.assert_visible(
            "the text 'hello from CUA-Lark' is visible in the message input box"
        )

The runner discovers tests, executes each in its own trajectory dir, and
emits a structured :class:`TestReport`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .agent import Agent
from .cdp import CDPSession
from .trajectory import Trajectory
from .verifier import AssertionResult, CdpVerifier, VlmVerifier

log = logging.getLogger(__name__)

_REGISTRY: list["TestCase"] = []


@dataclass
class TestCase:
    name: str
    func: Callable[["TestContext"], None]
    tags: tuple[str, ...] = ()


def cua_test(name: str, *tags: str) -> Callable:
    """Register a function as a CUA-Lark test case."""

    def wrap(func: Callable[["TestContext"], None]) -> Callable:
        _REGISTRY.append(TestCase(name=name, func=func, tags=tags))
        return func

    return wrap


def registered_tests() -> list[TestCase]:
    return list(_REGISTRY)


def clear_registry() -> None:
    """Drop all registered tests. Mainly useful in unit tests of the DSL itself."""
    _REGISTRY.clear()


@dataclass
class TestContext:
    """Per-test handle passed to user code."""

    name: str
    trajectory: Trajectory
    agent: Agent
    vlm: VlmVerifier
    cdp: CDPSession | None = None
    assertions: list[AssertionResult] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)

    # ---- agent driving ---------------------------------------------------

    def do(self, instruction: str) -> dict:
        """Run the agent against one natural-language instruction."""
        log.info("[%s] do: %s", self.name, instruction)
        result = self.agent.run(instruction)
        self.steps.append({"instruction": instruction, **result})
        return result

    # ---- assertions ------------------------------------------------------

    def assert_visible(self, claim: str) -> AssertionResult:
        result = self.vlm.assert_visible(claim)
        self.assertions.append(result)
        log.info("[%s] assert_visible(%s) -> %s", self.name, claim, result.passed)
        return result

    def assert_dom_text(self, selector: str, contains: str) -> AssertionResult:
        if self.cdp is None:
            res = AssertionResult(
                name=f"dom({selector!r}) contains {contains!r}",
                passed=False,
                channel="cdp",
                detail="CDP session unavailable; launch Feishu with --remote-debugging-port=9222",
            )
            self.assertions.append(res)
            return res
        res = CdpVerifier(self.cdp).assert_text(selector, contains)
        self.assertions.append(res)
        log.info("[%s] assert_dom_text(%s) -> %s", self.name, selector, res.passed)
        return res

    def assert_dom_any(self, selector: str, contains: str) -> AssertionResult:
        if self.cdp is None:
            res = AssertionResult(
                name=f"any({selector!r}) contains {contains!r}",
                passed=False,
                channel="cdp",
                detail="CDP session unavailable",
            )
            self.assertions.append(res)
            return res
        res = CdpVerifier(self.cdp).assert_any_text(selector, contains)
        self.assertions.append(res)
        return res

    @property
    def passed(self) -> bool:
        return bool(self.assertions) and all(a.passed for a in self.assertions)


@dataclass
class TestReport:
    case: TestCase
    started_at: str
    duration_s: float
    passed: bool
    assertions: list[AssertionResult]
    trajectory_dir: Path
    error: str = ""
