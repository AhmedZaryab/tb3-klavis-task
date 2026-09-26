# terminal-bench/support-desk-gateway

Work a support desk's refund escalations for one day. Every backend the company runs sits behind one
tool gateway that is registered with the agent as an MCP server, so the agent sees the whole company
catalog, about 270 tools across 19 products, as its own native tools. Twelve escalations are waiting
and six more are released as earlier ones are resolved. Refunds, customer messages and closed tickets
cannot be undone. The gateway meters every call against a run budget and rate-limits billing. Grading
reads the gateway's own ledgers after the agent's container is gone.

## Difficulty explanation

This is the daily work of a tier-two support agent at a subscription company, done through the kind of
tool gateway that companies now put in front of agents. Nothing is hidden: the runbook states every rule,
every tool describes itself honestly, every error names its cause. The difficulty is that the rules
interact and the state moves. Which code an escalation gets depends on the ticket, the account and the
invoice together, checked in a fixed order; the refund amount depends on the plan, the invoice period and
the desk's clock; the message depends on the code, the account's channel and its locale. The invoice a
customer cites may belong to a similarly named customer, or may already be refunded, or may not be paid.
Follow-ups arrive only after their parent is resolved and some of them ask again for something already
done. Around the right tools sit deprecated, sandbox and legacy look-alikes that do what they say and
nothing useful, and a budget that turns exploration into a cost. One refund of the wrong amount, one
message through the wrong channel or one duplicate side effect fails the run, and none of them can be
taken back. The data is synthetic and small; the difficulty is in doing eighteen interacting things
exactly once each.

## Solution explanation

Read the runbook, then loop over the queue: for each escalation read the ticket, find the account by
the requester's email (not the name), apply the resolution rules in order, do the side effects the code
requires through the current tools, close the ticket with the code, and resolve the escalation with the
ids of what was produced. Use the escalation id as the refund idempotency key, sleep for `retry_after_s`
on a billing rate limit, and re-read the queue after every resolution until it is empty. The reference
solution reads every fact from the gateway; the seed is never consulted.

## Verification explanation

The gateway runs as its own container and writes its state to a file the agent cannot reach. After the
agent's container stops, a collect hook copies that file out of the gateway container and the verifier,
in a third container, computes the expected outcome of every escalation from the seed and compares
ledgers: resolution codes and their references, the refund ledger exactly, the shadow ledgers empty,
messages exactly by customer, channel, template and locale, finance issues exactly, tickets closed with
their codes. No agent code is executed. Reward is 1 or 0.

## Relevant experience

I built and ran an agent gateway that fronts 183 tools across 10 products behind one key. Driving
frontier models through it, rather than through their vendor's harness, is where I watched them pick a
look-alike tool, make thirty calls where three were needed, and retry straight into a rate limit; the
runaway guard and the budget in this task are the ones that gateway grew. This task is that setting,
reduced to one desk and one day, with the ledgers as the judge.
