# tb3-klavis-task

One original [Terminal-Bench 3](https://github.com/harbor-framework/terminal-bench) task.

- `tasks/` — the task candidates, each a complete TB3 task package
- `tools/` — the tooling used to build, calibrate and probe them
- `RESULTS.md` — the research log: the method once (question, hypothesis rule, controls, measures, kill test), then every candidate under the same headings, then status against the brief and next steps

The git history follows the same loop: one branch per candidate, commit prefixes `prepare`, `impl`, `test`, `fix`, `verify`, `docs(epic)`, `merge` map to its steps (see section 1.7 of `RESULTS.md`).

## Status

| Candidate | Task | Outcome |
|---|---|---|
| 1 | `batch-tool-dispatch` | all CI gates green; the brief's trial matrix runs on it: Claude Opus 5.5 3/3 genuine passes |
| 2 | `mcp-tool-index` | reference index cannot reach a fair bar (47.7% vs 92%); shelved |
| 3 | `gateway-tenant-onboarding` | all CI gates green; solved by Claude Opus 5.5 in 4 min, hardened version in 6 min; retired |
| 4 | `gateway-metering-forensics` | all CI gates green; solved by Claude Opus 5.5 in 6 min; retired |
| 5 | `support-desk-gateway` | built from the official per-task leaderboard data; all CI gates green; solved by Claude Opus 5.5 in 9 min through 266 native MCP tools; retired |
