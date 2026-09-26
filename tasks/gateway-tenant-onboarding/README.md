# terminal-bench/gateway-tenant-onboarding

Onboard three tenants through a legacy agent-tool gateway that only speaks its own line protocol. The
gateway stages every change until it is committed, requires idempotency keys, meters each session, and
trips a loop guard on repeated identical requests. Grading reads the gateway's own committed state after
the agent's container is gone.

## Difficulty explanation

Nothing about the task is hidden: the gateway's help and status commands tell the truth, but only when
asked, and only about what is asked. The difficulty is operating an unfamiliar stateful system correctly by
interacting with it rather than by reading about it: telling accepted from committed, discovering the
commit order, recovering a session that the loop guard locked because of the operator's own retries,
noticing that a retry without an idempotency key counts as a second invocation, and finding the current
tool versions behind the deprecated ones on later pages. Each rule is ordinary for a production gateway;
together they punish assuming the system behaves like the protocols one already knows. The data is synthetic
and small; the difficulty is in the interaction, not the volume.

## Solution explanation

Read the help for every verb, list the tools to find the current version of each of the three, then for each
tenant bind, commit each binding, grant, commit each grant, invoke once per tool with a fresh idempotency
key, and finish, opening a resumed session whenever the budget runs out or the loop guard trips. The reference
solution discovers the tool identifiers from the gateway rather than hardcoding them.

## Verification explanation

The gateway runs as its own container and persists its state to a file the agent cannot reach. After the
agent's container stops, a collect hook copies that file out of the gateway container and the verifier,
in a third container, parses it as data: exactly the required bindings, scopes and single invocations per
tool for the three tenants, tenants marked onboarded, no pending stages, and the two other seeded tenants
unchanged. No agent code is executed. Reward is 1 or 0.

## Relevant experience

I built an agent gateway that routes 183 tools across 10 products with token-spend gates and a runaway-loop
guard; the rules in this task are the ones that gateway enforces, and the failure modes are the ones I
watched models hit when driven through it instead of through their vendor's harness.
