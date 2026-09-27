"""Unit tests for desk-shift-feed's gateway server (dispatch/State): the desk
clock, the event feed and its cursor semantics, escalation amendments, the
refund idempotency key format, the runbook's stale numbers versus the
gateway's real ones, and the verifier's rule engine (tests/rules.py) replayed
over both the oracle's own timeline and hand-built timelines that exercise
amendment paths the oracle's queue order never reaches.

These run directly against the in-process gateway (server.dispatch), never
over the wire.
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASK_DIR = ROOT / "tasks/desk-shift-feed"
GATEWAY_DIR = TASK_DIR / "environment/gateway"
TESTS_DIR = TASK_DIR / "tests"
SOLUTION_DIR = TASK_DIR / "solution"
TOOLS_FEED_DIR = Path(__file__).resolve().parent

# server.py reads DESKGATE_STATE at import time, so this must be set first.
_STATE_PATH = Path(tempfile.mkdtemp(prefix="deskgate-feed-test-")) / "state.json"
os.environ["DESKGATE_STATE"] = str(_STATE_PATH)

for _p in (GATEWAY_DIR, TESTS_DIR, SOLUTION_DIR, TOOLS_FEED_DIR):
    sys.path.insert(0, str(_p))

import server  # noqa: E402  (gateway under test)
import rules  # noqa: E402  (verifier's rule engine)
import test_outputs  # noqa: E402  (the actual verifier suite, reused for its _refs_match helper)
import work_queue  # noqa: E402  (oracle solution)
import generate  # noqa: E402  (seed generator)

REAL_SEED_PATH = TESTS_DIR / "seed.json"


def load_seed() -> dict:
    """A fresh, mutation-safe copy of the real task seed."""
    return json.loads(REAL_SEED_PATH.read_text())


def new_state(seed: dict) -> "server.State":
    return server.State(copy.deepcopy(seed))


def ok(state: "server.State", name: str, **args) -> dict:
    """Dispatch a call that must succeed and return its result payload."""
    reply = server.dispatch(state, name, args)
    assert reply["ok"], (name, args, reply)
    return reply["result"]


# ---- 1. tool catalog --------------------------------------------------------

def test_tool_count_names_unique_new_tools_present_no_ys_typos():
    """If this breaks, the MCP catalog silently gained/lost tools (an agent
    would see a different toolset than the task was designed around), two
    tools collide on the same name, one of the three new feed/clock/amend
    tools this task adds has gone missing, or a pluralisation typo ('ys_' /
    trailing 'ys') slipped into the noise catalog."""
    names = [t.name for t in server.MCP_TOOLS]
    assert len(server.MCP_TOOLS) == 268
    assert len(names) == len(set(names))
    for tool_name in ("desk_feed_pull", "desk_escalation_amend", "desk_clock"):
        assert tool_name in server.HANDLERS, tool_name
    assert not [n for n in names if "ys_" in n or n.endswith("ys")]


# ---- 2. desk clock -----------------------------------------------------------

def test_clock_advances_six_hours_on_resolve_and_amend_not_on_reads():
    """The runbook says the clock advances four hours; the gateway is right
    at six (seed clock_advance_hours). If resolve/amend ticked the wrong
    amount, or a plain read ticked the clock at all, every refund-proration
    and event-release computation downstream would land on the wrong date."""
    st = new_state(load_seed())
    assert st.clock_text() == "2026-09-14T09:00"

    clk = ok(st, "desk_clock")
    assert clk["now"] == "2026-09-14T09:00"
    assert clk["advance_hours"] == 6

    ok(st, "desk_queue_list")
    ok(st, "helpdesk_ticket_get", id="T-701")
    assert st.clock_text() == "2026-09-14T09:00", "a read must never advance the clock"

    resolved = ok(st, "desk_escalation_resolve", id="E-02", code="NO_REFUND_DUE")
    assert resolved["clock_now"] == "2026-09-14T15:00"
    assert st.clock_text() == "2026-09-14T15:00"

    refund = ok(st, "billing_refund_create", invoice_id="INV-2001", amount_cents=500,
                idempotency_key="E-01:INV-2001")["refund"]
    assert st.clock_text() == "2026-09-14T15:00", "a refund itself must not advance the clock"

    amended = ok(st, "desk_escalation_resolve", id="E-01", code="REFUNDED", refund_id=refund["id"])
    assert amended["clock_now"] == "2026-09-14T21:00"
    amend = ok(st, "desk_escalation_amend", id="E-01", action="withdrawn_after_refund")
    assert amend["clock_now"] == "2026-09-15T03:00"


# ---- 3. feed release and cursor semantics ------------------------------------

def test_feed_release_and_cursor_semantics():
    """The feed must stay silent until a fact's release time is reached, then
    release exactly the due entries once and apply their backend side
    effects (chargeback flag, ticket status), and a re-pull at the returned
    cursor must be a no-op. If release timing, released_clock, the backend
    mutation, or cursor filtering were wrong, an agent (and the verifier)
    would judge cases against stale or duplicated facts."""
    st = new_state(load_seed())

    before = ok(st, "desk_feed_pull", cursor=0)
    assert before["entries"] == []
    assert before["clock_now"] == "2026-09-14T09:00"

    resolved = ok(st, "desk_escalation_resolve", id="E-02", code="NO_REFUND_DUE")
    assert resolved["clock_now"] == "2026-09-14T15:00"

    pulled = ok(st, "desk_feed_pull", cursor=0)
    assert [e["seq"] for e in pulled["entries"]] == [1, 2]
    assert all(e["released_clock"] == "2026-09-14T15:00" for e in pulled["entries"])
    assert pulled["cursor"] == 2

    assert "chargeback_pending" in st.customers["C-1001"]["flags"], "event 1 must flag INV-2001's account"
    assert st.tickets["T-707"]["status"] == "closed" and st.tickets["T-707"]["closed_by"] == "customer", \
        "T-707 was already closed by the customer; a chargeback on its invoice must not touch ticket status"

    again = ok(st, "desk_feed_pull", cursor=2)
    assert again["entries"] == []
    assert again["cursor"] == 2


# ---- 4. refund key format and strictly increasing op numbers ----------------

def test_refund_key_format_and_op_numbers_strictly_increase():
    """billing_refund_create's idempotency key must be <escalation>:<invoice>,
    not a bare escalation id. And every op-stamped record the gateway writes
    (message, issue, refund, resolution, amendment, feed release) must draw
    from one global, strictly increasing counter: the verifier's timeline
    replay (tests/rules.py) orders facts by this number, so a shared or
    out-of-order op would let it judge escalations against the wrong facts."""
    st = new_state(load_seed())

    bad = server.dispatch(st, "billing_refund_create",
                           {"invoice_id": "INV-2001", "amount_cents": 100, "idempotency_key": "E-01"})
    assert bad["ok"] is False and bad["error"] == "E_IK_FORMAT"

    msg = ok(st, "email_send", customer_id="C-1001", template="needs_info")["message"]
    issue = ok(st, "tracker_issue_create", project="FIN", kind="chargeback", title="t", ticket_id="T-701")["issue"]
    refund = ok(st, "billing_refund_create", invoice_id="INV-2001", amount_cents=1000,
                idempotency_key="E-01:INV-2001")["refund"]
    ok(st, "desk_escalation_resolve", id="E-05", code="NO_REFUND_DUE")
    ok(st, "desk_escalation_resolve", id="E-06", code="NO_REFUND_DUE")
    amend = ok(st, "desk_escalation_amend", id="E-06", action="needs_info_again")
    # this pull's release_due_events fires at clock 21:00, releasing events 1-2 (15:00) and 3-4 (03:00 next day is not yet due)
    ok(st, "desk_feed_pull", cursor=0)
    event_ops = sorted(e["released_op"] for e in st.events if e["released"])

    all_ops = [msg["op"], issue["op"], refund["op"], st.escalations["E-05"]["op"],
               st.escalations["E-06"]["op"], st.escalations["E-06"]["amendments"][0]["op"], *event_ops]
    assert amend["amended"] == "E-06"
    assert sorted(all_ops) == list(range(1, len(all_ops) + 1)), all_ops


# ---- 5. templates: runbook says 'hold', the gateway wants 'dispute_hold' -----

def test_template_hold_is_unknown_dispute_hold_is_the_real_name():
    """The runbook's amendment table calls the dispute-hold template 'hold';
    the gateway only knows 'dispute_hold'. If the gateway ever accepted the
    runbook's stale name, or stopped listing the real one in E_TEMPLATE's
    error, an agent following the runbook literally would silently send the
    wrong (or no) message."""
    st = new_state(load_seed())
    bad = server.dispatch(st, "email_send", {"customer_id": "C-1001", "template": "hold"})
    assert bad["ok"] is False and bad["error"] == "E_TEMPLATE"
    assert "dispute_hold" in bad["templates"]
    assert "hold" not in bad["templates"]

    good = ok(st, "email_send", customer_id="C-1001", template="dispute_hold")
    assert good["message"]["template"] == "dispute_hold"


# ---- 6. amend rules ----------------------------------------------------------

def test_amend_rules_not_resolved_unknown_action_duplicate_unknown_ref_success():
    """Every guard on desk_escalation_amend, checked in the order the handler
    applies them. If any guard were missing or misordered, an agent could
    amend an unresolved case, invent an action, double-file the same
    corrective action, or attach a refund/issue/message id the ledgers never
    issued."""
    st = new_state(load_seed())

    unresolved = server.dispatch(st, "desk_escalation_amend", {"id": "E-02", "action": "refund_now"})
    assert unresolved["ok"] is False and unresolved["error"] == "E_NOT_RESOLVED"

    ok(st, "desk_escalation_resolve", id="E-06", code="NO_REFUND_DUE")

    unknown_action = server.dispatch(st, "desk_escalation_amend", {"id": "E-06", "action": "not_a_real_action"})
    assert unknown_action["ok"] is False and unknown_action["error"] == "E_ACTION"

    unknown_ref = server.dispatch(st, "desk_escalation_amend",
                                   {"id": "E-06", "action": "refund_now", "issue_id": "FAKE-1"})
    assert unknown_ref["ok"] is False and unknown_ref["error"] == "E_UNKNOWN_REF"

    success = ok(st, "desk_escalation_amend", id="E-06", action="needs_info_again")
    assert success == {"amended": "E-06", "action": "needs_info_again", "clock_now": "2026-09-14T21:00"}
    recorded = st.escalations["E-06"]["amendments"][0]
    assert recorded["action"] == "needs_info_again"
    assert recorded["refund_id"] is None and recorded["issue_id"] is None and recorded["message_id"] is None
    assert recorded["clock_at"] == "2026-09-14T15:00"
    assert isinstance(recorded["op"], int)

    duplicate = server.dispatch(st, "desk_escalation_amend", {"id": "E-06", "action": "needs_info_again"})
    assert duplicate["ok"] is False and duplicate["error"] == "E_AMENDED"


# ---- 7. budget is 300, not the runbook's 240 ---------------------------------

def test_budget_is_300_not_the_runbooks_240():
    """The runbook says the run budget is 240 calls; the seed (and the
    gateway that enforces it) says 300. If the gateway silently used the
    stale number, a correct desk shift within the real budget would be cut
    off early with E_BUDGET on the 241st call instead of the 301st."""
    st = new_state(load_seed())
    assert st.budget == 300
    for _ in range(300):
        assert server.dispatch(st, "desk_clock", {})["ok"] is True
    over = server.dispatch(st, "desk_clock", {})
    assert over["ok"] is False and over["error"] == "E_BUDGET"
    assert st.calls["total"] == 301


# ---- 8. oracle timeline: queue order ------------------------------------------

class _Adapter:
    """Adapts server.dispatch to the GatewayClient.call(name, **args) shape
    the oracle solution (solution/work_queue.py) expects: same reply
    envelope, no network."""

    def __init__(self, state: "server.State"):
        self.state = state

    def call(self, name: str, **args) -> dict:
        return server.dispatch(self.state, name, args)


def test_oracle_timeline_matches_verifier_on_the_real_queue_order(tmp_path):
    """Run the oracle solution's own Desk class in-process against the
    gateway (no HTTP), then grade the resulting state.json two ways: with
    the verifier's rule engine directly (tests/rules.py) and by running the
    actual tests/test_outputs.py suite against a dump of the state. If the
    oracle and the verifier ever disagreed on the queue's natural order, the
    task would be ungradeable for a correct agent."""
    seed = load_seed()
    st = new_state(seed)

    # billing_* shares a rolling rate limit keyed on time.monotonic(); advance
    # it far past the window on every check so the oracle's real retry loop
    # never actually has to sleep.
    counter = {"t": 0.0}

    def fake_monotonic():
        counter["t"] += 100.0
        return counter["t"]

    real_monotonic = server.time.monotonic
    server.time.monotonic = fake_monotonic
    try:
        work_queue.Desk(_Adapter(st)).run()
    finally:
        server.time.monotonic = real_monotonic

    snapshot = st.snapshot()
    expected = rules.expected_all(seed, snapshot)
    for eid, esc in st.escalations.items():
        assert esc["resolved"], f"{eid} left unresolved by the oracle"
        assert esc["code"] == expected["resolutions"][eid]["code"], \
            f"{eid}: oracle resolved {esc['code']}, verifier expected {expected['resolutions'][eid]['code']}"
    assert len(expected["resolutions"]) == 18
    assert all(ev["released"] for ev in st.events)

    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(snapshot))
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(TESTS_DIR / "test_outputs.py")],
        cwd=str(TESTS_DIR), env={**os.environ, "STATE_JSON": str(state_path)},
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


# ---- 9. hand-built timelines: amendment paths the oracle's order never hits --

def test_amendment_timeline_needs_info_resolved_before_invoice_paid_then_refund_now(tmp_path):
    """E-11's invoice (INV-2011) is unpaid when the shift starts, so resolving
    it immediately gives NEEDS_INFO. The oracle never sees this order because
    it works the queue front-to-back and only reaches the invoice_paid event
    (op-wise) after several other resolutions. Drive it by hand: resolve
    E-11 first, grind the clock forward on filler escalations until the
    invoice_paid event (at +66h, i.e. after 11 six-hour ticks) releases, then
    file the refund_now amendment the runbook requires. If the verifier's
    amendment math didn't track op ordering and the refund's own clock
    reading correctly, this exact path would either wrongly demand or
    wrongly skip the amendment, and it would not catch a wrong refund
    amount."""
    seed = load_seed()
    st = new_state(seed)

    msg = ok(st, "email_send", customer_id="C-1011", template="needs_info")["message"]
    ok(st, "desk_escalation_resolve", id="E-11", code="NEEDS_INFO", message_id=msg["id"])
    ok(st, "helpdesk_ticket_close", id="T-711", code="NEEDS_INFO")
    assert st.clock_text() == "2026-09-14T15:00"

    # 10 more six-hour ticks: 09:00 + 11*6h = 2026-09-17T03:00, exactly event 7's release time.
    for eid in ("E-01", "E-02", "E-03", "E-04", "E-05", "E-06", "E-07", "E-08", "E-09", "E-10"):
        ok(st, "desk_escalation_resolve", id=eid, code="NO_REFUND_DUE")
    assert st.clock_text() == "2026-09-17T03:00"

    invoice = ok(st, "billing_invoice_get", id="INV-2011")  # this call's release_due_events fires event 7 first
    assert invoice["status"] == "paid", "event 7 (invoice_paid) must have released by now"
    event7 = next(e for e in st.events if e["seq"] == 7)
    assert event7["released"] and event7["released_op"] > st.escalations["E-11"]["op"]

    today = date.fromisoformat(st.clock_text()[:10])
    amount = rules.refund_amount(today, "monthly", invoice)
    refund = ok(st, "billing_refund_create", invoice_id="INV-2011", amount_cents=amount,
                idempotency_key="E-11:INV-2011")["refund"]
    refunded_msg = ok(st, "email_send", customer_id="C-1011", template="refunded",
                       vars={"amount": f"USD {amount // 100}.{amount % 100:02d}"})["message"]
    ok(st, "desk_escalation_amend", id="E-11", action="refund_now",
       refund_id=refund["id"], message_id=refunded_msg["id"])

    timeline = rules.Timeline(seed, st.snapshot())
    expected = rules.expected_amendments(timeline)["E-11"]
    assert expected == [{
        "action": "refund_now",
        "refund": {"invoice_id": "INV-2011", "amount_cents": amount},
        "issue": None,
        "message": {"customer_id": "C-1011", "channel": "email", "template": "refunded", "locale": "en-US"},
    }]
    filed = st.escalations["E-11"]["amendments"][0]
    test_outputs._refs_match(timeline, filed, expected[0], "E-11/refund_now")  # must not raise

    # Now show the verifier would reject a wrong refund amount on the same path.
    seed2 = load_seed()
    st2 = new_state(seed2)
    msg2 = ok(st2, "email_send", customer_id="C-1011", template="needs_info")["message"]
    ok(st2, "desk_escalation_resolve", id="E-11", code="NEEDS_INFO", message_id=msg2["id"])
    for eid in ("E-01", "E-02", "E-03", "E-04", "E-05", "E-06", "E-07", "E-08", "E-09", "E-10"):
        ok(st2, "desk_escalation_resolve", id=eid, code="NO_REFUND_DUE")
    wrong_invoice = ok(st2, "billing_invoice_get", id="INV-2011")
    wrong_amount = amount + 500
    assert wrong_amount <= wrong_invoice["amount_cents"], "the wrong amount must still be a legal refund"
    wrong_refund = ok(st2, "billing_refund_create", invoice_id="INV-2011", amount_cents=wrong_amount,
                       idempotency_key="E-11:INV-2011")["refund"]
    wrong_msg = ok(st2, "email_send", customer_id="C-1011", template="refunded", vars={"amount": "x"})["message"]
    ok(st2, "desk_escalation_amend", id="E-11", action="refund_now",
       refund_id=wrong_refund["id"], message_id=wrong_msg["id"])
    timeline2 = rules.Timeline(seed2, st2.snapshot())
    expected2 = rules.expected_amendments(timeline2)["E-11"][0]
    filed2 = st2.escalations["E-11"]["amendments"][0]
    try:
        test_outputs._refs_match(timeline2, filed2, expected2, "E-11/refund_now")
    except AssertionError:
        pass
    else:
        raise AssertionError("verifier logic accepted a refund_now amendment with the wrong refund amount")


def test_amendment_timeline_chargeback_after_refund_and_withdrawn_gets_none():
    """E-01 is resolved REFUNDED before event 1 (a chargeback on its own
    invoice) releases: the runbook then requires chargeback_after_refund.
    E-07's ticket is resolved WITHDRAWN even though event 2 opens a
    chargeback on its invoice too -- WITHDRAWN never produced a refund, so
    no amendment is due there. If the amendment rule keyed off the event
    alone instead of the escalation's own resolution code, E-07 would
    wrongly be made to carry an amendment it never needed."""
    seed = load_seed()
    st = new_state(seed)

    invoice = ok(st, "billing_invoice_get", id="INV-2001")
    amount = rules.refund_amount(date.fromisoformat(st.clock_text()[:10]), "monthly", invoice)
    refund = ok(st, "billing_refund_create", invoice_id="INV-2001", amount_cents=amount,
                idempotency_key="E-01:INV-2001")["refund"]
    msg = ok(st, "email_send", customer_id="C-1001", template="refunded",
             vars={"amount": f"USD {amount // 100}.{amount % 100:02d}"})["message"]
    ok(st, "helpdesk_ticket_close", id="T-701", code="REFUNDED")
    ok(st, "desk_escalation_resolve", id="E-01", code="REFUNDED", refund_id=refund["id"], message_id=msg["id"])

    ok(st, "desk_escalation_resolve", id="E-07", code="WITHDRAWN")  # ticket was already closed by the customer

    pulled = ok(st, "desk_feed_pull", cursor=0)
    assert {e["seq"] for e in pulled["entries"]} >= {1, 2}, "both chargeback events must have released by now"

    timeline = rules.Timeline(seed, st.snapshot())
    expected = rules.expected_amendments(timeline)
    assert expected["E-01"] == [{
        "action": "chargeback_after_refund",
        "refund": None,
        "issue": {"project": "FIN", "kind": "chargeback_after_refund", "ticket_id": "T-701"},
        "message": {"customer_id": "C-1001", "channel": "email", "template": "dispute_hold", "locale": "en-US"},
    }]
    assert expected["E-07"] == []


# ---- 10. seed copies identical -----------------------------------------------

def test_seed_copies_identical_to_each_other_and_the_generator():
    """The gateway loads environment/gateway/seed.json and the verifier
    grades against tests/seed.json. If the two ever drifted, or either
    drifted from the generator that is supposed to produce both, the agent
    and the verifier would be working from different worlds."""
    tests_seed = load_seed()
    env_seed = json.loads((GATEWAY_DIR / "seed.json").read_text())
    assert tests_seed == env_seed
    assert tests_seed == generate.build()


# ---- 11. refund math and add_months agree between the verifier and oracle ---

def test_refund_amount_and_add_months_agree_between_rules_and_oracle():
    """tests/rules.py (the verifier) and solution/work_queue.py (the oracle)
    implement the refund arithmetic independently. If they disagreed on any
    invoice or on how add_months clamps a late start day, the task would be
    ungradeable: either no correct agent run could pass, or the verifier
    would be silently wrong about what 'correct' means."""
    seed = load_seed()
    today = date.fromisoformat(seed["clock_start"][:10])
    for inv in seed["invoices"]:
        for plan in ("monthly", "annual"):
            assert rules.refund_amount(today, plan, inv) == work_queue.refund_for(today, plan, inv), (inv["id"], plan)

    for day in (1, 15, 28, 29, 30, 31):
        d = date(2026, 1, day)
        for n in (1, 2, 11, 12):
            assert rules.add_months(d, n) == work_queue.add_months(d, n)
    assert rules.add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)


def make_state() -> "server.State":
    return new_state(load_seed())


def resolve_needs_info(st: "server.State", eid: str) -> None:
    """Resolve an escalation as NEEDS_INFO with its message and ticket close,
    the way the runbook prescribes, without deciding anything else."""
    d = lambda n, **a: server.dispatch(st, n, a)["result"]
    esc = d("desk_escalation_get", id=eid)
    ticket = d("helpdesk_ticket_get", id=esc["ticket_id"])
    cust = d("accounts_customers_search", email=ticket["requester_email"])["customers"][0]
    tool = "email_send" if cust["contact_channel"] == "email" else "chat_post"
    msg = d(tool, customer_id=cust["id"], template="needs_info")["message"]["id"]
    d("helpdesk_ticket_close", id=ticket["id"], code="NEEDS_INFO")
    d("desk_escalation_resolve", id=eid, code="NEEDS_INFO", message_id=msg)


# ---- regression tests from the review gate ---------------------------------

def test_refund_now_amendment_expected_even_when_no_refund_is_due():
    """When a late correction points at an invoice the follow-up already
    refunded, the runbook still requires a refund_now amendment carrying
    only the no_refund message. The runbook table now says so, and the
    verifier must expect exactly that, not nothing."""
    seed = load_seed()
    st = make_state()
    d = lambda n, **a: server.dispatch(st, n, a)
    # E-03 resolved NEEDS_INFO first (wrong invoice cited), then E-13 is not
    # available until E-03 resolves; refund INV-2003 through E-13 before the
    # correction on T-703 releases at +18 h.
    resolve_needs_info(st, "E-03")
    assert "E-13" in [e["id"] for e in d("desk_queue_list")["result"]["escalations"]]
    refund = d("billing_refund_create", invoice_id="INV-2003", amount_cents=100, idempotency_key="E-13:INV-2003")["result"]["refund"]
    msg = d("email_send", customer_id="C-1003", template="refunded", vars={"amount": "USD 1.00"})["result"]["message"]["id"]
    d("helpdesk_ticket_close", id="T-713", code="REFUNDED")
    d("desk_escalation_resolve", id="E-13", code="REFUNDED", refund_id=refund["id"], message_id=msg)
    resolve_needs_info(st, "E-11")  # third tick: clock reaches +18 h, correction releases on the next call
    d("desk_clock")
    assert any(ev["kind"] == "invoice_corrected" and ev["released"] for ev in st.events)
    want = rules.expected_amendments(rules.Timeline(seed, st.snapshot()))["E-03"]
    assert [w["action"] for w in want] == ["refund_now"]
    assert want[0]["refund"] is None and want[0]["message"]["template"] == "no_refund"
def test_idempotent_replay_ignores_the_reason_text():
    """The replay comparison included the free-text reason, so a retry with
    a reworded reason was refused as a conflict although the same money was
    meant. Replay now keys on invoice and amount only; a different amount
    is still a conflict."""
    st = make_state()
    first = server.dispatch(st, "billing_refund_create", {"invoice_id": "INV-2001", "amount_cents": 2613, "idempotency_key": "E-01:INV-2001", "reason": "escalation E-01"})
    again = server.dispatch(st, "billing_refund_create", {"invoice_id": "INV-2001", "amount_cents": 2613, "idempotency_key": "E-01:INV-2001", "reason": "retry"})
    assert again["ok"] and again["result"]["replayed"] and again["result"]["refund"]["id"] == first["result"]["refund"]["id"]
    assert len(st.refunds) == 2  # seed refund plus one
    conflict = server.dispatch(st, "billing_refund_create", {"invoice_id": "INV-2001", "amount_cents": 1, "idempotency_key": "E-01:INV-2001"})
    assert conflict["ok"] is False and conflict["error"] == "E_IDEMPOTENCY_CONFLICT"


