"""Chrome DevTools Protocol client for Electron-based apps.

Feishu desktop is Electron, so launching it with ``--remote-debugging-port=9222``
exposes its renderer processes via the standard CDP. We use it for *reads only*
— DOM/a11y inspection, JS evaluation, network introspection — never for clicks
or keystrokes, since those must traverse the OS to count as a real-user test.

Why a hand-rolled client instead of pychrome / pycdp:
- The surface we need is tiny (~5 RPC methods).
- Avoids pulling an async-first dependency into a synchronous codebase.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

import httpx
from websocket import WebSocket, create_connection

log = logging.getLogger(__name__)

DEFAULT_PORT = 9222


class CDPError(Exception):
    """Raised for any CDP transport or protocol failure."""


@dataclass
class CDPTarget:
    id: str
    type: str
    title: str
    url: str
    ws_url: str

    @property
    def is_page(self) -> bool:
        return self.type == "page"


def list_targets(host: str = "localhost", port: int = DEFAULT_PORT, timeout: float = 3.0) -> list[CDPTarget]:
    """Fetch the debuggable targets exposed by an Electron/Chrome process."""
    url = f"http://{host}:{port}/json"
    try:
        resp = httpx.get(url, timeout=timeout)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise CDPError(
            f"Cannot reach CDP at {host}:{port} — is Feishu launched with "
            f"--remote-debugging-port={port}? ({exc})"
        ) from exc
    return [
        CDPTarget(
            id=t["id"],
            type=t.get("type", ""),
            title=t.get("title", ""),
            url=t.get("url", ""),
            ws_url=t["webSocketDebuggerUrl"],
        )
        for t in resp.json()
        if "webSocketDebuggerUrl" in t
    ]


class CDPSession:
    """Synchronous JSON-RPC over a single CDP websocket.

    Intended use::

        with CDPSession(target.ws_url) as cdp:
            text = cdp.query_selector_text(".message-content:last-child")
    """

    def __init__(self, ws_url: str, timeout: float = 5.0):
        self.ws_url = ws_url
        self.timeout = timeout
        self._ws: WebSocket | None = None
        self._next_id = 0

    def __enter__(self) -> "CDPSession":
        self._ws = create_connection(self.ws_url, timeout=self.timeout)
        return self

    def __exit__(self, *exc) -> None:
        if self._ws is not None:
            try:
                self._ws.close()
            finally:
                self._ws = None

    # ---- low-level RPC ---------------------------------------------------

    def send(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if self._ws is None:
            raise CDPError("CDPSession is not open — use it as a context manager")
        self._next_id += 1
        msg_id = self._next_id
        payload: dict[str, Any] = {"id": msg_id, "method": method}
        if params:
            payload["params"] = params
        self._ws.send(json.dumps(payload))

        # CDP interleaves events with command responses; loop until our id returns.
        while True:
            raw = self._ws.recv()
            data = json.loads(raw)
            if data.get("id") != msg_id:
                continue  # asynchronous event, ignore
            if "error" in data:
                raise CDPError(f"{method} failed: {data['error']}")
            return data.get("result", {})

    # ---- high-level helpers ----------------------------------------------

    def evaluate(self, expression: str, return_by_value: bool = True) -> Any:
        """Execute JS in the page context and return the (optionally unwrapped) result."""
        result = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": return_by_value,
            "awaitPromise": True,
        })
        if result.get("exceptionDetails"):
            details = result["exceptionDetails"]
            raise CDPError(f"JS error: {details.get('text', details)}")
        ro = result.get("result", {})
        return ro.get("value") if return_by_value else ro

    def query_selector_text(self, selector: str) -> str | None:
        """Return ``innerText`` of the first match, or None."""
        return self.evaluate(
            f"document.querySelector({json.dumps(selector)})?.innerText ?? null"
        )

    def query_selector_all_texts(self, selector: str) -> list[str]:
        """Return ``innerText`` for every match. Empty list if nothing matches."""
        return self.evaluate(
            f"Array.from(document.querySelectorAll({json.dumps(selector)}))"
            ".map(e => e.innerText)"
        ) or []

    def visible_text(self) -> str:
        """``document.body.innerText`` — useful when no selector is known."""
        return self.evaluate("document.body.innerText") or ""

    def url(self) -> str:
        return self.evaluate("location.href") or ""

    def title(self) -> str:
        return self.evaluate("document.title") or ""


def find_target(
    predicate: Callable[[CDPTarget], bool],
    host: str = "localhost",
    port: int = DEFAULT_PORT,
) -> CDPTarget | None:
    for t in list_targets(host=host, port=port):
        if predicate(t):
            return t
    return None


def feishu_session(host: str = "localhost", port: int = DEFAULT_PORT) -> CDPSession:
    """Pick the most likely Feishu page target and return an *unopened* session.

    The caller is expected to use ``with`` to manage the websocket lifetime.
    Heuristic: prefer a page whose URL or title hints at Feishu/Lark, fall
    back to the first page-type target if nothing matches.
    """
    pages = [t for t in list_targets(host=host, port=port) if t.is_page]
    if not pages:
        raise CDPError(f"No page targets exposed on {host}:{port}")
    feishu_pages = [
        t for t in pages
        if "feishu" in (t.url + t.title).lower() or "lark" in (t.url + t.title).lower()
    ]
    target = (feishu_pages or pages)[0]
    log.debug("CDP session targeting: %s — %s", target.title, target.url)
    return CDPSession(target.ws_url)
