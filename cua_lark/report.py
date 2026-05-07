"""Self-contained HTML report generator.

Reads ``runs/<ts>/`` (trajectory.json + shot_*.png + optional test_report.json)
and emits ``runs/<ts>/report.html`` — a single file with all screenshots
inlined as data URIs. No JS, no external assets, opens in any browser.

We deliberately do not depend on Jinja or any templating library. The DOM is
small and the inline CSS is short; a few f-strings keep the install footprint
tiny and the output trivial to inspect.
"""

from __future__ import annotations

import base64
import json
from html import escape
from pathlib import Path
from typing import Any


_CSS = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                 "Helvetica Neue", Helvetica, Arial, sans-serif;
    max-width: 1080px; margin: 2rem auto; padding: 0 1.25rem; color: #1f2328;
    line-height: 1.55;
}
h1 { margin: 0 0 0.5rem; font-size: 1.6rem; }
h2 { margin-top: 2.5rem; font-size: 1.15rem; border-bottom: 1px solid #e3e6ea; padding-bottom: 0.3rem; }
.meta { color: #57606a; font-size: 0.92rem; margin-bottom: 1.5rem; }
.meta strong { color: #1f2328; }
.badge { display: inline-block; padding: 0.1em 0.55em; border-radius: 999px; font-size: 0.75rem; font-weight: 600; vertical-align: 1px; }
.badge.pass { background: #1a7f37; color: #fff; }
.badge.fail { background: #cf222e; color: #fff; }
.badge.warn { background: #9a6700; color: #fff; }
.card {
    border: 1px solid #d0d7de; border-radius: 8px;
    padding: 1rem 1.1rem; margin: 0.75rem 0;
    background: #fff;
}
.card.fail { border-color: #ff8182; background: #fff5f5; }
.card.assistant { background: #f6f8fa; border-color: #d0d7de; }
.row { display: flex; gap: 1rem; flex-wrap: wrap; }
.row > .left { flex: 1.4; min-width: 280px; }
.row > .right { flex: 1; min-width: 220px; }
img.shot {
    max-width: 100%; border: 1px solid #d0d7de; border-radius: 4px;
    background: #f6f8fa;
}
pre, code {
    font-family: ui-monospace, "SF Mono", Menlo, Monaco, Consolas, monospace;
    font-size: 0.85rem;
}
pre {
    background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 4px;
    padding: 0.5rem 0.75rem; overflow-x: auto;
}
.kv { font-size: 0.85rem; color: #57606a; }
.kv strong { color: #1f2328; }
.tag { display: inline-block; padding: 0 0.4em; background: #ddf4ff; color: #0969da; border-radius: 3px; font-size: 0.78rem; margin-right: 0.3em; }
.action-name { font-weight: 600; color: #1f2328; }
.assertion { padding: 0.5rem 0.75rem; border-radius: 6px; margin: 0.4rem 0; }
.assertion.pass { background: #dafbe1; }
.assertion.fail { background: #ffebe9; }
.muted { color: #57606a; }
"""


def _img_data_uri(path: Path) -> str:
    if not path.exists():
        return ""
    encoded = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _action_card(step: dict, run_dir: Path) -> str:
    inp = step.get("input", {}) or {}
    action_name = inp.get("action", "?")
    result = step.get("result", {}) or {}
    ok = bool(result.get("ok"))
    cls = "card" if ok else "card fail"
    status = '<span class="badge pass">ok</span>' if ok else '<span class="badge fail">err</span>'
    detail = result.get("detail") or ""
    latency = result.get("latency_ms", "?")
    shot = step.get("screenshot_after")
    shot_uri = _img_data_uri(run_dir / shot) if shot else ""
    inp_pretty = escape(json.dumps(inp, ensure_ascii=False, indent=2))
    return f"""
<div class="{cls}">
  <div class="kv">
    Step {step.get("step", "?")} · <span class="action-name">{escape(action_name)}</span>
    {status}
    <span class="muted">· {latency} ms</span>
  </div>
  <div class="row" style="margin-top:0.6rem;">
    <div class="left">
      <pre>{inp_pretty}</pre>
      {f'<div class="kv" style="margin-top:0.5rem;">detail: {escape(detail)}</div>' if detail else ""}
    </div>
    <div class="right">
      {f'<img class="shot" src="{shot_uri}" alt="after action">' if shot_uri else '<div class="muted">no screenshot</div>'}
    </div>
  </div>
</div>"""


def _assistant_card(step: dict) -> str:
    txt = step.get("text", "") or ""
    stop = step.get("stop_reason") or ""
    if not txt and not stop:
        return ""
    badge = f'<span class="badge warn">{escape(stop)}</span>' if stop else ""
    return f"""
<div class="card assistant">
  <div class="kv">Step {step.get("step", "?")} · assistant {badge}</div>
  {f'<pre style="margin-top:0.5rem;">{escape(txt)}</pre>' if txt else ""}
</div>"""


def _assertion_block(assertion: dict) -> str:
    cls = "assertion pass" if assertion.get("passed") else "assertion fail"
    badge = '<span class="badge pass">PASS</span>' if assertion.get("passed") else '<span class="badge fail">FAIL</span>'
    name = escape(assertion.get("name", ""))
    channel = assertion.get("channel", "")
    detail = escape(assertion.get("detail", "") or "")
    return f"""
<div class="{cls}">
  {badge} <span class="tag">{escape(channel)}</span> {name}
  {f'<div class="kv" style="margin-top:0.25rem;">{detail}</div>' if detail else ""}
</div>"""


def _initial_screenshot(run_dir: Path) -> str:
    shots = sorted(run_dir.glob("shot_*.png"))
    if not shots:
        return ""
    return _img_data_uri(shots[0])


def render_run(run_dir: Path) -> Path:
    """Render ``run_dir/report.html`` and return its path."""
    run_dir = Path(run_dir)
    traj_path = run_dir / "trajectory.json"
    test_path = run_dir / "test_report.json"
    if not traj_path.exists():
        raise FileNotFoundError(f"no trajectory.json under {run_dir}")

    traj = json.loads(traj_path.read_text(encoding="utf-8"))
    test: dict[str, Any] | None = None
    if test_path.exists():
        test = json.loads(test_path.read_text(encoding="utf-8"))

    started = traj.get("started_at", "?")
    ended = traj.get("ended_at", "?")
    instruction = traj.get("instruction", "")
    status = traj.get("status", "?")
    final_text = traj.get("final_text", "") or ""

    is_test = test is not None
    if is_test:
        passed_overall = test.get("passed", False)
        head_badge = (
            '<span class="badge pass">PASS</span>' if passed_overall
            else '<span class="badge fail">FAIL</span>'
        )
        title = test["case"]["name"]
    else:
        head_badge = (
            '<span class="badge pass">completed</span>' if status == "completed"
            else f'<span class="badge warn">{escape(status)}</span>'
        )
        title = instruction

    cards = []
    for step in traj.get("steps", []):
        kind = step.get("kind")
        if kind == "action":
            cards.append(_action_card(step, run_dir))
        elif kind == "assistant":
            cards.append(_assistant_card(step))

    assertions_html = ""
    if is_test and test.get("assertions"):
        n_pass = sum(1 for a in test["assertions"] if a.get("passed"))
        n_total = len(test["assertions"])
        assertions_html = f"""
<h2>Assertions ({n_pass}/{n_total} passed)</h2>
{"".join(_assertion_block(a) for a in test["assertions"])}
"""

    initial_uri = _initial_screenshot(run_dir)

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CUA-Lark · {escape(title)}</title>
<style>{_CSS}</style>
</head>
<body>
<h1>CUA-Lark Run Report {head_badge}</h1>
<div class="meta">
  <strong>Title:</strong> {escape(title)}<br>
  <strong>Started:</strong> {escape(started)} &nbsp; <strong>Ended:</strong> {escape(ended)}<br>
  <strong>Run dir:</strong> <code>{escape(str(run_dir))}</code>
  {f'<br><strong>Final summary:</strong> {escape(final_text)}' if final_text else ''}
</div>

{assertions_html}

<h2>Initial state</h2>
{f'<img class="shot" src="{initial_uri}" alt="initial screenshot">' if initial_uri else '<div class="muted">no initial screenshot</div>'}

<h2>Trajectory ({len(cards)} cards)</h2>
{"".join(cards)}

</body></html>"""

    out = run_dir / "report.html"
    out.write_text(html, encoding="utf-8")
    return out


def render_index(runs_root: Path) -> Path:
    """Aggregate every report.html under ``runs_root`` into an index page."""
    runs_root = Path(runs_root)
    rows = []
    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        traj_path = run_dir / "trajectory.json"
        if not traj_path.exists():
            continue
        traj = json.loads(traj_path.read_text(encoding="utf-8"))
        test_path = run_dir / "test_report.json"
        title = traj.get("instruction", run_dir.name)
        status = traj.get("status", "?")
        if test_path.exists():
            test = json.loads(test_path.read_text(encoding="utf-8"))
            title = test["case"]["name"]
            passed = test.get("passed", False)
            badge = '<span class="badge pass">PASS</span>' if passed else '<span class="badge fail">FAIL</span>'
        else:
            badge = (
                '<span class="badge pass">completed</span>' if status == "completed"
                else f'<span class="badge warn">{escape(status)}</span>'
            )
        report_html = run_dir / "report.html"
        link = f"{run_dir.name}/report.html" if report_html.exists() else ""
        rows.append(f"""
<tr>
  <td>{escape(traj.get("started_at", ""))}</td>
  <td>{escape(title)}</td>
  <td>{badge}</td>
  <td>{f'<a href="{link}">open</a>' if link else '—'}</td>
</tr>""")

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CUA-Lark · runs index</title>
<style>{_CSS}
table {{ border-collapse: collapse; width: 100%; }}
th, td {{ text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #d0d7de; }}
th {{ background: #f6f8fa; font-size: 0.85rem; }}
</style>
</head>
<body>
<h1>CUA-Lark Runs</h1>
<div class="meta">{len(rows)} run(s) under <code>{escape(str(runs_root))}</code></div>
<table>
<thead><tr><th>started</th><th>title</th><th>status</th><th>report</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
</body></html>"""

    out = runs_root / "index.html"
    out.write_text(html, encoding="utf-8")
    return out
