# Roadmap

Solo build, roughly eight weeks from repo init to final submission.

## M1 · Single-step loop  — week 1–2  (this milestone)

- [x] Project scaffolding, README, design doc.
- [x] Perception module with Retina scaling.
- [x] Executor with click / double-click / type / key / scroll / drag.
- [x] Claude Computer Use agent loop with full message history.
- [x] Per-run trajectory log.
- [x] CLI: `cua-lark run "..."`.
- [x] Example: open Feishu, click a chat, type a message.

**Exit criterion:** agent can perform ≥5 single-step actions on the live Feishu client from natural-language instructions.

## M2 · Multi-step flows + verification  — week 3–4  (in progress)

- [x] Testing DSL: Python decorator form with `assert_visible`, `assert_dom_text`, `assert_dom_any`.
- [x] CDP client: synchronous JSON-RPC client over Electron debug websocket.
- [x] Verifier: `VlmVerifier` (Claude semantic check) + `CdpVerifier` (DOM text queries).
- [x] Test runner with structured `test_report.json` per run + Rich summary table.
- [x] Three IM test cases authored against the DSL (`tests/feishu/im/im_basic.py`).
- [ ] Live debug pass against the running Feishu client (depends on local environment).

## M3 · Multi-product coverage  — week 5

- [ ] Docs: create doc, insert heading + body, share link, assert content.
- [ ] Calendar: create event, invite attendees, assert on mini-calendar view.
- [ ] Two passing cases per product.

## M4 · Evaluation framework  — week 6  (in progress)

- [x] Self-contained HTML report per run — screenshots inlined as data URIs, no external assets.
- [x] Aggregate index page (`runs/index.html`) over all runs.
- [x] `cua-lark report <path>` CLI subcommand.
- [ ] Metrics dashboard: success rate, step count, latency, token spend (next).
- [ ] Baseline comparison scaffolding (selector-based vs CUA).

## M5 · Differentiators  — week 7  (in progress)

- [x] Self-heal v1: enable Sonnet 4.6's `zoom` action; system prompt steers the model to zoom rather than low-confidence click.
- [x] Agent-side `_handle_zoom` crops to the requested region and returns it as the tool_result image.
- [ ] Self-heal v2: on executor failure, automatically replan with a "last action missed, re-look" prompt.
- [ ] Cross-product chain: IM receives a Calendar invite → switch to Calendar → accept → switch back to IM → assert read state.
- [ ] UI-drift A/B: manually nudge a target button 20 px, re-run the same tests; report the delta between selector-based and CUA results.

## Submission week  — week 8

- [ ] 3–5 minute demo video.
- [ ] 15-minute pitch deck.
- [ ] Evaluation report with M4/M5 data.
- [ ] Final design doc polish + README install walkthrough.
