# Results

One original Terminal-Bench 3 task, built to the current TB3 CI and tested against the agents named in
the brief. This file is written as a research log. Section 1 states the method once: the question, how the
prediction is written down, what is held fixed, what is measured, how runs are analysed, and the rule for
iterating. Sections 2 to 6 apply that method to each of the five candidate designs in the order they were
tried, every one under the same headings, with the commits that hold each step. Section 7 is the
hypothesis for candidate 6, recorded before its build; section 8 the analysis across candidates; section 9
the status against the brief; section 10 the next steps in loop order. Raw harbor output lives under
`runs/` (not committed).

## 1. Method

### 1.1 Question

Can the two agents named in the brief, `claude-code` on `anthropic/claude-opus-5-5` at `reasoning_effort=max`
and `codex` on `openai/gpt-6-sol` at `reasoning_effort=xhigh`, solve a fair, CI-clean TB3 task in the
agent-gateway domain? The brief needs a task that both fail three times out of three and cannot cheat. The
live TB3 CI defaults moved to `anthropic/claude-fable-5-1` and `openai/gpt-6-astra` on 2026-09-21; those are
run as additional evidence once the required matrix is complete.

### 1.2 Prediction, and how it is written down

Each candidate begins with a written hypothesis: the documented model weakness it targets, why the design
should defeat the model, and what result would prove the hypothesis wrong. It is recorded before the build,
either in a decision-record commit on the epic branch or in the candidate's `prepare` commit (the README's
Difficulty paragraph), and it is repeated under "Hypothesis" in the candidate's section below with the
commit that holds it. The falsifier is the same for every candidate: the kill test.

Kill test: one clean-room run of `claude-code` on `claude-opus-5-5` at `max`, with a 2 h agent cap (a quarter
of the 8 h task timeout), before any 8 h trial is spent. Reward 1.0 means the hypothesis is false and the
candidate is retired. One hardening revision is allowed when the transcript names a specific, fixable reason;
if the hardened version is also solved, the design line is closed. Only a candidate that survives the kill
test earns the six-trial matrix. Claude goes first because it is the stronger agent on the public leaderboard
(section 8.3): a candidate Claude solves cannot meet the brief whatever codex does.

### 1.3 Controls: what is held fixed

- Harness: harbor 0.23.0, Docker Desktop 29.8.0 on macOS arm64 (18 cores, 16 GB for Docker),
  terminal-bench main at `4def1f3` (2026-09-23) for the static checks and rubric.
- Agent configuration: one runner, `tools/run-trial.sh`, applies the same flags to every run: the brief's
  model and effort, subscription auth (`CLAUDE_FORCE_OAUTH`, `CODEX_FORCE_AUTH_JSON`),
  `CLAUDE_CODE_NO_MODEL_FALLBACK=1` so no fallback model can answer for the one under test, one trial at a
  time, machine kept awake, token redacted from every saved log.
- Task: once a candidate's gates pass, its instruction, environment image, verifier and hidden data are
  frozen; every trial of that candidate sees the same task. Agent code never runs as root. The verifier runs
  after the agent's container is gone and reads state the agent cannot reach.
- Gates, passed before any agent sees the task: 25 static checks, both Docker images build, oracle (the
  reference solution) scores 1.0, nop (an agent that does nothing) scores 0.0, the cheat artifact scores 0.0.
  The oracle is the positive control (the task is solvable), nop and cheat are the negative controls (the
  task is not free and the verifier cannot be gamed).
- Independent variable: the agent and its model. Nothing else changes between trials.
- Exclusion rule, from the brief: a crash, timeout, rate limit or container failure is an invalid trial. It
  is recorded and rerun, never counted as a pass or a fail. None occurred in this work.

### 1.4 What is measured

Per trial: reward from the verifier's CTRF file (1.0 or 0.0, with the pass count), wall-clock agent time,
number of tool calls, errors, and for probes the minute at which the transcript first states the key idea.
Per candidate: the gate results and the data sizes.

### 1.5 How runs are analysed

Every transcript is read, not only scored. For each run: what the model read first, when it stated its model
of the problem, whether its call pattern matched the reference solution, whether it hit any trap the design
set (wrong tool, retry storm, budget, irreversible mistake), and what it did after it believed it was done.
A pass is analysed as carefully as a fail, because the pass is what falsifies the hypothesis.

### 1.6 Iteration rule

Retire or shelve, write the reason in one paragraph, name the one axis the next design changes, then build.
The decision record is committed before the next `prepare` commit, so the order is auditable in the history.

### 1.7 How the loop shows in the git history

One branch per candidate under `ticket/tb3-original-task/`, merged into `epic/tb3-original-task`, merged
into `main`. Commit prefixes map to loop steps:

| Prefix | Loop step | What the commit holds |
|---|---|---|
| `prepare` | hypothesis, task statement | instruction, task.toml, README with the Difficulty rationale |
| `impl` | build | environment, reference solution, verifier, cheat artifact, tooling |
| `test` | build, held to the truth | test suites for the verifier, oracle and any sidecar |
| `fix` | iterate inside the build | one gate or review finding, fixed with its regression test |
| `verify` | measure | a gate result or a trial result; the subject line carries the number |
| `docs(epic)` | analyse, decide | trial records, analysis, and the decision record that opens the next candidate |
| `merge` | close one turn of the loop | the subject line states the outcome |

Timeline: candidate 1 and its fallback (candidate 2) on 2026-09-25 evening; the pivot record, candidates 3
and 4, the Claude half of the matrix, the leaderboard study and candidate 5 on 2026-09-26.

## 2. Candidate 1: batch-tool-dispatch (retired)

### Hypothesis

Recorded in `87d944c` (problem and checker) and `f1343c0` (instruction), 2026-09-25, before any agent run.
Weakness targeted: algorithmic modelling insight under an exactness requirement. The task: plan a nightly
batch of up to 20,000 tool calls onto rate-limited MCP servers at exact minimum cost. The insight is that the
capped token bucket relaxes exactly into a min-cost flow. Prediction: the model reaches for a generic LP or a
greedy heuristic, and neither produces the exact optimum at 20,000 calls inside the timeout. Falsifiers:
kill test 1 (a generic LP scales, so the insight is not needed) or kill test 2 (the model finds the flow).

### Build

Branch `ticket/tb3-original-task/task-scaffold`, PR #2. Seeded instance generator and greedy baseline
(`676b977`), exact planner as a time-expanded min-cost flow (`52bd5bb`), independent CBC cross-check and 47
checker and solver tests (`85ca40a`), agent image with five example batches (`64d38ac`), sealed verifier with
hidden instances and unprivileged runs (`331bf77`), reference solution and poisoned-artifact cheat oracle
(`b371b66`), one-command trial runner (`db0c0e1`).

### Controls

| Check | Command | Result |
|---|---|---|
| Static checks | `for c in scripts/checks/check-*.sh; do bash $c tasks/batch-tool-dispatch; done` | 25/25 pass |
| Docker build | `docker build environment/`, `docker build tests/` | 21 s, 86 s |
| Oracle | `harbor run -p tasks/batch-tool-dispatch --agent oracle --env docker --yes` | reward 1.0, 20/20 |
| Nop | `harbor run -p tasks/batch-tool-dispatch --agent nop --env docker --yes` | reward 0.0 |
| Cheat artifact | `cheat/solve.sh` run as the solution | reward 0.0 |

Recorded in `fdec5db`.

### Trials

Kill test 1 (`cea0627`): does a generic LP solver reach the optimum with no modelling insight? The natural
LP is integral but does not scale: 0.6 s at 200 calls, 23.8 s at 600, over 300 s at 1,500, over 49 min at
4,000, against under 1 s for the flow solver at 20,000. The hypothesis survived this test.

Kill test 2 (`7ec12ba`), clean-room agent run, 2 h cap:

| Agent | Model | Effort | Reward | Time | Notes |
|---|---|---|---|---|---|
| claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 71 min | flow model stated at minute 11; planner written by minute 10; done at minute 35, then built a C++ solver it did not need |

Required trials, run on this candidate because no later candidate survived its kill test either, so the
brief's matrix has a real record (`tools/run-trial.sh`, full 8 h agent timeout, subscription auth;
`698af5e`, `ddadec1`, `b933def`):

| # | Agent | Model | Effort | Reward | Time | Tool calls | Errors | Job |
|---|---|---|---|---|---|---|---|---|
| 1 | claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 99 min | 82 | none | `runs/run-dispatch-claude-1` |
| 2 | claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 39 min | 52 | none | `runs/run-dispatch-claude-2` |
| 3 | claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 92 min | 96 | none | `runs/run-dispatch-claude-3` |

Additional evidence on the live CI default (`974dd7a`, not required by the brief):

| Agent | Model | Effort | Reward | Time | Tool calls | Errors | Job |
|---|---|---|---|---|---|---|---|
| claude-code | anthropic/claude-fable-5-1 | max | 1.0 | 113 min | 59 | none | `runs/run-dispatch-fable-1` |

Adversarial trial (`8c06bf6`; the CI's `docs/prompts/hack-trial-prompt.md` appended to the instruction):

| Agent | Model | Effort | Reward | Time | Tool calls | What it did |
|---|---|---|---|---|---|---|
| claude-code | anthropic/claude-opus-5-5 | max | 0.0 | 1 min | 3 | enumerated /app, /logs and the checker; found no leaked answers, no writable grader state and no way to fake the exact-minimum check; reported "no credible bypass" and left no planner. It noted that a safety classifier cut off one probe; the report was still completed. |

Codex trials on this candidate: not yet run (section 9).

### Measurements

Five Claude runs, five rewards of 1.0, 39 to 113 minutes, 52 to 96 tool calls, zero errors, zero invalid
trials. Adversarial run 0.0 in one minute.

### Analysis

The prediction was that the model would not find the flow. It found it in eleven minutes, before writing
any solver, and never tried the LP or the greedy path the design expected. The rest of each run was
self-verification: independent checkers, a cross-check against its own second implementation, and in the
kill test an unneeded C++ port. Time varies threefold between runs but the outcome does not. The insight is
textbook for a model trained on operations research. The adversarial run confirms the verifier design: the
sealed hidden instances and the exact-minimum check gave it nothing to attack.

### Decision and next step

Retired as a difficulty candidate; the package stays as the record and carries the matrix. Axis changed for
the next design: from an offline algorithmic insight, which a well-read model already holds, to knowledge
that must be learned by interacting with a stateful system (decision record `09d4ff0`).

## 3. Candidate 2: mcp-tool-index (shelved)

### Hypothesis

Recorded in `12a86e7` and `b485723`, 2026-09-25, built in parallel with candidate 1 as the fallback design.
Weakness targeted: compression under a fixed lexical router. The task: write a compressed index of 242 MCP
tools so a fixed router routes hand-written requests under a token budget. Prediction: the model optimises
for the wrong signal and the router misroutes. Falsifier: the reference index fails to reach the bar, which
would make the task unfair before it is hard.

### Build

Branches `candidate-strata-index` and `task-tool-index`, PR #3. MCP tool catalog, fixed router, scorer and
tests (`b485723`), beam-2 path-scored router with the same token accounting (`a0aa831`), task scaffold
(`db11e56`).

### Controls

The positive control failed. Calibration of the reference index against 260 drafted requests: 30.4% with the
catalog-only builder and a greedy router, 37.3% with product vocabulary, 47.7% with a beam-2 path-scored
router, against a 92% bar (`ee5ad1d`).

### Trials

None. A task whose own reference cannot pass is not put in front of an agent.

### Measurements

Three reference variants, best 47.7% against 92%.

### Analysis

BM25 over summaries this short rewards whichever rare noun a request contains. Reaching the bar would mean
tuning the reference to the request wording, which is exactly the overfitting the task was meant to punish.

### Decision and next step

Shelved on solvable-and-fair grounds. Lesson kept for every later candidate: the oracle control is run and
passed before any agent hour is spent.

## 4. Candidate 3: gateway-tenant-onboarding (retired)

### Hypothesis

Decision record `09d4ff0`, 2026-09-26 09:26, committed before the first build commit `f416333` at 09:46.
Weakness targeted, from a second research round on documented frontier-model weaknesses: learning an
unfamiliar stateful system by interaction, and harness sensitivity, the two failure modes with the strongest
evidence that survive a self-verifying agent. The task: operate a legacy tool gateway that speaks its own
protocol, with staged commits, idempotency keys, session budgets and a loop guard, to onboard tenants;
grading reads the gateway's committed state after the agent's container is gone. Prediction: the model
trips the loop guard or exhausts a session budget before it has learned the commit semantics. Falsifier:
the kill test.

### Build

Branch `ticket/tb3-original-task/candidate-gateway-probe`. Opsgate service, thin client and compose
environment (`caad85f`), verifier over collected state, oracle and cheat (`62c65fa`), server suite of
nineteen tests, three of them from gate failures (`a632c94`), trial runner takes the task path (`319a434`).

### Controls

| Check | Command | Result |
|---|---|---|
| Static checks | `for c in scripts/checks/check-*.sh; do bash $c tasks/gateway-tenant-onboarding; done` | 25/25 pass |
| Server tests | `pytest tools/opsgate/test_server.py` | 19 passed |
| Oracle | `harbor run -p tasks/gateway-tenant-onboarding --agent oracle --env docker --yes` | reward 1.0, 7/7; 55 requests over 7 sessions |
| Nop | `harbor run -p tasks/gateway-tenant-onboarding --agent nop --env docker --yes` | reward 0.0 |
| Cheat artifact | `cheat/solve.sh` run as the solution | reward 0.0 (forged file never collected) |

Recorded in `91759d3`. Two gate failures during bring-up, both fixed with tests: the oracle's tokenizer
mishandled quoted names (replaced with the standard library splitter), and the gateway wrote no state file
until its first request, which turned a do-nothing agent into a verifier error instead of a clean 0.0.

### Trials

Kill test (`8e3641a`), 2 h cap:

| Agent | Model | Effort | Reward | Time | Notes |
|---|---|---|---|---|---|
| claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 4 min 13 s | 38 tool calls; read HELP for every verb, paged the tool list, onboarded all three tenants without tripping the guard |

### Measurements

Reward 1.0 in 4 min 13 s, 38 tool calls, no errors, guard never tripped, no duplicate requests.

### Analysis

The feasibility version was a reading task, not a discovery task. HELP spelled out every rule (budget size,
loop-guard threshold, resume semantics, commit ordering, what FINISH checks), so nothing had to be learned by
interacting. The pipeline itself (sidecar gateway, collect hook, sealed verifier) worked and was kept.

### Iteration inside the candidate: hardened revision

The transcript named a specific, fixable reason (the help gave everything away), so the one hardening
revision allowed by the method was spent. Branch `ticket/tb3-original-task/candidate-gateway-hardening`.
Changes (`90c5d20`, `122e473`): HELP lists verbs, syntax and error codes only; errors are short and truthful;
a commit is queued and applies at the start of the next request in its session chain; FINISH freezes a tenant
and REOPEN unfreezes it; budget 25 per session; eight tenants to onboard. Thirty-nine server tests
(`07f485c`).

| Check | Result |
|---|---|
| Static checks | 25/25 pass |
| Server tests (`pytest tools/opsgate/test_server.py`) | 39 passed |
| Oracle | reward 1.0, 12/12; 203 requests over 9 sessions |
| Nop | reward 0.0 |
| Cheat artifact | reward 0.0 |

Recorded in `9a10326`. Kill test on the hardened version (`c6e7c9a`), 2 h cap:

| Agent | Model | Effort | Reward | Time | Notes |
|---|---|---|---|---|---|
| claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 6 min 2 s | 96 tool calls; probed STATUS after each step, learned the queued-then-applied rule and the freeze, never retried, no duplicates |

Hardening added two minutes and 58 tool calls. The model replaced reading the help with probing STATUS after
every step, which is the correct scientific behaviour and cost it almost nothing.

### Decision and next step

A truthful interactive system with a stated goal is learned by this model in minutes, even with terse help.
Making it harder from here would mean lying in the help or hiding state from STATUS, which the rubric
forbids. The gateway line is closed; the package stays as the record. Axis changed for the next design: from
learning by interaction to a judgment that recomputation cannot confirm.

## 5. Candidate 4: gateway-metering-forensics (retired)

### Hypothesis

Recorded in the prepare commit `e1e6651` (README Difficulty paragraph), 2026-09-26 10:39, twenty minutes
after candidate 3 closed and before the build commits. Weakness targeted: a judgment that recomputation
cannot confirm, the one pattern in the candidate survey with a clean 6/6 win against both agents that had not
been tried. The task: a week of an agent gateway's billing ledger disagrees with its policy because of five
metering defects that overlap on the same requests; produce the corrected ledger and identify the distinct
defects with the requests each one affected, graded on count and on each affected set up to relabeling.
Prediction: the model corrects the ledger but merges or splits the overlapping defects, because how many
distinct causes explain a diff is a judgment, not a computation. Falsifier: the kill test.

### Build

Branch `ticket/tb3-original-task/candidate-forensics-task`. Seeded generator with five overlapping metering
defects (`ea3e92b`), policy, week of traffic, legacy ledger and agent image (`60525d5`), sealed verifier,
honest oracle and cheat artifact (`1e4b379`).

### Controls

| Check | Result |
|---|---|
| Static checks | 25/25 pass |
| Docker build | environment and verifier images build; the verifier regenerates the truth from the seed |
| Oracle | reward 1.0, 14/14 |
| Nop | reward 0.0 |
| Cheat artifact (legacy ledger copied, one catch-all defect) | reward 0.0, 13/14 fail |

Recorded in `acbd107`. Data: 121,001 requests, 8.5% affected by at least one defect (D1 2,050, D2 1,956,
D3 1,570, D4 2,003, D5 3,431), 291 by exactly two, 212 by three.

### Trials

Kill test (`6c2d5be`), 2 h cap:

| Agent | Model | Effort | Reward | Time | Notes |
|---|---|---|---|---|---|
| claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 6 min 16 s | 20 tool calls; recomputed the ledger, diffed, and reported exactly five defects with the exact affected sets |

### Measurements

Reward 1.0 in 6 min 16 s, 20 tool calls, exact defect count and exact affected sets.

### Analysis

With every policy rule stated, each defect is a clean single-rule deviation and the grouping is mechanical,
not a judgment. The pattern that beat earlier models in the survey relied on mechanisms that no stated rule
pins down, and that is the kind of hidden rule the rubric forbids. The prediction failed at the design
level: a fair version of "judgment" collapses into recomputation.

### Decision and next step

Retired. This closed the first design search: four candidates, each passing every CI gate, each solved by
Claude Opus 5.5 at max reasoning in 4 to 71 minutes, and the required matrix run on candidate 1. Before a
fifth design, the analysis was checked against the official per-task leaderboard data instead of published
reports (section 8.3), and the axis changed to: irreversible live state, information that arrives in waves,
many interacting rules, lifecycle grading, all behind a wide tool surface (decision record `54dd9eb`).

## 6. Candidate 5: support-desk-gateway (retired)

### Hypothesis

Decision record `54dd9eb`, 2026-09-26 17:59, committed before the first build commit `f4e7f43` at 18:10.
Two inputs. First, the official per-task data (section 8.3): the ten tasks that defeat every frontier pair
share one shape, state that changes under the agent and cannot be undone, information that arrives over
time, many small interacting rules, all-or-nothing lifecycle grading. Second, the author's production
experience with an agent gateway: with a few hundred tools behind one aggregator key, agents picked
look-alike tools, made thirty or more calls where two or three were needed, retried straight into rate
limits, and went down wrong paths that a fresh context would not have taken; runaway protection had to be
added to the gateway. None of the first four candidates reproduced that setting: they gave the model a
terminal and a file, not a tool surface.

The task: a support desk's refund escalations, worked through one company tool gateway that Harbor
registers with the agent as an MCP server. About 250 tools across some 20 services with deprecated, sandbox
and legacy look-alikes described honestly, a rate limit with retry-after on billing, a call budget that ends
the run when spent; refunds and messages cannot be undone, follow-ups arrive as earlier cases are resolved,
a dozen stated rules interact, and the verifier grades the whole lifecycle from the gateway's own ledger.
Everything is stated in the runbook; nothing is hidden except the expected end state, which the verifier
computes from the same seed. Prediction: the tools are a multiplier and the state machine is the
difficulty, so the model makes at least one irreversible wrong action (wrong tool, duplicate refund, wrong
proration, missed follow-up) and the all-or-nothing verifier scores it 0. Falsifier: the kill test.

### Build

Branch `ticket/tb3-original-task/candidate-support-desk-task`. Gateway sidecar serving 266 tools over MCP
(33 on the desk's path), seed and runbook (`84bd9fe`); sealed verifier, honest oracle and cheat artifact
(`6a7c5dd`); thirteen gateway tests, rules cross-check, seed copies (`990564b`). Twelve escalations wait in
the queue and six follow-ups are released as their parents are resolved. The runbook states a run budget of
240 tool calls, a billing rate limit of 6 calls per 10 seconds with `retry_after_s`, refund idempotency keys,
one refund per invoice, seven resolution rules applied in order, proration arithmetic for monthly and annual
plans against the desk's clock, and one templated message per escalation through the customer's channel in
the customer's locale. The oracle reads every fact from the gateway through a standard-library MCP client;
the seed is never consulted. The reference and the verifier implement the refund arithmetic independently.

### Controls

| Check | Command | Result |
|---|---|---|
| Static checks | `for c in scripts/checks/check-*.sh; do bash $c tasks/support-desk-gateway; done` | 25/25 pass (24/25 before the canary fix `bed518c`) |
| Docker build | part of the oracle run; gateway image installs `mcp==2.2.0`, `uvicorn==0.54.0` | builds |
| Oracle | `harbor run -p tasks/support-desk-gateway --agent oracle --env docker --yes` | reward 1.0, 59/59; 171 calls, 5 rate-limit waits, 1 min 10 s after the fixes |
| Nop | `harbor run -p tasks/support-desk-gateway --agent nop --env docker --yes` | reward 0.0, 56/59 fail, collect hook delivered the state |
| Cheat artifact | `cheat/solve.sh` run as the solution | reward 0.0, 47/59 fail; queue emptied with no side effects |
| Gateway tests | `pytest tools/desk/test_desk.py` | 17 passed, including the verifier's refund arithmetic against the oracle's on every seed invoice and both seed copies against the generator's output |

Recorded in `23fe428`. Review gate (rubric, exploitability, fairness) findings, each fixed in its own commit
with a regression test:

- `2686c81`: the instruction said "exactly one message per customer", false for the three customers with a
  follow-up; now "one per resolved escalation". The runbook's definition of done names credit notes, sandbox
  refunds, drafts and v1 posts, which the verifier already rejected.
- `a09af99`: `helpdesk_ticket_solve` had no closed guard, so a wrong close could be flipped and closed again;
  it now refuses closed tickets like `helpdesk_ticket_close`.
- `a9db966`: argument checks ran after the billing rate limit and never checked JSON types; a list as a
  project name reached the ledger and made the verifier raise. Checks now run first and enforce types.
- `5a17b40`: the oracle's month arithmetic raised on start days 29 to 31 while the verifier clamped; both
  clamp now and the runbook says so.
- `896676b`: catalog plurals produced `querys`; fixed, and the catalog passes the noun to the server.
- Exploitability: no way to reach reward 1 without doing the work was found. The artifact comes from the
  gateway container, resolve validates ids against the real ledgers, one refund per invoice with no delete,
  and the verifier counts ledgers, not the queue.

### Trials

Kill test (`960f240`; `tools/run-trial.sh claude anthropic/claude-opus-5-5 probe-desk-v1`):

| Trial | Reward | Agent time | Gateway calls | Errors | Wrong-tool calls | Notes |
|---|---|---|---|---|---|---|
| probe-desk-v1 | 1.0 (59/59) | 9.4 min | 149 of 240 | 0 | 0 | 149 native MCP calls, 47 shell calls; 10.6 M input tokens, 48.5 K output |

Additional trials after the kill test, same runner and flags, run as extra evidence on consistency
(pass^k) and on the cheat prompt for this candidate:

| Trial | Reward | Agent time | Gateway calls | Errors | Wrong-tool calls | Notes |
|---|---|---|---|---|---|---|
| run-desk-claude-2 | 1.0 (59/59) | 8.7 min | 149 of 240 | 0 | 0 | same call pattern as the probe |
| run-desk-claude-3 | 1.0 (59/59) | 10.8 min | 163 of 240 | 0 | 0 | two extra tracker searches, otherwise the same |
| cheat-desk-claude | 0.0 | 0.3 min | 0 | n/a | n/a | the CI hack prompt appended; the agent refused the task outright, so the run says nothing about the verifier beyond the required 0 |

### Measurements

Three rewards of 1.0 in 8.7 to 10.8 minutes, 149 to 163 of 240 budgeted calls, 0 errors, 0 wrong-tool
calls, 0 rate-limit hits, 0 duplicate keys, every refund amount exact in every run. pass^3 held: no
consistency collapse on this task. Adversarial run 0.0 by refusal.

### Analysis

The model read the runbook, listed the queue, and worked the escalations in order with the same eight-call
pattern the reference uses: ticket, account by email, account details, invoice, refunds list, side effect,
ticket close, resolve. It never called a deprecated, sandbox, legacy or raw tool, never hit the rate limit,
never reused a key, and re-read the queue after resolving so the follow-ups were picked up. Every refund
amount was exact, including the annual prorations and the follow-up that asks again for an invoice already
refunded. The 266-tool catalog cost it nothing: the `claude-code` harness loads MCP tools lazily and searches
them by name, so the distractors were never in its context. None of the production failures this candidate
was built to reproduce appeared. With a complete runbook and honest tool descriptions, Opus 5.5 at maximum
reasoning behaves like the reference solution.

### Decision and next step

Retired after the kill test, as the method requires. What the result adds to the analysis: the leaderboard
shape is necessary but not sufficient. The official zero-score tasks also carry information the agent cannot
read up front (event feeds at cutoffs, scanned images that override structured data), which a complete
runbook by definition does not. That is the axis for the next design (section 7).

## 7. Candidate 6: desk-shift-feed (retired)

### Hypothesis

Decision record, written before any build commit, per the iteration rule in 1.6.

Axis changed from candidate 5, and only this axis: the agent must go and read information that is not in
the runbook and that changes the right answer to work it has already done. Candidate 5 keeps its gateway,
its 266 tools, its ledgers, its budget and its lifecycle grading. Candidate 6 adds a shift clock and an
event feed.

- The desk clock advances as escalations are resolved, and the runbook says so. Proration is computed at
  the clock reading when the refund is issued, so the same invoice refunds less the later it is handled.
  The verifier recomputes every amount from the clock reading the gateway recorded at that refund.
- An event feed, named in the instruction, releases entries at stated cutoffs on the desk clock: a
  chargeback opened on an invoice refunded an hour earlier, a customer withdrawing a request after the
  refund went out, an invoice that was unpaid becoming paid, a plan change, a corrected invoice number.
  The runbook states the corrective action for each kind, and the actions are the usual irreversible
  ones: a finance issue of a stated kind on an already resolved case, a hold on the account, a message.
- Resolutions stay final. A corrective action is filed against the resolved escalation through a new
  gateway tool, never by resolving it again.
- Added on 2026-09-26 evening after a second pass over the leaderboard data (section 8.3): the runbook
  is stale in a few stated places, and says so at the top. Where the gateway's tool descriptions or
  replies disagree with the runbook, the gateway is right. Three of the fourteen tasks that defeat the
  strongest board model are debugging tasks whose comments are wrong but believable; the analogue in a
  production gateway is documentation drift, and the truth is always discoverable from the system. One
  stale item changes a graded amount (the clock advance per resolution); the others cost budget only.

Why this should defeat the model when candidate 5 did not: the ten zero-score leaderboard tasks all carry
information the agent cannot read before it must act, and candidate 5 had everything else (section 8.4).
The prediction is specific: the model will work the queue as it did in candidate 5, poll the feed when the
runbook says to, and fail on the reconciliation, either by acting on stale facts for a case it has already
handled, by repeating a side effect that the feed made wrong, or by missing a corrective action for a case
it considers closed. Time-dependent proration adds a second failure path: computing amounts from the clock
at the start of the shift rather than at the moment of the refund.

What proves the hypothesis wrong: reward 1.0 on the kill test (one `claude-code` run on `claude-opus-5-5`
at `max`, 2 h cap). If the transcript shows the model polling the feed after every resolution and
reconciling correctly, the line is closed with no hardening revision, because there is no further axis
inside "stated rules plus a stated source" left to try. Honest prior: about one chance in three that the
kill test fails, up from the one in five given to candidate 5 before its probe.

Fairness: the instruction names the feed and the cutoffs; the runbook states every corrective rule and the
clock rule, and states that it is stale where the gateway disagrees; nothing graded is hidden. Expected outcomes depend on the agent's own order of work, so the
verifier derives them from the recorded timeline rather than from a fixed answer key; the oracle and the
verifier implement the arithmetic independently, as in candidate 5.

### Build

Branch `ticket/tb3-original-task/candidate-desk-feed-task`, branched from the decision record. Candidate
5's package with the three changes and nothing else. Gateway: 268 tools; every resolution, amendment,
refund, message, issue and feed release stamped with a global operation number and the desk clock; the
clock advances six hours per resolution or amendment; eight authored feed entries at cutoffs from six to
seventy-eight hours after the start, released by the gateway at the first call after their time and
applied to the backends (flag, ticket closed by the customer, invoice paid, correction comment);
`desk_escalation_amend` files one corrective action per action per resolved case. Budget 300. The runbook
states at its top that it predates the gateway's latest changes and is stale in four places: clock
advance (four hours; the gateway says six), budget (240; the gateway says 300), refund key format (the
escalation id; the gateway wants `<escalation>:<invoice>`), and the hold template (`hold`; the gateway's
is `dispute_hold`). Each is discoverable from a tool description, a reply or an error; only the clock
advance can change a graded amount, and only for an agent that extrapolates instead of reading the clock.

Verifier: `tests/rules.py` replays the recorded timeline. For each resolution it computes the code the
runbook required on the facts released before that resolution and the refund amount for the clock reading
of the refund it references; for each released feed entry, the amendment required of each case already
resolved when it released. Ledgers are compared exactly. Expected outcomes therefore follow the agent's own
order of work, and the review gate simulated queue order, reverse order, follow-ups first, lazy feed
pulls, amendments deferred to the end, both orders of the invoice contended by a correction and a
follow-up, and forty random orders: every runbook-compliant order scores 1, every cheat scores 0.

### Controls

Same harness, runner and flags as candidate 5. Gates:

| Check | Command | Result |
|---|---|---|
| Static checks | `for c in scripts/checks/check-*.sh; do bash $c tasks/desk-shift-feed; done` | 25/25 pass, first run and after the fixes |
| Docker build | part of the oracle run | builds |
| Oracle | `harbor run -p tasks/desk-shift-feed --agent oracle --env docker --yes` | reward 1.0, 60/60; 197 calls, 4 rate-limit waits, two amendments in queue order, 1 min 2 s total |
| Nop | `harbor run -p tasks/desk-shift-feed --agent nop --env docker --yes` | reward 0.0, 56/60 fail |
| Cheat artifact | `cheat/solve.sh` run as the solution | reward 0.0, 40/60 fail; queue emptied with no side effects |

Gateway suite (`tools/feed/test_feed.py`): 15 passed, including the oracle run in-process graded by the
verifier, a hand-built order that files a refund after a late payment and shows the verifier rejects a
wrong amount, and a hand-built order in which the follow-up takes the contended invoice first.

Review gate findings and fixes, each fix with its regression test: the runbook now says the `refund_now`
amendment is filed even when the rules yield no refund, and that a case is judged on the facts at the
moment it is resolved, so a case's side effects, close and resolution belong together; the refund replay
keys on invoice and amount, not on the free-text reason; the verifier and the oracle cite invoices with
the same regex; the verifier image uses the same base tag as the others. No exploit found: the artifact
comes from the gateway container, references are validated against the real ledgers, ledgers are counted
exactly, and every feed entry must have released.

### Trials

Kill test (`tools/run-trial.sh claude anthropic/claude-opus-5-5 probe-feed-v1`, `reasoning_effort=max`):

| Trial | Reward | Agent time | Gateway calls | Errors | Wrong-tool calls | Amendments | Notes |
|---|---|---|---|---|---|---|---|
| probe-feed-v1 | 1.0 (60/60) | 10.0 min | 171 of 300 | 1 (`E_TEMPLATE`) | 0 | 2, both required | 171 native MCP calls, 19 shell calls; 10.0 M input tokens, 53.7 K output |

### Measurements

Reward 1.0 in ten minutes. 171 of 300 budgeted calls, 21 of them feed pulls (one after every resolution
and amendment, as the runbook says). One error in the whole run: the stale `hold` template, refused by
the gateway with the list of real templates, corrected on the next call. Every refund amount matched the
verifier's recomputation at its own clock reading, including the two refunds priced days later than the
shift start. Both required amendments filed with the right issue kinds and message; no amendment filed
where none was due, including the dispute on the withdrawn case.

### Analysis

The model read the runbook and its revision note, then read `desk_clock`, and from that point treated
the gateway as the source of truth: it never assumed the four-hour advance or the 240 budget, it used the
gateway's key format on the first refund, and the one stale item it did trust (the template name) was
refused loudly and fixed at once. It pulled the feed after every resolution, mapped each entry to the
case it affected, and filed exactly the corrective actions the table prescribes. Its order of work was
the queue order, the same as the reference, so the timeline and the amounts were the reference's. In the
transcript there is no moment where it acted on a stale picture: the three predicted failure paths, stale
facts on a handled case, a repeated side effect, and amounts computed from the start of the shift, did
not occur. The prior of one in three was wrong in the same direction as the earlier candidates.

### Decision and next step

Retired after the kill test, as the hypothesis said: no hardening revision, because the transcript shows
the model polling the feed after every step and reconciling correctly, and there is no further axis inside
"stated rules plus a stated source plus a stated staleness" left to try. Six candidates now share one
result: when everything needed is written down, or is discoverable from a truthful system, Opus 5.5 at
maximum reasoning executes it. The ten zero-score leaderboard tasks add knowledge that is neither: expert
judgment that cannot be looked up, or artifacts that must stay correct under change. The agent-gateway
domain does not supply the first, and the second is the only line left open.

## 8. Analysis across candidates

### 8.1 What the trials show

The brief asks for a task that both agents fail three times out of three. This repository does not yet
deliver that. Across five candidate designs, four of them passing every CI gate, Claude Opus 5.5 at maximum
reasoning solved each on the first attempt: 71, 4, 6, 6 and 9 minutes in the kill tests, and 99, 39 and 92
minutes in the three required trials on candidate 1. No trial crashed, timed out, hit a rate limit or
refused; every pass is genuine. The codex half of the matrix has not been run.

### 8.2 Why the models succeed

Each candidate was built on a documented weakness and each was solved for the same reason: once a task is
fair by the TB3 rubric, its difficulty is written down somewhere the model can read, and this model reads
everything. In the transcripts it reads the format and the checker first, states the modelling idea within
minutes, builds several independent checkers of its own, and stops only when they agree.

- Candidate 1 asked for an algorithmic insight. The insight is textbook for a model trained on operations
  research; a generic LP solver cannot scale, but the model never tried one.
- Candidate 2 asked for compression under a fixed lexical router. The reference could not reach a fair bar,
  so the task was unfair before it was hard.
- Candidate 3 asked the model to learn an unfamiliar stateful system by interacting with it. With honest help
  and a truthful status command, that is a few dozen requests of reading. Terse help and deferred state added
  two minutes.
- Candidate 4 asked for a judgment that recomputation cannot confirm. With every billing rule stated, each
  defect is a clean single-rule deviation and the grouping is mechanical.
- Candidate 5 put the leaderboard's hardest shape behind a 266-tool MCP gateway. The model used the gateway
  natively, picked the right tool 149 times out of 149, and matched the reference's call pattern. Its harness
  loads tools lazily, and the runbook named the path.

The pattern across the published attempts surveyed holds here: what still beats these models is knowledge
that cannot be written down without becoming a hidden rule (real document layouts, real legacy runtime
quirks, event feeds revealed at cutoffs), or physical and numerical problems in specialist domains. In the
agent-gateway domain, every rule can be stated, and a stated rule is a solved rule, even with 266 tools
between the agent and the ledger.

### 8.3 Where the models actually fail: the official per-task data

Before choosing the fifth design, the analysis above was checked against the official leaderboard runs
themselves. The leaderboard submission files in the Terminal-Bench repository
(`leaderboard/submissions/*.json`) name the Harbor Hub jobs behind each score, and the Hub's `get_job_tasks`
endpoint returns the per-task reward for a public job without a login. Pulled on 2026-09-26: 66 tasks in the
current set, 13 agent and model pairs, 5 attempts each.

| Pair (agent, model, effort) | Accuracy | pass@5 |
|---|---|---|
| claude-code, claude-fable-5-1, max | 57.9% | 78.8% |
| claude-code, claude-opus-5, max | 51.8% | 69.7% |
| codex, gpt-5.6-sol, max | 37.3% | 60.6% |

Neither of the brief's models (`claude-opus-5-5`, `gpt-6-sol`) is on the official board yet.

By category, the mean pass rate over all 13 pairs is lowest for Operations (0.20 over 9 tasks) and highest
for Security (0.46 over 5). Thirteen tasks are failed by both `claude-opus-5` and `gpt-5.6-sol` on every
attempt; ten of those also defeat `claude-fable-5-1` every time. Reading those ten, the shape is the same:

- State that changes under the agent and cannot be undone. A freight dispatch desk where the verifier asks
  for plans at several cutoffs during a shift and grades every commitment made along the way.
- Information that arrives over time, so the agent must act before it has seen the whole problem.
- Many small rules that interact: driver hours, supplier cutoffs, tolls and delivery windows, each simple,
  together a trap.
- Grading on the whole lifecycle, all or nothing.
- Truth split across sources: in the one official task that exposes an MCP server to the agent, the invoice
  images override the structured data. That task scores 0 for all 13 pairs.

The solved tasks are the mirror image: one artifact, computed offline, checkable by the model before it
hands it in. Candidates 1, 3 and 4 are all of that shape. Candidate 3 had a live gateway but a small state
that a status command reported truthfully.

Outside Terminal-Bench, the tool-calling numbers point the same way. Anthropic's own documentation says tool
selection degrades past 30 to 50 tools. On MCP-Atlas (220 tools, 36 servers) the best model reaches 62%; on
MCPMark the best single-attempt rate is 52.6% and the four-in-a-row rate 33.9%; on LiveMCPBench (527 tools)
about half of all failures are a wrong tool pick.

A second pass on 2026-09-26 evening, over the CI bot's own trial analyses on recent task PRs in the
Terminal-Bench repository, adds three points. First, the recent tasks that defeat both CI agents are near
misses under all-or-nothing grading: 33 of 38 tests passing, or a real fix on a code path the verifier
does not exercise. Second, the bot's own runs show `claude-fable-5-1` falling back to `claude-opus-5` or
`claude-opus-4-8` mid-task, and a public review found that only one of five published Opus 5.5 scores
rules fallback out; every trial in this repository sets `CLAUDE_CODE_NO_MODEL_FALLBACK=1`, so its numbers
are the named model's alone. Third, the CI hack prompt triggers a safety refusal on both agents in most
recent runs, which is why a refusal is reported here as "0 by refusal" and not as verifier evidence.

Grouping the fourteen tasks the strongest board model fails every time, by what the authors say makes
them hard: doubting text that is wrong but believable (three debugging tasks); returning to work already
done when new facts arrive (the two dispatch tasks and the claims task); rules that interact so that a
local fix breaks a global one (harmony, coupled bugs); expert knowledge that cannot be looked up (four
science tasks); and artifacts that must stay correct when a parameter changes (CAD, build pipeline,
anonymizer). Candidate 6 targets the second and third groups, and takes the first as its third change.

### 8.4 What candidate 5 added

Candidate 5 had every item on the leaderboard list except one, and was solved in nine minutes. The missing
item is the one the ten zero-score tasks all share and a complete runbook cannot: information the agent
cannot read before it must act. Waves that are released as earlier work completes are not enough when their
content follows the same stated rules; what defeats the models is content that changes the right answer to
work already done, or truth that lives in a source the agent must go and read (a scan, a feed at a cutoff)
rather than in the rules. That is fair under the rubric as long as the instruction says the source exists.

### 8.5 What this repository shows so far

Five complete TB3 task packages, four of them CI-clean with sealed verifiers, honest oracles and cheat
artifacts that all score zero; a kill-test discipline that measured each design against the target model
within hours of building it; and a record, in the git history and in this file, of what was tried, what it
cost, and why each line was closed.

## 9. Status against the brief

| Requirement | Status |
|---|---|
| Static checks, rubric, Docker build, oracle, nop | Passed on candidates 1, 3, 4, 5, 6. Candidate 2 shelved before the gates. |
| Verifier not exploitable (cheat artifact 0.0) | Passed on candidates 1, 3, 4, 5, 6. |
| `/run` claude-code, opus-5.5 max, x3, all genuine fails | Run on candidate 1: 3/3 genuine passes; also on candidate 5 as extra evidence: 3/3 passes; candidate 6 kill test: pass in 10 min. Requirement not met. |
| `/run` codex, gpt-6-sol xhigh, x3, all genuine fails | Not run. The codex login is not yet set up on the build machine. |
| `/cheat` claude-code x1, reward 0 | Done on candidate 1: 0.0; on candidate 5: 0.0 (the agent refused the prompt). |
| `/cheat` codex x1, reward 0 | Not run. |
| Failure analysis | Written for the passes (section 8); there are no model failures to analyse yet. |
| Commands, configs, results documented | This file and `tools/run-trial.sh`. |

## 10. Next steps, in loop order

1. Candidate 6: built, gated and killed in one evening (section 7). The line "stated rules plus a stated
   source plus a stated staleness" is closed. Any further candidate must change the kind of knowledge
   required, not the amount of state: an artifact that must stay correct under a change the verifier
   makes after the agent is done is the one leaderboard pattern not yet tried.
2. Complete the codex half of the record on candidate 1: `codex login`, then three `/run` trials and one
   `/cheat` trial through `tools/run-trial.sh`, so the brief's matrix has a codex result on the same task as
   the Claude result.
3. Build candidate 6, pass the gates, run the kill test. If it survives, run the six-trial matrix and the two
   adversarial trials on it; if not, one hardening revision, then retire and record.
4. Analyse every transcript, pass or fail, under the headings in section 1.5, and record it here the same
   day as the run.
