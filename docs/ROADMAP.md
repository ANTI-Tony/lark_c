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

## M2 · Multi-step flows + verification  — week 3–4

- [ ] Testing DSL (YAML or Python decorator form) with `assert_visible`, `assert_text`, `assert_sent`.
- [ ] CDP client: connect to Feishu's Electron debug port, read DOM + a11y tree.
- [ ] Verifier: VLM semantic diff + CDP structured assertion.
- [ ] Three end-to-end IM test cases (send text, create group, search message).

## M3 · Multi-product coverage  — week 5

- [ ] Docs: create doc, insert heading + body, share link, assert content.
- [ ] Calendar: create event, invite attendees, assert on mini-calendar view.
- [ ] Two passing cases per product.

## M4 · Evaluation framework  — week 6

- [ ] Run-aggregator that batches test cases and summarizes metrics (success rate, step count, latency, token spend).
- [ ] HTML report with timeline screenshots + assertion pass/fail.
- [ ] Baseline comparison scaffolding (selector-based vs CUA).

## M5 · Differentiators  — week 7

- [ ] Self-heal: on executor failure, replan with a targeted "your last click missed, look again" prompt and retry.
- [ ] Cross-product chain: IM receives a Calendar invite → switch to Calendar → accept → switch back to IM → assert read state.
- [ ] UI-drift A/B: manually nudge a target button 20 px, re-run the same tests; report the delta between selector-based and CUA results.

## Submission week  — week 8

- [ ] 3–5 minute demo video.
- [ ] 15-minute pitch deck.
- [ ] Evaluation report with M4/M5 data.
- [ ] Final design doc polish + README install walkthrough.
