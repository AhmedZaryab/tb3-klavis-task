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

Checks (`tasks/gateway-tenant-onboarding`, branch `ticket/tb3-original-task/candidate-gateway-probe`):

| Check | Command | Result |
|---|---|---|
| Static checks | `for c in scripts/checks/check-*.sh; do bash $c tasks/gateway-tenant-onboarding; done` | 25/25 pass |
| Server tests | `pytest tools/opsgate/test_server.py` | 19 passed |
| Oracle | `harbor run -p tasks/gateway-tenant-onboarding --agent oracle --env docker --yes` | reward 1.0, 7/7; 55 requests over 7 sessions |
| Nop | `harbor run -p tasks/gateway-tenant-onboarding --agent nop --env docker --yes` | reward 0.0 |
| Cheat artifact | `cheat/solve.sh` run as the solution | reward 0.0 (forged file never collected) |

Two gate failures during bring-up, both fixed with tests: the oracle's tokenizer mishandled quoted names
(replaced with the standard library splitter), and the gateway wrote no state file until its first request,
which turned a do-nothing agent into a verifier error.

Feasibility probe (2 h cap):

| Agent | Model | Effort | Reward | Time | Notes |
|---|---|---|---|---|---|
| claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 4 min 13 s | 38 tool calls; read HELP for every verb, paged the tool list, onboarded all three tenants without tripping the guard |

Verdict: the feasibility version is a reading task, not a discovery task. HELP spelled out every rule
(budget size, loop-guard threshold, resume semantics, commit ordering, what FINISH checks), so nothing had
to be learned by interacting. The pipeline (sidecar gateway, collect hook, sealed verifier) works and is
kept; the next revision makes the help terse like real legacy help, keeps every error truthful, and adds
state that only shows itself over a sequence of requests.

### Hardened revision (branch `ticket/tb3-original-task/candidate-gateway-hardening`)

Changes: HELP lists verbs, syntax and error codes only; errors are short and truthful; a commit is queued and
applies at the start of the next request in its session chain; FINISH freezes a tenant and REOPEN unfreezes
it; budget 25 per session; eight tenants to onboard.

| Check | Result |
|---|---|
| Static checks | 25/25 pass |
| Server tests (`pytest tools/opsgate/test_server.py`) | 39 passed |
| Oracle | reward 1.0, 12/12; 203 requests over 9 sessions |
| Nop | reward 0.0 |
| Cheat artifact | reward 0.0 |

Feasibility probe (2 h cap):

| Agent | Model | Effort | Reward | Time | Notes |
|---|---|---|---|---|---|
| claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 6 min 2 s | 96 tool calls; probed STATUS after each step, learned the queued-then-applied rule and the freeze, never retried, no duplicates |

Verdict: a truthful interactive system with a stated goal is learned by this model in minutes, even with
terse help. Making it harder from here would mean lying in the help or hiding state from STATUS, which the
rubric forbids. The gateway line of design is closed; the package stays as the record.

## Candidate 4: gateway-metering-forensics (in progress)

A week of an agent gateway's billing ledger disagrees with its policy because of five metering defects
that overlap on the same requests. The agent must produce the corrected ledger and identify the distinct
defects with the requests each one affected. The defect list is graded on count and on each affected set,
up to relabeling. Chosen because it is the one pattern in the candidate survey with a clean 6/6 win against
both agents that had not been tried: a judgment that recomputation cannot confirm.

Checks (`tasks/gateway-metering-forensics`, branch `ticket/tb3-original-task/candidate-forensics-task`):

| Check | Result |
|---|---|
| Static checks | 25/25 pass |
| Docker build | environment and verifier images build; the verifier regenerates the truth from the seed |
| Oracle | reward 1.0, 14/14 |
| Nop | reward 0.0 |
| Cheat artifact (legacy ledger copied, one catch-all defect) | reward 0.0, 13/14 fail |

Data: 121,001 requests, 8.5% affected by at least one defect (D1 2,050, D2 1,956, D3 1,570, D4 2,003,
D5 3,431), 291 by exactly two, 212 by three.

Feasibility probe: pending.
