# Author's report

What I set out to do, how I went about it, what I found, and what I am changing in my own setup because
of it. `RESULTS.md` is the formal log with every number and command; this is the story behind it.

## Where I started

I run an agent gateway in production. It fronts 183 tools across 10 products behind one key, and agents
call it the way they would call any MCP server. Driving frontier models through it, rather than through
the vendor's own coding harness, I kept seeing the same four failures: the model picks a look-alike tool
instead of the right one; it makes thirty calls where two or three would do; it retries straight into a
rate limit and keeps retrying; and it goes down a wrong path that a fresh context would never take. I had
to build runaway protection into the gateway because of it. The same models, in their vendor's harness,
did not behave that way. So when the brief asked for a Terminal-Bench 3 task that Opus 5.5 and GPT-6
genuinely fail, my first instinct was that I already knew where the failure lived: in the tool layer, with
many tools, side effects and rate limits. This exercise was my chance to reproduce it under controlled
conditions and put a number on it.

## How I went about it

I treated it as an experiment rather than a build. Before each candidate I wrote down the weakness it
targeted, why the design should defeat the model, and what result would prove me wrong. Then I built it,
passed every CI gate the TB3 repository runs (25 static checks, both images, oracle 1.0, nop 0.0, and a
deliberate cheat artifact that must score 0), had a review pass over the verifier for exploits and hidden
rules, and only then ran a kill test: one Opus 5.5 run at maximum reasoning with a two-hour cap. A pass
meant the hypothesis was wrong and the candidate was retired. That rule cost me some attachment to
designs I liked, but it kept the eight-hour trial budget for candidates that had earned it, and it meant
every retirement had a transcript behind it, not a feeling.

The git history is the lab notebook. One branch per candidate, and commit prefixes that map onto the loop:
`prepare` holds the hypothesis, `impl` the build, `test` the suites, `fix` one review finding with its
regression test, `verify` a gate or trial result with the number in the subject, `docs(epic)` the trial
records and the decision that opens the next candidate. Every change arrived by pull request and nothing
was squashed, so the order in which things were decided is auditable.

I used coding agents for most of the typing. The decisions, the kill-test rule and the analysis are mine.

## What I tried, in order

1. **batch-tool-dispatch.** An exact-optimum scheduling problem: 20,000 tool calls onto rate-limited MCP
   servers, where the trick is that a capped token bucket relaxes exactly into a min-cost flow. I predicted
   the model would reach for a generic solver that cannot scale. It found the flow in eleven minutes and
   spent the rest of the run building independent checkers. Solved in 71 minutes; the three required
   trials passed in 99, 39 and 92 minutes.
2. **mcp-tool-index.** Compress a 242-tool catalog so a fixed router still routes correctly under a token
   budget. My own reference could not reach a fair bar, so the task was unfair before it was hard. Shelved.
3. **gateway-tenant-onboarding.** A legacy gateway with its own line protocol, staged commits, idempotency
   keys, session budgets and a loop guard. The prediction was that the model trips the guard before it
   learns the commit semantics. With truthful help and a truthful status command it walked through in
   four minutes. Terse help and deferred state added two.
4. **gateway-metering-forensics.** A week of billing ledger that disagrees with policy because five
   metering defects overlap; produce the corrected ledger and say how many distinct defects there are.
   I thought counting causes was a judgment, not a computation. With every rule stated, it was mechanical.
   Six minutes.
5. **support-desk-gateway.** This was the one built from my own experience, after I stopped guessing and
   pulled the official per-task leaderboard data. A support desk working refund escalations through one
   MCP gateway serving 266 tools across 19 products, with deprecated, sandbox and legacy look-alikes next
   to the real tools, refunds and messages that cannot be undone, follow-ups released as cases close, a
   call budget and a billing rate limit. Everything I had watched break in production. Opus resolved all
   eighteen cases in nine minutes with zero wrong-tool calls and the same eight-call pattern as my
   reference solution. Two more runs: nine and eleven minutes, both perfect.
6. **desk-shift-feed.** The last thing the leaderboard's zero-score tasks had that mine did not: facts the
   agent cannot read before it acts. I made the clock move so amounts depend on when work is done, added
   a feed that releases events after cases are closed and requires corrective actions on them, and made
   the runbook stale in four stated places. Opus read the clock before every amount, pulled the feed after
   every step, filed exactly the corrections required, and treated every runbook number as something to
   check. Ten minutes.

## What I saw in my setup, and what I tried to replicate

In my gateway the model sees the whole catalog at once. The tool definitions sit in its context on every
turn, the gateway's errors are terse, retry-after is not always surfaced, and there is no budget in the
reply. Candidate 5 reproduced the catalog, the look-alikes, the irreversibility and the rate limit as
faithfully as a fair task allows. What it could not reproduce, because Harbor registers the gateway
directly into the vendor harness, was my harness itself. That turned out to be the point.

## Results

| Candidate | Gates | Opus 5.5 kill test | Further runs |
|---|---|---|---|
| batch-tool-dispatch | all green | pass, 71 min | 3/3 passes (99, 39, 92 min); cheat 0.0; Fable 5.1 pass, 113 min |
| mcp-tool-index | shelved | not run | reference could not reach a fair bar |
| gateway-tenant-onboarding | all green | pass, 4 min; hardened 6 min | |
| gateway-metering-forensics | all green | pass, 6 min | |
| support-desk-gateway | all green | pass, 9 min, 0 wrong-tool calls | 3/3 passes; cheat 0.0 by refusal |
| desk-shift-feed | all green | pass, 10 min, 0 wrong-tool calls | |

Eleven genuine runs, eleven passes. The codex half of the matrix was not run; I time-boxed the work at two
days and chose not to buy the subscription its auth path needs. Since every Claude kill test passed, a codex
result could not have changed the outcome against the brief.

## What I realised

**A stated rule is a solved rule.** The TB3 rubric requires that nothing graded be hidden, and rightly so.
But once every rule is written down or discoverable from a truthful system, Opus 5.5 at maximum reasoning
executes it. It reads the runbook, states its plan, builds its own checks, and stops when they agree. Six
designs, six data points, one cause.

**Announced staleness is an instruction to verify.** Telling the model "this runbook is out of date where
the gateway disagrees" did not trip it. It made the model read the clock first and treat every number in
the document as a hypothesis. Fairness demands the announcement, and the announcement removes the trap.

**Tool bloat never reached the model.** The 266 tools that I expected to cause wrong picks were loaded
lazily by the vendor harness and searched by name. The distractors were never in its context. In my
gateway they always are.

**What actually beats the strongest models, from the leaderboard data.** I pulled the per-task rewards for
every official run (66 tasks, 13 agent-model pairs, 5 attempts each). Fourteen tasks defeat the strongest
model every time. Reading their authors' notes, they fall into five groups: doubting text that is wrong but
believable; going back to fix work when new facts arrive; rules that interact so a local fix breaks a
global one; expert knowledge that cannot be looked up; and artifacts that must stay correct under a change
made later. My candidates targeted the second and third and took the first as a change. The fourth is not
in my domain. The fifth is the only one I did not try.

**Three things about the benchmark itself.** Recent task PRs that beat both CI agents are near misses
under all-or-nothing grading, not conceptual failures. The CI bot's own runs show the flagship model
silently falling back to an older one mid-task, which is why every run in this repository disables
fallback and says so. And the adversarial prompt mostly ends in a safety refusal, which is a zero but not
evidence about the verifier.

## The reason my harness failed, and the delta I am going to measure

Everything I watched go wrong in production happened with the same models that solved these tasks in
minutes. The tasks reproduced the catalog, the side effects and the rate limits; they could not reproduce
my harness. So the failure is in the delta between the two harnesses, and I now have a list of what that
delta is:

- **Tool definitions in context.** My gateway hands the model all 183 tools on every turn. The vendor
  harness loads MCP tools lazily and searches them by name, so the model picks among a handful. The
  published numbers say selection degrades past 30 to 50 tools; my setup lives past that line.
- **Error quality.** Every error in these tasks names its code, says what went wrong, and carries
  `retry_after_s` and the remaining budget. Mine are terser, and a retry storm is what a model does when
  an error does not tell it how long to wait.
- **Truthful state on demand.** The model here could always ask the system what was true. Where my
  documentation and my system disagree, the model has no way to find out which is right.
- **Model fallback.** I did not control it. The CI evidence shows it happens silently; some of what I
  attributed to the flagship model may not have been the flagship model.
- **Runaway protection as a rule, not a surprise.** A stated budget in every reply made the model frugal
  without a single budget error in eleven runs. A guard that trips unannounced is a failure the model
  cannot plan around.

## Monday

I am going back to my own gateway with this list. First, measure the delta rather than assume it: run
candidate 5 through my harness with the same model and the same flags, and compare call counts,
wrong-tool picks and outcome against the eleven runs here. Then close the gaps in order of the numbers:
lazy tool loading with search by name, errors that say what to do next, retry-after and remaining budget
on every reply, a truthful status endpoint, fallback pinned off, and the runaway guard stated up front. The
task package in this repository is the test bench for all of it: it is fair, sealed and CI-clean, and it
already knows what a correct run looks like.

## What I learned about doing this kind of work

Write the hypothesis before the build, and write down what would prove it wrong. Kill early with a cheap
run before spending the expensive one. Have someone, or something, try to break the verifier before the
model does. Pull the real data before designing from a story, even when the story is yours; the
leaderboard pull turned candidates 5 and 6 from guesses into tests. And when the result is negative, say
so plainly and explain it. I did not find the task the brief asked for. I found out why, and that has
already changed what I am building.
