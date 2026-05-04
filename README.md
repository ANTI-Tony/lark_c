# CUA-Lark

**Vision-driven Computer-Use Agent for automated QA testing of the Feishu (Lark) desktop client.**

Submission to the *飞书 AI 校园竞赛 · 质量工程与智能测试* track. CUA-Lark operates the Feishu desktop app the way a real user does — it looks at the screen, decides what to do, clicks and types — and treats every interaction as a QA assertion.

## Why this approach

Traditional GUI automation breaks every time the UI changes. A vision-language agent reads the screen semantically, so a button moving or being renamed is no longer a test regression. CUA-Lark turns that robustness into a testing framework:

| Pillar | What it gives us |
|---|---|
| **Testing-DSL** | Write end-to-end tests with `assert_visible`, `assert_text`, `assert_sent` — not brittle selectors. |
| **Hybrid Grounding** | Claude vision decides *what* to do; Electron CDP reads the DOM/a11y tree for deterministic *assertions*. |
| **Self-Heal** | When the UI shifts, the model re-locates targets instead of failing. We measure this against selector-based baselines. |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                        CUA-Lark Agent                        │
│                                                              │
│  Perception   →   Planner   →   Executor   →   Verifier      │
│   (screen,         (Claude        (PyAutoGUI     (VLM + CDP  │
│    CDP a11y)        CoT)           hotkeys)       asserts)   │
│                         │                                    │
│                         ▼                                    │
│                    Trajectory  →  HTML / Markdown Report     │
└──────────────────────────────────────────────────────────────┘
```

- **Perception** — `mss`/PyAutoGUI screenshot, base64 to VLM; optional CDP over WebSocket to Feishu's Electron debug port for DOM/a11y.
- **Planner** — Claude Sonnet 4.6 Computer Use (`computer_20250124` beta tool). Returns actions with pixel coordinates.
- **Executor** — PyAutoGUI with macOS Retina scaling, failsafe corner abort, action throttling.
- **Verifier** — VLM semantic diff + CDP structured assertions + OCR fallback (planned M4).
- **Reporter** — Per-run trajectory (screenshots + JSON log) → HTML dashboard (planned M4).

## Milestones

| | Goal | Status |
|---|---|---|
| M1 | Screenshot → Claude → single-step click/type loop | done |
| M2 | DSL + CDP client + Verifier + 3 IM cases | code done, live-debug pending |
| M3 | Docs + Calendar coverage | next |
| M4 | Eval framework + HTML report | |
| M5 | Self-heal (via `zoom`) + cross-product chains | |

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full plan.

## Install

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set ANTHROPIC_API_KEY
```

### macOS permissions

PyAutoGUI needs two system grants. Without them, clicks will silently no-op.

1. `System Settings → Privacy & Security → Screen Recording` — add your terminal (Terminal / iTerm / VS Code).
2. `System Settings → Privacy & Security → Accessibility` — same terminal.

Restart the terminal after granting.

## Run

```bash
# One-shot instruction
python -m cua_lark.cli run "打开飞书,点击第一个聊天"

# Or run the Feishu hello-world example
python examples/hello_feishu.py

# Run the IM test suite (M2)
python -m cua_lark.cli test tests/feishu/im/

# Filter by tag, or skip CDP if Feishu was launched without --remote-debugging-port
python -m cua_lark.cli test tests/feishu/ --tag im --no-cdp
```

Every run writes a trajectory to `runs/<timestamp>/` (screenshots + `trajectory.json`,
plus `test_report.json` for test-mode runs).

### Enabling CDP-backed assertions

Launch Feishu with the Electron debug port exposed so the verifier can query
the DOM directly:

```bash
# macOS
open -a "Feishu" --args --remote-debugging-port=9222
```

Without that flag, CDP assertions fail with a clear message and the VLM
channel still works.

## Safety

- `PYAUTOGUI_FAILSAFE=1` — flicking the mouse to any screen corner aborts.
- Hard step cap (default 20) to prevent runaway loops.
- Actions are throttled; nothing goes through the pipeline faster than ~2 ops/sec.

## Prior art

- [UI-TARS-desktop](https://github.com/bytedance/UI-TARS-desktop) — we build in Python rather than fork its TS codebase; architecture inspiration only.
- [Anthropic Computer Use](https://docs.anthropic.com/en/docs/build-with-claude/computer-use) — we use the `computer_20250124` beta tool directly.
- [OSWorld](https://github.com/xlang-ai/OSWorld) — eval methodology reference for M4.

## Repo layout

```
cua-lark/
├── cua_lark/           # library
│   ├── perception.py   # screenshot + Retina scaling
│   ├── executor.py     # PyAutoGUI wrapper
│   ├── agent.py        # Claude Computer Use loop
│   ├── trajectory.py   # per-run artifact log
│   ├── cdp.py          # Electron debug-port client
│   ├── verifier.py     # VLM + CDP assertion engines
│   ├── dsl.py          # @cua_test decorator + TestContext
│   ├── runner.py       # discover / execute / report
│   └── cli.py          # `cua-lark run`, `cua-lark test`
├── examples/
│   └── hello_feishu.py
├── tests/feishu/im/    # M2 test cases
├── docs/
│   ├── DESIGN.md
│   └── ROADMAP.md
└── runs/               # per-run artifacts (gitignored)
```

## License

TBD — pending competition requirements.
