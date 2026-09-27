# tb3-klavis-task

Six candidate designs for one original [Terminal-Bench 3](https://github.com/harbor-framework/terminal-bench)
task in the agent-gateway domain, each built to the current TB3 CI, each tested against Claude Opus 5.5 at
maximum reasoning within hours of being built, and each solved. The task the brief asks for, one that both
agents fail three times out of three, was not found. What the repository delivers instead is the record:
five CI-clean task packages with sealed verifiers, eleven genuine agent runs, a study of the official
per-task leaderboard data, and a written analysis of why every design fell, in a git history where each
hypothesis is committed before its build and each kill test before the next hypothesis.

## Results at a glance

| Candidate | Task | Gates | Kill test (Opus 5.5, max) | Outcome |
|---|---|---|---|---|
| 1 | `batch-tool-dispatch` | 25/25, oracle 1.0, nop 0.0, cheat 0.0 | pass, 71 min | three required trials: 3/3 passes (99, 39, 92 min); cheat trial 0.0; Fable 5.1 extra run pass in 113 min |
| 2 | `mcp-tool-index` | shelved before the gates | not run | reference solution could not reach a fair bar (47.7% vs 92%) |
| 3 | `gateway-tenant-onboarding` | 25/25, oracle 1.0, nop 0.0, cheat 0.0 | pass, 4 min; hardened revision pass, 6 min | retired |
| 4 | `gateway-metering-forensics` | 25/25, oracle 1.0, nop 0.0, cheat 0.0 | pass, 6 min | retired |
| 5 | `support-desk-gateway` | 25/25, oracle 1.0, nop 0.0, cheat 0.0 | pass, 9 min, 266 native MCP tools, 0 wrong-tool calls | two more trials 3/3 passes; cheat trial 0.0 by refusal; retired |
| 6 | `desk-shift-feed` | 25/25, oracle 1.0, nop 0.0, cheat 0.0 | pass, 10 min, feed pulled after every step | retired; line closed |

Every run used the brief's configuration: `claude-code` on `anthropic/claude-opus-5-5`, `reasoning_effort=max`,
subscription auth, model fallback disabled. No run crashed, timed out, hit a rate limit or fell back. The
`codex` half of the matrix was not run, by decision; section 9 of `RESULTS.md` says why and how to run it.

## The finding

Each candidate targeted a documented weakness: an algorithmic insight under exactness, an unfamiliar
stateful protocol learned by interaction, a judgment recomputation cannot confirm, a 266-tool gateway
with look-alike tools and irreversible side effects, and finally a moving clock, a feed that changes the
answer to work already done, and a runbook that admits it is stale. Each was solved for the same reason:
once a task is fair by the TB3 rubric, its difficulty is written down or discoverable from a truthful
system, and this model reads everything and verifies what it can. The official per-task leaderboard data,
pulled from the Harbor Hub on 2026-09-26, says what still beats the strongest models: expert knowledge that
cannot be looked up, and artifacts that must stay correct under a change made after the agent is done. The
agent-gateway domain supplies neither. `RESULTS.md` section 8 carries the data and the argument.

## How to reproduce

Requirements: harbor 0.23.0, Docker Desktop, a Claude subscription token in `.env` as
`CLAUDE_CODE_OAUTH_TOKEN` (never committed), Python 3.12 on PATH for the static checks.

```bash
# CI gates on any candidate (terminal-bench checkout at 4def1f3 for the check scripts)
for c in scripts/checks/check-*.sh; do bash $c tasks/desk-shift-feed; done
harbor run -p tasks/desk-shift-feed --agent oracle --env docker --yes
harbor run -p tasks/desk-shift-feed --agent nop --env docker --yes

# agent trials with the brief's flags (token read from .env, redacted from logs)
TASK=tasks/desk-shift-feed tools/run-trial.sh claude anthropic/claude-opus-5-5 my-run
TASK=tasks/desk-shift-feed tools/run-trial.sh codex  openai/gpt-6-sol        my-run   # after codex login

# tooling test suites
python -m pytest tools/desk/test_desk.py tools/feed/test_feed.py tools/dispatch/test_dispatch.py \
                 tools/strata/test_strata.py tools/opsgate/test_server.py
```

The cheat trial appends the CI's hack prompt to the instruction and runs the same command on the copy.

## Layout

```
RESULTS.md              the research log: method, six candidates under the same headings, analysis, status
tasks/<name>/           one complete TB3 task package each: task.toml, instruction.md, README.md,
                        environment/ (agent image, gateway sidecar), solution/ (reference), tests/ (sealed
                        verifier), cheat/ (deliberate poisoned artifact that must score 0)
tools/run-trial.sh      the one runner every trial went through
tools/<candidate>/      generators, calibration, and the test suite for each candidate's gateway or verifier
.github/                the pull request template with the gate table
```

## How the work is organised

The git history is the iteration record. One epic branch, one ticket branch per candidate, and commit
prefixes that map to the loop: `prepare` (hypothesis and task statement), `impl`, `test`, `fix` (one review
finding with its regression test), `verify` (a gate or trial result, number in the subject), `docs(epic)`
(trial records and the decision record that opens the next candidate), `merge` (outcome in the subject).
Every change arrived by pull request; nothing was squashed. Section 1.7 of `RESULTS.md` has the map.

AI coding agents were used throughout, as the brief allows; the design decisions, the kill-test rule and
the analysis are the author's and are discussed in `RESULTS.md`.

## License

MIT. See `LICENSE`.
