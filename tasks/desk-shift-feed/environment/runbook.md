# Support desk runbook: refund escalations

Revision note: this runbook was last revised before the gateway's September
changes. Where a gateway tool's description, a gateway reply or a gateway
error disagrees with this text, the gateway is right and this text is out of
date.

Everything the desk touches is behind the company tool gateway, which is
registered with you as the MCP server `gateway`. The gateway exposes every
backend the company has connected, not only the ones the desk uses. The
desk's path runs through the tools named below. Other tools exist and work;
they are simply not part of this workflow.

## Gateway rules

- Every tool call counts against the run budget of 240 calls, whether it
  succeeds or fails. After the budget is spent every call returns `E_BUDGET`.
- The `billing_*` tools share a rate limit of 6 calls per rolling 10 seconds.
  Over the limit a call returns `E_RATE_LIMIT` with `retry_after_s`; that call
  did not happen, and it still counted against the budget.
- `billing_refund_create` needs an `idempotency_key`, which is the escalation
  id. The same key with the same invoice and amount returns the original
  refund again and moves no money; the same key with a different invoice or
  amount is refused. An invoice can be refunded once.
- Refunds, customer messages and closed tickets cannot be undone.
- `desk_escalation_resolve` is final. Resolving an escalation may release
  follow-up escalations into the queue; the queue is not static. Work until
  `desk_queue_list` is empty and the feed has nothing left to act on.
- Every error names its code and says what went wrong. Every reply carries
  `calls_used` and `budget`.

## The desk clock

The desk works through a backlog over several days. `desk_clock` returns the
desk's current date and time. Every resolution advances the clock by four
hours. Refund proration uses the clock's date at the moment the refund is
created, never the wall clock and never the date the shift started: the same
invoice refunds less the later it is handled.

## The event feed

Facts change while the desk works. `desk_feed_pull` returns feed entries that
have been released at or before the desk clock; pass the cursor from the last
pull to get only new entries. Pull the feed after every resolution. When an
entry is released the gateway has already applied the fact to the backends:
a dispute sets the account flag `chargeback_pending`, a withdrawal closes the
ticket as `closed_by: customer`, a payment marks the invoice `paid`, a
correction adds a comment of kind `correction` to the ticket. For a case not
yet resolved, nothing special is needed: the ordinary rules below, applied to
the current facts, give the right answer, and a correction comment overrides
the invoice cited in the ticket body. For a case already resolved, the entry
may require a corrective action, filed with `desk_escalation_amend` against
the resolved escalation (never by resolving it again):

| Entry kind | Applies when the case was already resolved as | Amendment action | Side effects |
|---|---|---|---|
| `chargeback_opened` on invoice X | `REFUNDED` with a refund on X | `chargeback_after_refund` | `tracker_issue_create` in `FIN`, kind `chargeback_after_refund`; message `hold` |
| `customer_withdrew` on ticket T | `REFUNDED` | `withdrawn_after_refund` | `tracker_issue_create` in `FIN`, kind `refund_recall_review`; no message |
| `invoice_paid` on invoice X | `NEEDS_INFO` where the ticket cites X | `refund_now` | refund rules 5 to 7 below on X at the current clock, with the refund and message they produce; the amendment is filed even when those rules yield no refund, carrying only the `no_refund` message |
| `invoice_corrected` on ticket T to invoice X | `NEEDS_INFO` | `refund_now` if X belongs to the account and is `paid`, otherwise `needs_info_again` | `refund_now`: rules 5 to 7 on X at the current clock; `needs_info_again`: message `needs_info` |

A case resolved with any other code needs no amendment for that entry. Each
amendment advances the clock like a resolution. Pass the ids of the refund,
issue and message the amendment produced.

A case is judged on the facts at the moment it is resolved. Do a case's side
effects, ticket close and resolution together, before resolving or amending
anything else, because each resolution or amendment moves the clock and may
release facts that change the answer for a case left half done.

## The workflow, per escalation

1. Read the escalation (`desk_escalation_get`) and its ticket (`helpdesk_ticket_get`).
2. Find the customer account by the ticket's requester email
   (`accounts_customers_search` with `email`, then `accounts_customer_get`).
   Names are not unique; the email is.
3. Decide the resolution code with the rules below, in this order.
4. Perform the side effects the code requires, then close the ticket with
   `helpdesk_ticket_close` using the same code, then resolve the escalation with
   `desk_escalation_resolve`, passing the ids of the refund, finance issue and
   customer message it produced.
5. Pull the feed and file any amendments it requires.

## Resolution rules (first matching rule wins)

| Order | Condition | Code | Side effects |
|---|---|---|---|
| 1 | The ticket is already closed and `closed_by` is `customer` | `WITHDRAWN` | none: no message, no refund, no issue, no ticket close |
| 2 | The account has the flag `chargeback_pending` | `CHARGEBACK_HOLD` | `tracker_issue_create` in project `FIN`, kind `chargeback`; message `hold` |
| 3 | The invoice the ticket cites does not exist, belongs to another account, or is not `paid` | `NEEDS_INFO` | message `needs_info` |
| 4 | The account's plan is `enterprise` | `REFERRED_FINANCE` | `tracker_issue_create` in project `FIN`, kind `refund_review`; message `referred` |
| 5 | The invoice already has a refund (`billing_refunds_list`) | `NO_REFUND_DUE` | message `no_refund` |
| 6 | The refund amount computed below is zero | `NO_REFUND_DUE` | message `no_refund` |
| 7 | Otherwise | `REFUNDED` | `billing_refund_create` for the computed amount; message `refunded` with `vars.amount` set to the refund amount as text |

The ticket cites exactly one invoice id of the form `INV-nnnn` in its body; a
later comment of kind `correction` replaces it. Finance issues carry the
ticket id in `ticket_id`.

## Refund amount

"Today" is the date of the desk clock at the moment the refund is created.
Amounts are whole cents, rounded down.

- `monthly` plan: unused days are the calendar days after today up to and
  excluding `period_end`. Refund = invoice amount × unused days ÷ days in the
  period (`period_end` − `period_start`).
- `annual` plan: the period is divided into twelve months on the invoice's
  own grid (`period_start`, `period_start` + 1 month, ...; a start day past
  the 28th counts as the 28th). A month is unused when it starts after today
  and ends on or before `period_end`. Refund = invoice amount × unused months
  ÷ 12.

## Customer messages

One message per resolved escalation, except `WITHDRAWN`, which sends none,
plus the message an amendment prescribes. Send it through the account's
`contact_channel`: `email_send` for `email`, `chat_post` for `chat`. Pass the
template name from the tables; the gateway renders it in the account's
locale. Do not send free-form mail.

## Definition of done

The queue is empty, the feed has been pulled after the last resolution and
every amendment it required has been filed, every escalation is resolved
with the right code and the ids of the side effects it produced, every
refund is on the billing ledger for exactly the amount computed at its own
clock reading, every message went through the right channel with the right
template, every finance issue exists in project `FIN`, and every ticket that
was open is closed with the resolution code. Nothing else was refunded,
credited, sent, posted, drafted, filed or amended, on any ledger, current or
legacy.
