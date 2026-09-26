# Results

One original Terminal-Bench 3 task, built to the current TB3 CI and tested against the agents named in
the brief. This file records every candidate design in the order it was tried, the checks and trials run
against it, and why it was kept or retired. Raw harbor output lives under `runs/` (not committed).

Environment: harbor 0.23.0, Docker Desktop 29.8.0 on macOS (arm64, 18 cores, 16 GB for Docker),
terminal-bench main at `4def1f3` (2026-09-23) for the static checks and rubric.

Agents required by the brief: `claude-code` on `anthropic/claude-opus-5-5` with `reasoning_effort=max`,
`codex` on `openai/gpt-6-sol` with `reasoning_effort=xhigh`. The live TB3 CI defaults moved to
`anthropic/claude-fable-5-1` and `openai/gpt-6-astra` on 2026-09-21; those are run as additional evidence
once the required matrix is complete.

## Candidate 1: batch-tool-dispatch (retired)

Plan a nightly batch of up to 20,000 tool calls onto rate-limited MCP servers at exact minimum cost. The
insight is that the capped token bucket relaxes exactly into a min-cost flow.

Checks (`tasks/batch-tool-dispatch`, branch `ticket/tb3-original-task/task-scaffold`, PR #2):

| Check | Command | Result |
|---|---|---|
| Static checks | `for c in scripts/checks/check-*.sh; do bash $c tasks/batch-tool-dispatch; done` | 25/25 pass |
| Docker build | `docker build environment/`, `docker build tests/` | 21 s, 86 s |
| Oracle | `harbor run -p tasks/batch-tool-dispatch --agent oracle --env docker --yes` | reward 1.0, 20/20 |
| Nop | `harbor run -p tasks/batch-tool-dispatch --agent nop --env docker --yes` | reward 0.0 |
| Cheat artifact | `cheat/solve.sh` run as the solution | reward 0.0 |

Kill test 1 (does a generic LP solver reach the optimum with no modelling insight?): the natural LP is
integral but does not scale: 0.6 s at 200 calls, 23.8 s at 600, over 300 s at 1,500, over 49 min at 4,000,
against under 1 s for the flow solver at 20,000. Passed.

Kill test 2 (clean-room agent run, 2 h cap):

| Agent | Model | Effort | Reward | Time | Notes |
|---|---|---|---|---|---|
| claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 71 min | flow model stated at minute 11; planner written at minute 10; done at minute 35, then built a C++ solver it did not need |

Retired: the insight is textbook for this model. The package stays as the record; the required trial matrix
was not run on it because the design does not meet the failure bar.

## Candidate 2: mcp-tool-index (shelved)

Write a compressed index of 242 MCP tools so a fixed router routes hand-written requests under a token
budget. Branches `candidate-strata-index` and `task-tool-index`, PR #3.

Calibration of the reference index against 260 drafted requests: 30.4% with the catalog-only builder and a
greedy router; 37.3% with product vocabulary; 47.7% with a beam-2 path-scored router, against a 92% bar.
BM25 over summaries this short rewards whichever rare noun a request contains. Reaching the bar would mean
tuning the reference to the request wording, which is the overfitting the task is meant to punish.

Shelved on solvable-and-fair grounds before any agent trial.

## Candidate 3: gateway-tenant-onboarding (in progress)

Operate a legacy tool gateway that speaks its own protocol, with staged commits, idempotency keys, session
budgets and a loop guard, to onboard three tenants. Grading reads the gateway's committed state after the
agent's container is gone. Chosen after a second research round on documented frontier-model weaknesses:
learning an unfamiliar stateful system by interaction, and harness sensitivity, are the failure modes with
the strongest evidence that survive a self-verifying agent.

Feasibility probe and gates: pending.
