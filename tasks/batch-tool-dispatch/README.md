# terminal-bench/batch-tool-dispatch

Plan a nightly batch of tool calls onto rate-limited MCP servers at minimum cost. Each server has a per-call
price, a concurrency cap and a token bucket; each call has a release tick, a deadline and a set of eligible
servers; a call can be dropped at a fixed penalty. The planner is graded on unseen instances of up to
20,000 calls and must reach the exact minimum cost within 60 seconds per instance.

## Difficulty explanation

The obvious planner, earliest deadline first onto the cheapest server that still has a token, is feasible
but lands well above the minimum because it drains the cheap buckets early and starves the later,
tighter calls. The exact answer needs one modelling insight: the capped bucket, which looks non-convex,
relaxes exactly into a network, so the whole batch is a time-expanded min-cost flow. Writing the natural
integer program instead is correct but does not scale: a generic LP solver takes minutes at a few
thousand calls where the flow formulation takes under a second at 20,000. The data is synthetic but
shaped like a real gateway's nightly load: cheap servers with small buckets, expensive ones with large
buckets, calls arriving in waves with windows from a couple of ticks to a few dozen.

## Solution explanation

Aggregate calls that share (release, deadline, eligible servers) into one demand node; build, per server,
a chain of tick nodes where a capacity arc enforces the bucket cap and storage arcs carry unused tokens
forward; refill arcs from the source, concurrency arcs before the draw arcs, drop arcs at the penalty
cost; solve the min-cost flow (OR-Tools) and decode the integral flow call by call.

## Verification explanation

The verifier runs in its own container with 20 hidden instances from the same generator and their
optimal costs computed at image build time. It runs the agent's planner unprivileged with a 60 second
limit per instance, then checks feasibility with the same checker the agent had and requires the cost to
equal the optimum on every instance. Costs are integers, so there is no tolerance. Reward is 1 only if all
20 instances pass.

## Relevant experience

I built an agent gateway that routes 183 tools across 10 products behind token-spend gates and
provider rate limits; this task is the offline version of the dispatch decision that gateway makes live.
