# CUA-Lark Design

## 1. Problem statement

Automated QA for the Feishu desktop client is today a brittle pursuit: tests bind to DOM selectors or accessibility IDs that change every sprint. CUA-Lark swaps that for a vision-language agent that reads the screen semantically and acts like a human tester. The goal is not to build yet another screen-recording bot — it is to reframe GUI QA around **assertions a human could make by eye**.

## 2. Architecture

Five layers, each with a narrow job:

### 2.1 Perception

- Primary: full-screen screenshot via `mss` (fast) or PyAutoGUI. Encoded to PNG, base64'd for VLM input.
- Retina handling: on macOS the physical screenshot is 2× the logical resolution; we pass the physical dimensions to Claude and divide click coordinates by the same factor before feeding them to PyAutoGUI.
- Optional (M2+): Chrome DevTools Protocol over WebSocket to Feishu's Electron debug port, exposing DOM + a11y tree.

### 2.2 Planner

- Claude Sonnet 4.6 with the `computer_20250124` beta tool and the `computer-use-2025-01-24` beta header.
- Stateful conversation: we keep the full message history so Claude retains context between tool calls.
- The model decides when it is finished by responding with `stop_reason == "end_turn"` (no further tool_use blocks).

### 2.3 Executor

- PyAutoGUI for click, double-click, right-click, drag, type, key, scroll, move.
- `pyautogui.FAILSAFE = True` — flicking the mouse to any screen corner aborts.
- Coordinate scaling is centralized in one `Executor` so the rest of the system can work in physical (Claude-space) pixels.
- Key-combo parser translates `cmd+c`, `ctrl+shift+t`, etc. into PyAutoGUI hotkeys.

### 2.4 Verifier  (M4)

Three complementary channels:

1. **VLM semantic diff** — before/after screenshots plus an assertion prompt ("did a new message appear?").
2. **CDP structured assertion** — read Feishu's DOM/a11y via CDP and check text/attributes. Deterministic, fast, survives visual noise.
3. **OCR fallback** — Tesseract / RapidOCR for when CDP is unavailable (e.g., system dialogs outside Feishu).

A single assertion can use any subset; the DSL selects the cheapest one that is sufficient.

### 2.5 Reporter  (M4)

Per-run artifacts under `runs/<timestamp>/`:
- `trajectory.json` — ordered list of `{step, action, screenshot_path, latency_ms, ...}`.
- `step_00.png`, `step_01.png`, ... — before/after snapshots.
- `report.html` (M4) — side-by-side screenshot timeline + assertion results.

## 3. Key design decisions

### Python over TypeScript

Faster iteration for solo work, richer VLM ecosystem, PyAutoGUI is mature, and CDP can be driven from Python just fine via `websockets`. UI-TARS-desktop is TS/Electron — we reference its architecture but do not fork it.

### Claude Computer Use over custom grounding

Claude's Computer Use API returns pixel coordinates directly. This removes an entire class of bug ("click predictor says button is at (x, y) but screenshot-to-action pipeline is off by a half-pixel"). We lose the ability to run fully offline, but we gain a single, simple loop.

### Hybrid grounding (Vision + CDP)

Pure vision is robust to UI change but non-deterministic on assertions — two pixels difference between runs can flip a naive pixel-diff. Pure DOM/a11y is brittle but exact. We use vision for **decisions** and CDP for **assertions**. Both sides can cross-check the other for self-healing.

### No fork of UI-TARS-desktop

Judges score originality. A thin wrapper over a TS Electron app would be indistinguishable from a weekend hack. Building the Python stack from first principles gives us room to innovate on the test DSL, the report, and the hybrid grounding — the things that actually matter for QA.

## 4. Module map

| File | Responsibility |
|---|---|
| `cua_lark/perception.py` | Screenshot, base64 encoding, display info. |
| `cua_lark/executor.py` | PyAutoGUI action wrapper with scaling + key mapping. |
| `cua_lark/agent.py` | Claude Computer Use loop — orchestrates Perception + Planner + Executor. |
| `cua_lark/trajectory.py` | Per-run artifact logging. |
| `cua_lark/cli.py` | `cua-lark run "..."` entry point. |
| `examples/hello_feishu.py` | Smoke test against the Feishu client. |

## 5. Data flow (one step)

```
user instruction ──┐
                   ▼
           ┌───────────────┐
           │  Agent loop   │
           └──────┬────────┘
                  │ 1. screenshot()
                  ▼
           ┌───────────────┐
           │  Perception   │  (PNG bytes, dims)
           └──────┬────────┘
                  │ 2. messages.create(image + instruction)
                  ▼
           ┌───────────────┐
           │    Claude     │  tool_use blocks: {action, coordinate, text}
           └──────┬────────┘
                  │ 3. dispatch
                  ▼
           ┌───────────────┐
           │   Executor    │  PyAutoGUI → OS
           └──────┬────────┘
                  │ 4. screenshot() again, append tool_result
                  ▼
               loop until end_turn
```

## 6. Non-goals (for now)

- Mobile Feishu. Desktop only.
- Running unattended in CI. M5 may explore a headless VNC setup, but the primary deliverable is attended, developer-machine testing.
- Training a new grounding model. We use the Claude API and optionally UI-TARS as a comparison baseline.
