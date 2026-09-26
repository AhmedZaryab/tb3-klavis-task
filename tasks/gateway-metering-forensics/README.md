# terminal-bench/gateway-metering-forensics

A week of an agent gateway's billing ledger disagrees with its billing policy. Produce the corrected ledger
and identify the distinct defects in the metering code that explain every disagreement, with the requests
each one affected. The ledger is checked exactly; the defect list is checked on how many defects there are
and on each defect's affected set, up to relabeling.

## Difficulty explanation

Recomputing the correct ledger is careful work but fully specified by the policy. The hard part is the
second deliverable: five independent wrong rules overlap on the same requests (a cancelled retry, a
cache-heavy tenant on the discounted tier, a retry that straddles midnight), so the per-request
discrepancies do not sort themselves into causes. An explanation with too few defects covers every
discrepancy with a rule that is wrong in two ways at once; one with too many splits a single wrong rule by
symptom. No recomputation can confirm which grouping is right, so an analyst's own verification passes
while the answer is wrong. The data is synthetic, generated from the policy with the defects injected, and
shaped like a real gateway week: bursts, retries, cancellations, timezone spread and a mid-week price change.

## Solution explanation

Compute the correct amount for every request from the policy, diff it against the ledger, and for each
disagreeing request test which single wrong-rule hypotheses, derived one per policy rule, reproduce the
billed amount alone or in combination. Group the affected requests by hypothesis. The reference solution
derives the hypotheses from the rules and never hardcodes request ids.

## Verification explanation

The verifier runs in its own container with the ground truth regenerated from the same seed at image
build time; the generator never enters the agent image. It parses the two output files as data: every
request present once with the exact correct amount, and a defect list whose count equals the truth and
whose affected sets match the true sets one to one. Descriptions are not graded. Reward is 1 or 0.

## Relevant experience

I built the token-spend gates and metering for an agent gateway serving 10 products; the defects in this
task are the classes of metering bug I have had to find and explain to finance, where the count of root
causes decided how many fixes shipped.
