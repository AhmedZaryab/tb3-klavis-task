# Results

One original Terminal-Bench 3 task, built to the current TB3 CI and tested against the agents named in
the brief. This file is written as a research log. Section 1 states the method once: the question, how the
prediction is written down, what is held fixed, what is measured, how runs are analysed, and the rule for
iterating. Sections 2 to 6 apply that method to each of the five candidate designs in the order they were
tried, every one under the same headings, with the commits that hold each step. Section 7 is the analysis
across candidates, section 8 the status against the brief, section 9 the next steps in loop order. Raw
harbor output lives under `runs/` (not committed).

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
(section 7.3): a candidate Claude solves cannot meet the brief whatever codex does.

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

Retired as a difficulty candidate: the insight is textbook for this model. The package stays as the record,
and because no later candidate held either, the brief's required trial matrix is run on it.

Required trials (`tools/run-trial.sh`, full 8 h agent timeout, subscription auth):

| # | Agent | Model | Effort | Reward | Time | Tool calls | Errors | Job |
|---|---|---|---|---|---|---|---|---|
| 1 | claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 99 min | 82 | none | `runs/run-dispatch-claude-1` |
| 2 | claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 39 min | 52 | none | `runs/run-dispatch-claude-2` |
| 3 | claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 92 min | 96 | none | `runs/run-dispatch-claude-3` |

Additional evidence on the live CI defaults (not required by the brief):

| Agent | Model | Effort | Reward | Time | Tool calls | Errors | Job |
|---|---|---|---|---|---|---|---|
| claude-code | anthropic/claude-fable-5-1 | max | 1.0 | 113 min | 59 | none | `runs/run-dispatch-fable-1` |

Adversarial trial (the CI's `docs/prompts/hack-trial-prompt.md` appended to the instruction, one run per agent):

| Agent | Model | Effort | Reward | Time | Tool calls | What it did |
|---|---|---|---|---|---|---|
| claude-code | anthropic/claude-opus-5-5 | max | 0.0 | 1 min | 3 | enumerated /app, /logs and the checker; found no leaked answers, no writable grader state and no way to fake the exact-minimum check; reported "no credible bypass" and left no planner. It noted that a safety classifier cut off one probe; the report was still completed. |

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

## Candidate 4: gateway-metering-forensics (retired)

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

Feasibility probe (2 h cap):

| Agent | Model | Effort | Reward | Time | Notes |
|---|---|---|---|---|---|
| claude-code | anthropic/claude-opus-5-5 | max | 1.0 | 6 min 16 s | 20 tool calls; recomputed the ledger, diffed, and reported exactly five defects with the exact affected sets |

Verdict: with every policy rule stated, each defect is a clean single-rule deviation and the grouping is
mechanical, not a judgment. The pattern that beat earlier models needed mechanisms that no stated rule
pins down, and that is the kind of hidden rule the rubric forbids. Retired. This closes the design search:
four candidates, each passing every CI gate, each solved by Claude Opus 5.5 at max reasoning in 4 to 71
minutes. The required trial matrix runs on candidate 1.

## Candidate 5: support-desk-gateway (retired)

Branch `ticket/tb3-original-task/candidate-support-desk-task`, forked from the decision record.

Design, from the per-task leaderboard data and the author's gateway experience (see the decision record in
the analysis below): a support desk's refund escalations, worked through one company tool gateway that
Harbor registers with the agent as an MCP server. The gateway serves 266 tools across 19 products; 33 are
on the desk's path, the rest are honest distractors, including deprecated, sandbox and legacy look-alikes
of the tools that matter. Twelve escalations wait in the queue and six follow-ups are released as their
parents are resolved. The runbook states every rule: a run budget of 240 tool calls, a billing rate limit
of 6 calls per 10 seconds with `retry_after_s`, refund idempotency keys, one refund per invoice, seven
resolution rules applied in order, proration arithmetic for monthly and annual plans against the desk's
clock, and one templated message per escalation through the customer's channel in the customer's locale.
Refunds, messages and closed tickets cannot be undone. The verifier computes the expected outcome of all
eighteen escalations from the seed and compares the gateway's ledgers exactly.

Checks (`tasks/support-desk-gateway`):

| Check | Command | Result |
|---|---|---|
| Static checks | `for c in scripts/checks/check-*.sh; do bash $c tasks/support-desk-gateway; done` | 25/25 pass (24/25 before the canary fix) |
| Docker build | part of the oracle run below; gateway image installs `mcp==2.2.0`, `uvicorn==0.54.0` | builds |
| Oracle | `harbor run -p tasks/support-desk-gateway --agent oracle --env docker --yes` | reward 1.0, 59/59; 171 calls, 5 rate-limit waits, 1 min 10 s total after the fixes |
| Nop | `harbor run -p tasks/support-desk-gateway --agent nop --env docker --yes` | reward 0.0, 56/59 fail, collect hook delivered the state |
| Cheat artifact | `cheat/solve.sh` run as the solution | reward 0.0, 47/59 fail; queue emptied with no side effects |

The oracle reads every fact from the gateway through a standard-library MCP client; the seed is never
consulted. The reference and the verifier implement the refund arithmetic independently.

Review gate (rubric, exploitability, fairness), findings and fixes, each fix with its regression test:

- The instruction said "exactly one message per customer", false for the three customers with a follow-up;
  now "one per resolved escalation". The runbook's definition of done now names credit notes, sandbox
  refunds, drafts and v1 posts, which the verifier already rejected.
- `helpdesk_ticket_solve` had no closed guard, so a wrong close could be flipped and closed again; it now
  refuses closed tickets like `helpdesk_ticket_close`.
- Argument checks ran after the billing rate limit and never checked JSON types; a list as a project name
  reached the ledger and made the verifier raise. Checks now run first and enforce types, `E_ARGS`.
- The oracle's month arithmetic raised on start days 29 to 31 while the verifier clamped; both clamp now
  and the runbook says so.
- Catalog plurals produced `querys`; fixed, and the catalog passes the noun to the server.
- No way to reach reward 1 without doing the work was found: the artifact comes from the gateway
  container, resolve validates ids against the real ledgers, one refund per invoice with no delete, and
  the verifier counts ledgers, not the queue.

Gateway test suite (`tools/desk/test_desk.py`): 17 passed, including the verifier's refund arithmetic
against the oracle's on every seed invoice and both seed copies against the generator's output.

Probe (`tools/run-trial.sh claude anthropic/claude-opus-5-5 probe-desk-v1`, `reasoning_effort=max`):

| Trial | Reward | Agent time | Gateway calls | Errors | Wrong-tool calls | Notes |
|---|---|---|---|---|---|---|
| probe-desk-v1 | 1.0 (59/59) | 9.4 min | 149 of 240 | 0 | 0 | 149 native MCP calls, 47 shell calls; 10.6 M input tokens, 48.5 K output |

What the transcript shows. The model read the runbook, listed the queue, and worked the escalations in
order with the same eight-call pattern the reference uses: ticket, account by email, account details,
invoice, refunds list, side effect, ticket close, resolve. It never called a deprecated, sandbox, legacy
or raw tool, never hit the rate limit, never reused a key, and re-read the queue after resolving so the
follow-ups were picked up. Every refund amount was exact, including the annual prorations and the
follow-up that asks again for an invoice already refunded. The 266-tool catalog cost it nothing: the
`claude-code` harness loads MCP tools lazily and searches them by name, so the distractors were never in its context.

The production failures this candidate was built to reproduce, look-alike tool picks, thirty calls where
eight are needed, retry storms, did not appear. With a complete runbook and honest tool descriptions,
Opus 5.5 at maximum reasoning behaves like the reference solution. Retired after the probe, as planned.

## Analysis

### What the six standard trials show

The brief asks for a task that both agents fail three times out of three. This repository does not deliver
that. Across four candidate designs, every one passing every CI gate, Claude Opus 5.5 at maximum
reasoning solved each in the first attempt: 71, 4, 6 and 6 minutes in the probes, and 99, 39 and 92
minutes in the three required trials on candidate 1. No trial crashed, timed out, hit a rate limit or
refused; every pass is genuine.

### Why the models succeed

Each candidate was built on a documented weakness and each was solved for the same reason: once a task is
fair by the TB3 rubric, its difficulty is written down somewhere the model can read, and this model reads
everything. In the transcripts it reads the format and the checker first, states the modelling idea within
minutes, builds several independent checkers of its own, and stops only when they agree.

- Candidate 1 asked for an algorithmic insight (the token bucket relaxes exactly into a min-cost flow). The
  insight is textbook for a model trained on operations research; a generic LP solver cannot scale, but the
  model never tried one. It went straight to the flow.
- Candidate 2 asked for compression under a fixed lexical router. The reference solution could not reach a
  fair bar, so the task was unfair before it was hard.
- Candidate 3 asked the model to learn an unfamiliar stateful system by interacting with it. With honest
  help and a truthful status command, that is a few dozen requests of reading. Making the help terse and the
  state deferred added two minutes.
- Candidate 4 asked for a judgment that recomputation cannot confirm: how many distinct defects explain a
  ledger. With every billing rule stated, each defect is a clean single-rule deviation and the grouping is
  mechanical.

- Candidate 5 put the leaderboard's hardest shape (irreversible state, waves, interacting rules,
  lifecycle grading) behind a 266-tool MCP gateway. The model used the gateway natively, picked the
  right tool 149 times out of 149, and matched the reference's call pattern. The tool bloat that breaks
  agents in production did not reach it: its harness loads tools lazily, and the runbook named the path.

The pattern across the published attempts we surveyed holds here: what still beats these models is
knowledge that cannot be written down without becoming a hidden rule (real document layouts, real legacy
runtime quirks, event feeds revealed at cutoffs), or physical and numerical problems in specialist
domains. In the agent-gateway domain, where the author's expertise lies, every rule can be stated, and a
stated rule is a solved rule, even when 266 tools stand between the agent and the ledger.

### Where the models actually fail: the official per-task data

The analysis above was written from the four probes and from published reports. Before choosing a fifth
design it was checked against the official leaderboard runs themselves. The leaderboard submission files
in the Terminal-Bench repository (`leaderboard/submissions/*.json`) name the Harbor Hub jobs behind each
score, and the Hub's `get_job_tasks` endpoint returns the per-task reward for a public job without a
login. Pulled on 2026-09-26: 66 tasks in the current set, 13 agent and model pairs, 5 attempts each.

| Pair (agent, model, effort) | Accuracy | pass@5 |
|---|---|---|
| claude-code, claude-fable-5-1, max | 57.9% | 78.8% |
| claude-code, claude-opus-5, max | 51.8% | 69.7% |
| codex, gpt-5.6-sol, max | 37.3% | 60.6% |

Neither of the brief's models (`claude-opus-5-5`, `gpt-6-sol`) is on the official board yet.

By category, the mean pass rate over all 13 pairs is lowest for Operations (0.20 over 9 tasks) and highest
for Security (0.46 over 5). Thirteen tasks are failed by both `claude-opus-5` and `gpt-5.6-sol` on every
attempt; ten of those also defeat `claude-fable-5-1` every time. Reading those ten, the shape is the same
in each:

- State that changes under the agent and cannot be undone. A freight dispatch desk where the verifier
  asks for plans at several cutoffs during a shift and grades every commitment made along the way.
- Information that arrives over time, so the agent must act before it has seen the whole problem.
- Many small rules that interact: driver hours, supplier cutoffs, tolls and delivery windows, each simple,
  together a trap.
- Grading on the whole lifecycle, all or nothing.
- Truth split across sources: in the one official task that exposes an MCP server to the agent, the
  invoice images override the structured data. That task scores 0 for all 13 pairs.

The solved tasks are the mirror image: one artifact, computed offline, checkable by the model before it
hands it in. Candidates 1, 3 and 4 in this repository are all of that shape, and each was solved in
minutes. Candidate 3 had a live gateway but a small state that a status command reported truthfully, so
the model read it and walked through.

Outside Terminal-Bench, the tool-calling numbers point the same way. Anthropic's own documentation says
tool selection degrades past 30 to 50 tools. On MCP-Atlas (220 tools, 36 servers) the best model reaches
62%; on MCPMark the best single-attempt rate is 52.6% and the four-in-a-row rate 33.9%; on LiveMCPBench
(527 tools) about half of all failures are a wrong tool pick.

### Decision: candidate 5, a support desk behind a 250-tool gateway

The author's production experience with an agent gateway is the second input to this decision. With a few
hundred tools behind one aggregator key, agents picked look-alike tools, made thirty or more calls where
two or three were needed, retried straight into rate limits, and went down wrong paths that a fresh
context would not have taken. Runaway protection had to be added to the gateway. None of the first four
candidates reproduced that setting: they gave the model a terminal and a file, not a tool surface.

Candidate 5 combines the two findings. The hard core is the Operations shape from the data: a customer
support escalation queue where refunds and messages cannot be undone, follow-ups arrive as earlier cases
are resolved, a dozen stated rules interact (proration by plan, chargeback holds, invoice ownership,
one refund per invoice, channel and locale), and the verifier grades the whole lifecycle from the
gateway's own ledger. The tool surface is the production setting: every backend sits behind one MCP
gateway that Harbor registers directly into `claude-code` and `codex`, about 250 tools across 22 services
with deprecated, sandbox and legacy look-alikes described honestly, a rate limit with retry-after on
billing, and a call budget that ends the run when it is spent. The tools are a multiplier; the state
machine is the difficulty, so writing a client script does not remove it.

Everything is stated in the runbook. Nothing is hidden except the expected end state, which the verifier
computes from the same seed. The kill test is unchanged: a two-hour Opus 5.5 probe before the matrix.

Outcome (recorded in the Candidate 5 section above): the probe passed in 9.4 minutes with no wrong tool
calls and no errors. The leaderboard shape is necessary but not sufficient: the official zero-score tasks
also carry information the agent cannot read up front (event feeds at cutoffs, scanned images that
override data), which a stated runbook by definition does not.

### What this repository shows instead

Five complete, CI-clean TB3 task packages with sealed verifiers, honest oracles and cheat artifacts that all
score zero; a kill-test discipline that measured each design against the target model within hours of
building it; and a record, in the git history and in this file, of what was tried, what it cost, and why
each line was closed.
