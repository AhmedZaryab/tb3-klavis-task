"""Unit tests for the support-desk-gateway's gateway server (dispatch/State),
its verifier rule engine, and the seed data pipeline.

These run directly against the in-process gateway (server.dispatch), never
over the wire, and cover the gateway-wide contracts the runbook and the
verifier depend on: the run budget, the billing rate limit, refund
idempotency, shadow ledgers that must never touch real money, escalation
finality and follow-up release, messaging, ticket close semantics, customer
search, on-disk persistence, the verifier's rule engine agreeing with the
oracle solution's own math, the two seed copies staying identical to the
generator, and the noise catalog staying inert.
"""

import copy
import json
import os
import sys
import tempfile
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GATEWAY_DIR = ROOT / "tasks/support-desk-gateway/environment/gateway"
TESTS_DIR = ROOT / "tasks/support-desk-gateway/tests"
SOLUTION_DIR = ROOT / "tasks/support-desk-gateway/solution"
TOOLS_DESK_DIR = Path(__file__).resolve().parent

# server.py reads DESKGATE_STATE at import time, so this must be set first.
_STATE_PATH = Path(tempfile.mkdtemp(prefix="deskgate-test-")) / "state.json"
os.environ["DESKGATE_STATE"] = str(_STATE_PATH)

for _p in (GATEWAY_DIR, TESTS_DIR, SOLUTION_DIR, TOOLS_DESK_DIR):
    sys.path.insert(0, str(_p))

import server  # noqa: E402  (gateway under test)
import rules  # noqa: E402  (verifier's rule engine)
import work_queue  # noqa: E402  (oracle solution's own refund math)
import generate  # noqa: E402  (seed generator)

REAL_SEED_PATH = TESTS_DIR / "seed.json"


def load_seed() -> dict:
    """A fresh, mutation-safe copy of the real task seed."""
    return json.loads(REAL_SEED_PATH.read_text())


def minimal_seed(**overrides) -> dict:
    """The smallest seed State() will accept, for tests that only exercise
    gateway-wide mechanics (budget, rate limit) and don't need real data."""
    seed = {
        "clock": "2026-01-01",
        "budget": 1000,
        "rate_limit": {"prefix": "billing_", "calls": 6, "window_s": 10},
        "customers": [],
        "invoices": [],
        "tickets": [],
        "escalations": [],
        "refunds": [],
        "resolution_codes": ["REFUNDED", "REFERRED_FINANCE", "CHARGEBACK_HOLD",
                              "NEEDS_INFO", "NO_REFUND_DUE", "WITHDRAWN"],
        "templates": ["refunded", "referred", "hold", "needs_info", "no_refund"],
    }
    seed.update(overrides)
    return seed


def new_state(seed: dict) -> "server.State":
    return server.State(copy.deepcopy(seed))


# ---- 1. tool catalog --------------------------------------------------------

def test_tool_count_and_names_unique_and_runbook_tools_present():
    """If this breaks, either the MCP catalog silently gained/lost tools (an
    agent would see a different toolset than the task was designed around),
    two tools collide on the same name, or a tool the runbook's workflow
    depends on has gone missing from the gateway."""
    names = [t.name for t in server.MCP_TOOLS]
    assert len(server.MCP_TOOLS) == 266
    assert len(names) == len(set(names))
    runbook_tools = [
        "desk_clock", "desk_queue_list", "desk_escalation_get", "desk_escalation_resolve",
        "helpdesk_ticket_get", "accounts_customers_search", "accounts_customer_get",
        "billing_refunds_list", "billing_refund_create", "tracker_issue_create",
        "email_send", "chat_post", "helpdesk_ticket_close",
    ]
    for tool_name in runbook_tools:
        assert tool_name in server.HANDLERS, tool_name


# ---- 2. budget --------------------------------------------------------------

def test_budget_exhaustion_counts_errors():
    """If the budget didn't count failed calls, or didn't cut off exactly
    after `budget` calls, an agent could get free extra calls (or legitimate
    calls could be cut off early) by triggering errors."""
    st = new_state(minimal_seed(budget=2))
    ok1 = server.dispatch(st, "desk_clock", {})
    assert ok1["ok"] is True

    err1 = server.dispatch(st, "no_such_tool", {})  # call #2: an error, still within budget
    assert err1["ok"] is False and err1["error"] == "E_NO_TOOL"
    assert st.calls["budget_exhausted"] is False

    over = server.dispatch(st, "desk_clock", {})  # call #3: exceeds budget of 2
    assert over["ok"] is False and over["error"] == "E_BUDGET"
    assert st.calls["budget_exhausted"] is True
    assert st.calls["total"] == 3


# ---- 3. billing rate limit ---------------------------------------------------

def test_billing_rate_limit_and_recovery(monkeypatch):
    """If the rolling billing rate limit didn't trip at the right count, gave
    no retry_after_s, leaked onto non-billing tools, or never recovered after
    the window, an agent could hammer billing without consequence (or get
    wrongly throttled forever)."""
    st = new_state(load_seed())
    results = [server.dispatch(st, "billing_invoice_get", {"id": "INV-2001"}) for _ in range(7)]
    for r in results[:6]:
        assert r["ok"] is True
    assert results[6]["ok"] is False
    assert results[6]["error"] == "E_RATE_LIMIT"
    assert results[6]["retry_after_s"] >= 1

    unaffected = server.dispatch(st, "desk_clock", {})
    assert unaffected["ok"] is True

    real_monotonic = time.monotonic  # server.time IS the time module: capture before patching it
    monkeypatch.setattr(server.time, "monotonic", lambda: real_monotonic() + 11)
    recovered = server.dispatch(st, "billing_invoice_get", {"id": "INV-2001"})
    assert recovered["ok"] is True


# ---- 4. refund idempotency ---------------------------------------------------

def test_refund_idempotency_and_validation():
    """If idempotency replay, conflict detection, one-refund-per-invoice, the
    amount bound, or the paid-invoice check broke, a retried refund could
    double-move money or refund an invoice that was never paid."""
    st = new_state(load_seed())

    r1 = server.dispatch(st, "billing_refund_create",
                          {"invoice_id": "INV-2001", "amount_cents": 1000, "idempotency_key": "k1"})
    assert r1["ok"] is True and r1["result"]["replayed"] is False
    refund_id = r1["result"]["refund"]["id"]

    r2 = server.dispatch(st, "billing_refund_create",
                          {"invoice_id": "INV-2001", "amount_cents": 1000, "idempotency_key": "k1"})
    assert r2["ok"] is True and r2["result"]["replayed"] is True
    assert r2["result"]["refund"]["id"] == refund_id
    assert sum(1 for r in st.refunds if r["invoice_id"] == "INV-2001") == 1

    r3 = server.dispatch(st, "billing_refund_create",
                          {"invoice_id": "INV-2001", "amount_cents": 2000, "idempotency_key": "k1"})
    assert r3["ok"] is False and r3["error"] == "E_IDEMPOTENCY_CONFLICT"

    r4 = server.dispatch(st, "billing_refund_create",
                          {"invoice_id": "INV-2001", "amount_cents": 500, "idempotency_key": "k2"})
    assert r4["ok"] is False and r4["error"] == "E_ALREADY_REFUNDED"

    r5 = server.dispatch(st, "billing_refund_create",
                          {"invoice_id": "INV-2002", "amount_cents": 999999, "idempotency_key": "k3"})
    assert r5["ok"] is False and r5["error"] == "E_AMOUNT"

    r6 = server.dispatch(st, "billing_refund_create",
                          {"invoice_id": "INV-2011", "amount_cents": 100, "idempotency_key": "k4"})
    assert r6["ok"] is False and r6["error"] == "E_INVOICE_STATUS"


# ---- 5. shadow ledgers -------------------------------------------------------

def test_shadow_ledgers_never_touch_the_real_refund_ledger():
    """If a legacy/sandbox/credit-note write ever landed on the real refunds
    ledger (or vice versa), the verifier's exact-ledger check could be fooled
    into crediting money that never moved, or an agent could dodge the
    one-refund-per-invoice rule through a side door."""
    st = new_state(load_seed())
    before = len(st.refunds)

    r1 = server.dispatch(st, "billing_refunds_issue_v1", {"invoice_id": "INV-2001", "amount_cents": 500})
    r2 = server.dispatch(st, "billing_sandbox_refund_create",
                          {"invoice_id": "INV-2001", "amount_cents": 500, "idempotency_key": "x"})
    r3 = server.dispatch(st, "billing_credit_note_create", {"invoice_id": "INV-2001", "amount_cents": 500})

    assert r1["ok"] is True and r1["result"]["ledger"] == "legacy"
    assert r2["ok"] is True and r2["result"]["ledger"] == "sandbox"
    assert r3["ok"] is True and "credit_note" in r3["result"]

    assert len(st.legacy_refunds) == 1
    assert len(st.sandbox_refunds) == 1
    assert len(st.credit_notes) == 1
    assert len(st.refunds) == before


# ---- 6. resolve is final, releases follow-ups --------------------------------

def test_resolve_is_final_and_releases_followups():
    """If resolve could be reopened, didn't release the right follow-ups, or
    accepted an unknown code / a ref not on its real ledger, the agent could
    silently corrupt the queue or attach a fabricated refund/issue/message id
    to an escalation."""
    st = new_state(load_seed())

    queue_before = server.dispatch(st, "desk_queue_list", {})["result"]
    assert not any(e["id"] == "E-13" for e in queue_before["escalations"])

    hidden = server.dispatch(st, "desk_escalation_get", {"id": "E-13"})
    assert hidden["ok"] is False and hidden["error"] == "E_NOT_FOUND"

    msg = server.dispatch(st, "email_send", {"customer_id": "C-1003", "template": "needs_info"})
    assert msg["ok"] is True
    msg_id = msg["result"]["message"]["id"]

    resolved = server.dispatch(st, "desk_escalation_resolve",
                                {"id": "E-03", "code": "NEEDS_INFO", "message_id": msg_id})
    assert resolved["ok"] is True
    assert "E-13" in resolved["result"]["released"]

    queue_after = server.dispatch(st, "desk_queue_list", {})["result"]
    assert any(e["id"] == "E-13" for e in queue_after["escalations"])

    twice = server.dispatch(st, "desk_escalation_resolve", {"id": "E-03", "code": "NEEDS_INFO"})
    assert twice["ok"] is False and twice["error"] == "E_RESOLVED"

    unknown_code = server.dispatch(st, "desk_escalation_resolve", {"id": "E-04", "code": "NOT_A_CODE"})
    assert unknown_code["ok"] is False and unknown_code["error"] == "E_CODE"

    fake_ref = server.dispatch(st, "desk_escalation_resolve",
                                {"id": "E-02", "code": "REFUNDED", "refund_id": "sbx_0001"})
    assert fake_ref["ok"] is False and fake_ref["error"] == "E_UNKNOWN_REF"


# ---- 7. messages --------------------------------------------------------------

def test_messages_record_channel_template_locale_and_unknown_template():
    """If a message didn't record the right channel/template/locale, the
    verifier couldn't confirm the right customer got the right notice; if an
    unknown template were accepted, or raw/v1 channels leaked into the real
    messages ledger, the exact-message check could pass on wrong output."""
    st = new_state(load_seed())

    email = server.dispatch(st, "email_send",
                             {"customer_id": "C-1001", "template": "refunded", "vars": {"amount": "USD 10.00"}})
    assert email["ok"] is True
    m1 = email["result"]["message"]
    assert (m1["channel"], m1["template"], m1["locale"]) == ("email", "refunded", "en-US")

    chat = server.dispatch(st, "chat_post", {"customer_id": "C-1002", "template": "referred"})
    assert chat["ok"] is True
    m2 = chat["result"]["message"]
    assert (m2["channel"], m2["template"], m2["locale"]) == ("chat", "referred", "fr-FR")

    bad_template = server.dispatch(st, "email_send", {"customer_id": "C-1001", "template": "not_a_template"})
    assert bad_template["ok"] is False and bad_template["error"] == "E_TEMPLATE"

    raw = server.dispatch(st, "email_send_raw", {"to": "x@example.com", "subject": "s", "body": "b"})
    assert raw["ok"] is True
    v1 = server.dispatch(st, "chat_post_v1", {"customer_id": "C-1002", "text": "hi"})
    assert v1["ok"] is True

    assert len(st.messages) == 2
    assert len(st.raw_emails) == 1
    assert len(st.chat_v1) == 1


# ---- 8. ticket close ------------------------------------------------------------

def test_ticket_close_solve_and_v1_mirror_are_distinct():
    """If close-when-already-closed weren't rejected, solve() marked a ticket
    closed instead of solved, or the deprecated v1 mirror leaked into the
    real helpdesk, the verifier's ticket-status check could be fooled."""
    st = new_state(load_seed())

    already_closed = server.dispatch(st, "helpdesk_ticket_close", {"id": "T-707", "code": "WITHDRAWN"})
    assert already_closed["ok"] is False and already_closed["error"] == "E_TICKET_CLOSED"

    solved = server.dispatch(st, "helpdesk_ticket_solve", {"id": "T-701"})
    assert solved["ok"] is True and solved["result"]["status"] == "solved"
    assert st.tickets["T-701"]["status"] == "solved"

    v1_close = server.dispatch(st, "helpdesk_v1_ticket_close", {"id": "T-701"})
    assert v1_close["ok"] is True
    assert st.helpdesk_v1["T-701"]["status"] == "closed"
    assert st.tickets["T-701"]["status"] == "solved"  # the real helpdesk ticket is untouched


# ---- 9. search ------------------------------------------------------------------

def test_customer_search_exact_fuzzy_and_legacy_omits_flags():
    """If exact email search returned the wrong count, fuzzy search failed to
    surface the deliberate look-alike account, or the legacy CRM mirror
    leaked account flags it predates, an agent could act on the wrong
    customer or see data the legacy export never had."""
    st = new_state(load_seed())

    exact = server.dispatch(st, "accounts_customers_search", {"email": "nadia.okafor@brightloom.example"})
    assert exact["ok"] is True
    assert exact["result"]["count"] == 1
    assert exact["result"]["customers"][0]["id"] == "C-1001"

    fuzzy = server.dispatch(st, "accounts_customers_search_fuzzy", {"name": "Nadia Okafor"})
    assert fuzzy["ok"] is True
    ids = [c["id"] for c in fuzzy["result"]["customers"]]
    assert "C-1103" in ids

    legacy = server.dispatch(st, "accounts_legacy_customer_get", {"id": "C-1001"})
    assert legacy["ok"] is True
    assert "flags" not in legacy["result"]


# ---- 10. persistence --------------------------------------------------------------

def test_state_persists_to_disk_after_every_call():
    """The verifier grades the on-disk state.json, not the in-process state.
    If persistence broke or lagged, the verifier would grade stale or
    missing data even though the gateway itself behaved correctly."""
    st = new_state(load_seed())
    server.dispatch(st, "desk_clock", {})
    assert os.path.exists(server.STATE_PATH)
    on_disk = json.loads(Path(server.STATE_PATH).read_text())
    assert on_disk["calls"]["total"] == st.calls["total"]


# ---- 11. rules cross-check with the oracle -----------------------------------------

def test_rules_engine_matches_oracle_refund_math_and_expected_all():
    """The verifier's rule engine (tests/rules.py) and the oracle solution
    (solution/work_queue.py) implement the refund arithmetic independently.
    If they disagreed, the task would be ungradeable: either no correct
    agent run could pass, or the verifier could be wrong about what
    'correct' means."""
    seed = load_seed()
    today = date.fromisoformat(seed["clock"])
    for inv in seed["invoices"]:
        for plan in ("monthly", "annual"):
            assert rules.refund_amount(today, plan, inv) == work_queue.refund_for(today, plan, inv), (inv["id"], plan)

    expected = rules.expected_all(seed)
    assert len(expected) == 18

    want = {
        "E-01": ("REFUNDED", 2613),
        "E-04": ("REFUNDED", 41250),
        "E-12": ("REFUNDED", 5000),
        "E-17": ("REFUNDED", 40000),
        "E-09": ("NO_REFUND_DUE", None),
        "E-15": ("NO_REFUND_DUE", None),
        "E-07": ("WITHDRAWN", None),
        "E-06": ("CHARGEBACK_HOLD", None),
        "E-16": ("CHARGEBACK_HOLD", None),
        "E-05": ("REFERRED_FINANCE", None),
        "E-18": ("REFERRED_FINANCE", None),
        "E-03": ("NEEDS_INFO", None),
        "E-11": ("NEEDS_INFO", None),
    }
    for eid, (code, amount) in want.items():
        assert expected[eid]["code"] == code, eid
        if amount is not None:
            assert expected[eid]["refund"]["amount_cents"] == amount, eid


# ---- 12. seed copies identical -----------------------------------------------------

def test_seed_copies_identical_to_each_other_and_the_generator():
    """The gateway loads environment/gateway/seed.json and the verifier
    grades against tests/seed.json. If the two ever drifted, or either
    drifted from the generator that is supposed to produce both, the agent
    and the verifier would be working from different worlds."""
    env_seed_path = GATEWAY_DIR / "seed.json"
    tests_seed = json.loads(REAL_SEED_PATH.read_text())
    env_seed = json.loads(env_seed_path.read_text())
    assert tests_seed == env_seed
    assert tests_seed == generate.build()


# ---- 13. noise tools -------------------------------------------------------------

def test_noise_tools_are_inert_and_snapshot_as_counts():
    """Noise tools exist to distract the agent from the desk's real path. If
    a noise write ever touched real desk state, or the snapshot exposed the
    raw noise records instead of a count, an agent's off-path exploration
    could corrupt what the verifier grades, or leak record volume as data."""
    st = new_state(load_seed())

    read = server.dispatch(st, "github_repositorys_list", {})
    assert read["ok"] is True
    assert len(read["result"]["items"]) > 0

    write = server.dispatch(st, "github_repository_update", {"id": "gh-1", "fields": {"a": 1}})
    assert write["ok"] is True
    assert st.noise["github"][-1]["id"] == write["result"]["item"]["id"]

    snapshot = st.snapshot()
    assert isinstance(snapshot["noise"]["github"], int)
    assert snapshot["noise"]["github"] == len(st.noise["github"])

# ---- regression tests from the review gate ---------------------------------

def test_solve_refuses_a_closed_ticket():
    """helpdesk_ticket_solve had no closed guard, so an agent could flip a
    wrongly closed ticket to 'solved' and close it again with another code,
    breaking 'closed tickets cannot be undone'. It must refuse like close."""
    st = new_state(load_seed())
    assert server.dispatch(st, "helpdesk_ticket_close", {"id": "T-701", "code": "NEEDS_INFO"})["ok"]
    solve = server.dispatch(st, "helpdesk_ticket_solve", {"id": "T-701"})
    assert solve["ok"] is False and solve["error"] == "E_TICKET_CLOSED"
    again = server.dispatch(st, "helpdesk_ticket_close", {"id": "T-701", "code": "REFUNDED"})
    assert again["ok"] is False and again["error"] == "E_TICKET_CLOSED"
    assert st.tickets["T-701"]["code"] == "NEEDS_INFO"
    withdrawn = server.dispatch(st, "helpdesk_ticket_solve", {"id": "T-707"})
    assert withdrawn["ok"] is False and withdrawn["error"] == "E_TICKET_CLOSED"


