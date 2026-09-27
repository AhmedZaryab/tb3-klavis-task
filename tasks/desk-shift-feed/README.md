# terminal-bench/desk-shift-feed

Work a support desk's refund backlog over several days. Every backend sits behind one tool gateway that
is registered with the agent as an MCP server, about 270 tools across 19 products. Twelve escalations are
waiting and six more are released as earlier ones are resolved. The desk clock advances with every
resolution, and refunds are prorated at the clock reading when they are created. An event feed releases
facts at cutoffs on that clock that change the right answer to work already done: a dispute on an invoice
already refunded, a request withdrawn after the money went out, a late payment, a corrected invoice
number. The runbook states the corrective action for each, and says of itself that it is stale where the
gateway disagrees. Grading replays the gateway's own timeline.

## Difficulty explanation

This is tier-two support work at a subscription company through the kind of tool gateway companies now
put in front of agents. Nothing is hidden and nothing is beyond a careful reader: the runbook states every
rule, every tool describes itself, every error names its cause. The difficulty is that the world moves
under the agent in three ways at once. Amounts depend on when the work is done, not on the date the shift
started, so every refund must be computed against the clock at that moment. Facts arrive after decisions
are made, so the agent must return to cases it considers finished and file the corrective action the
runbook prescribes, without being able to undo the refund or the message, and without filing one where
the runbook does not require it. And the runbook is out of date in a few places, as production runbooks
are, so the agent must notice when the gateway says otherwise and trust the system over the document. Any
one of these is manageable; together, over eighteen cases and eight feed entries whose right handling
depends on the agent's own order of work, a single stale assumption or a single missed return to an old
case fails the run. The data is synthetic and small; the difficulty is in keeping the picture current.

## Solution explanation

Read the runbook, then loop over the queue: for each escalation read the ticket (a correction comment
overrides the body), find the account by the requester's email, apply the resolution rules in order on the
current facts, read the desk clock before computing a refund, do the side effects through the current
tools, close the ticket, and resolve the escalation with the ids of what was produced. After every
resolution pull the feed and, for each entry, find the cases already resolved that it affects and file the
amendment the runbook's table prescribes. Use `<escalation>:<invoice>` refund keys and the gateway's
template names, because the runbook's are stale. The reference solution reads every fact from the gateway.

## Verification explanation

The gateway runs as its own container and stamps every resolution, amendment, refund, message, issue and
feed release with a global operation number and the clock. After the agent's container stops, a collect
hook copies the gateway's state out and the verifier, in a third container, replays that timeline: for each
resolution, the code the runbook required on the facts released before it and the refund amount for the
clock reading of the refund it references; for each released feed entry, the amendment required of each
case already resolved at that moment. Ledgers are then compared exactly. No agent code is executed.
Reward is 1 or 0.

## Relevant experience

I built and ran an agent gateway that fronts 183 tools across 10 products behind one key. Driving frontier
models through it is where I watched them act on a stale picture: refund against the wrong date, miss the
dispute that came in after the refund, and follow documentation the system had moved past. This task is
that setting reduced to one desk and one backlog, with the gateway's own timeline as the judge.
