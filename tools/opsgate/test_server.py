"""Tests for the opsgate v2 gateway server.

Each test starts a fresh copy of server.py as a subprocess on a random
port, with OPSGATE_STATE pointed at a temp file so the seed catalog and
tenants are clean and nothing touches /var/lib/opsgate.
"""

import json
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

SERVER_PATH = (
    Path(__file__).resolve().parents[2]
    / "tasks"
    / "gateway-tenant-onboarding"
    / "environment"
    / "gateway"
    / "server.py"
)

LIST_SHAPED_VERBS = {"STATUS", "LIST", "HELP"}
NEW_TENANTS = ["acme-corp", "globex", "initech", "vandelay", "stark", "wayne", "wonka", "tyrell"]
ALL_TENANTS = set(NEW_TENANTS) | {"umbrella", "hooli"}


def free_port():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_for_port(host, port, timeout=5.0):
    deadline = time.time() + timeout
    last_err = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError as e:
            last_err = e
            time.sleep(0.05)
    raise TimeoutError(f"server never opened {host}:{port}: {last_err}")


class Client:
    def __init__(self, host, port):
        self.sock = socket.create_connection((host, port), timeout=5)
        self.rf = self.sock.makefile("rb")

    def send(self, line):
        verb = line.split()[1].upper()
        self.sock.sendall((line + "\n").encode("utf-8"))
        header = self.rf.readline().decode("utf-8").rstrip("\r\n")
        tag, status, kv = parse_header(header)
        items = []
        if status != "ERR" and verb in LIST_SHAPED_VERBS:
            while True:
                raw = self.rf.readline().decode("utf-8").rstrip("\r\n")
                if raw == ".":
                    break
                # strip the wire-format "- " item-line prefix for easier assertions
                items.append(raw[2:] if raw.startswith("- ") else raw)
        return SimpleNamespace(header=header, tag=tag, status=status, kv=kv, items=items)

    def close(self):
        self.rf.close()
        self.sock.close()


def parse_header(header):
    tokens = shlex.split(header)
    tag = tokens[0]
    status = tokens[1]
    kv = {}
    for tok in tokens[2:]:
        k, _, v = tok.partition("=")
        kv[k] = v
    return tag, status, kv


@pytest.fixture()
def gw(tmp_path):
    state_path = tmp_path / "state.json"
    port = free_port()
    env = dict(os.environ)
    env["OPSGATE_STATE"] = str(state_path)
    env["OPSGATE_PORT"] = str(port)
    env["OPSGATE_BIND_HOST"] = "127.0.0.1"
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_PATH)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_for_port("127.0.0.1", port)
        yield SimpleNamespace(host="127.0.0.1", port=port, state_path=state_path)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def hello(gw, agent="tester", resume=None):
    c = Client(gw.host, gw.port)
    line = f"h1 HELLO agent={agent}"
    if resume:
        line += f" resume={resume}"
    r = c.send(line)
    assert r.status == "OK", r.header
    return c, r.kv["session"]


def bind_and_commit(c, sid, tenant, tool, ik_prefix):
    """BIND, then COMMIT (which only queues it). The caller's next request
    in this same chain -- any verb -- applies it before doing anything else,
    so no extra request is needed here just to force that along."""
    r = c.send(f"t1 BIND s={sid} ik={ik_prefix}-bind tenant={tenant} tool={tool}")
    assert r.status == "PENDING", r.header
    stage = r.kv["stage"]
    r = c.send(f"t2 COMMIT s={sid} ik={ik_prefix}-commit stage={stage}")
    assert r.status == "OK", r.header
    assert r.kv["queued"] == stage
    return stage


def grant_and_commit(c, sid, tenant, tool, ik_prefix, scopes=None):
    scopes = scopes or f"{tool}:read,{tool}:invoke"
    r = c.send(f"t1 GRANT s={sid} ik={ik_prefix}-grant tenant={tenant} tool={tool} scopes={scopes}")
    assert r.status == "PENDING", r.header
    stage = r.kv["stage"]
    r = c.send(f"t2 COMMIT s={sid} ik={ik_prefix}-commit stage={stage}")
    assert r.status == "OK", r.header
    assert r.kv["queued"] == stage
    return stage


# --- HELLO / budget --------------------------------------------------

def test_hello_grants_budget_of_25(gw):
    c, sid = hello(gw)
    assert sid.startswith("s-")
    c.close()


def test_budget_exhausts_and_reports_e_budget(gw):
    c, sid = hello(gw)
    tenants = NEW_TENANTS
    for i in range(25):
        r = c.send(f"q{i} STATUS s={sid} tenant={tenants[i % len(tenants)]}")
        assert r.status == "OK", r.header
    r = c.send(f"over STATUS s={sid} tenant=acme-corp")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_BUDGET"
    assert r.kv["msg"] == "session budget exhausted"
    c.close()


# --- resume: pending stages + ik history ------------------------------

def test_resume_carries_pending_stages_and_ik_history(gw):
    c1, s1 = hello(gw)
    r = c1.send(f"b1 BIND s={s1} ik=bind-1 tenant=acme-corp tool=crm-contacts-v2")
    assert r.status == "PENDING"
    stage = r.kv["stage"]

    c2, s2 = hello(gw, resume=s1)
    assert s2 != s1

    # old session is closed
    r = c1.send(f"x STATUS s={s1}")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_SESSION"

    # pending stage is still visible under the new session
    r = c2.send(f"st STATUS s={s2}")
    assert r.status == "OK"
    assert any(f"stage={stage}" in line for line in r.items)

    # replaying the exact same ik + args returns the original stage, no new one
    r = c2.send(f"b1 BIND s={s2} ik=bind-1 tenant=acme-corp tool=crm-contacts-v2")
    assert r.status == "PENDING"
    assert r.kv["stage"] == stage

    r = c2.send(f"st2 STATUS s={s2}")
    pending_lines = [l for l in r.items if l.startswith("stage=")]
    assert len(pending_lines) == 1

    c1.close()
    c2.close()


# --- loop guard --------------------------------------------------------

def test_loop_guard_locks_after_three_and_resume_unlocks(gw):
    c, sid = hello(gw)
    for _ in range(3):
        r = c.send(f"same STATUS s={sid} tenant=acme-corp")
        assert r.status == "OK", r.header

    r = c.send(f"same STATUS s={sid} tenant=acme-corp")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_LOCKED"
    assert r.kv["msg"] == "session locked"

    c2, sid2 = hello(gw, resume=sid)
    r = c2.send(f"free STATUS s={sid2} tenant=acme-corp")
    assert r.status == "OK", r.header
    assert r.kv["locked"] == "no"
    assert r.kv["budget_left"] == "24"
    c.close()
    c2.close()


# --- idempotency ---------------------------------------------------------

def test_ik_replay_and_conflict(gw):
    c, sid = hello(gw)
    r1 = c.send(f"a BIND s={sid} ik=k1 tenant=acme-corp tool=crm-contacts-v2")
    assert r1.status == "PENDING"

    r2 = c.send(f"b BIND s={sid} ik=k1 tenant=acme-corp tool=crm-contacts-v2")
    assert r2.status == "PENDING"
    assert r2.kv["stage"] == r1.kv["stage"]

    r3 = c.send(f"c BIND s={sid} ik=k1 tenant=acme-corp tool=billing-invoices-v2")
    assert r3.status == "ERR"
    assert r3.kv["code"] == "E_IK_CONFLICT"
    assert r3.kv["msg"] == "ik reused with different arguments"
    c.close()


def test_ik_missing_is_short_and_truthful(gw):
    c, sid = hello(gw)
    r = c.send(f"a BIND s={sid} tenant=acme-corp tool=crm-contacts-v2")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_IK_REQUIRED"
    assert r.kv["msg"] == "ik required"
    c.close()


def test_ik_replay_in_a_new_chain_executes_again(gw):
    """Idempotency history belongs to the chain: the same ik string reused
    in a brand-new (non-resumed) chain is not a replay -- it runs again."""
    c1, s1 = hello(gw)
    bind_and_commit(c1, s1, "acme-corp", "crm-contacts-v2", "b1")
    grant_and_commit(c1, s1, "acme-corp", "crm-contacts-v2", "g1")
    r1 = c1.send(f"i1 INVOKE s={s1} ik=same-ik tenant=acme-corp tool=crm-contacts-v2 op=smoke")
    assert r1.status == "OK"

    c2, s2 = hello(gw, agent="tester2")  # fresh chain, no resume
    r2 = c2.send(f"i1 INVOKE s={s2} ik=same-ik tenant=acme-corp tool=crm-contacts-v2 op=smoke")
    assert r2.status == "OK"

    r = c2.send(f"st STATUS s={s2} tenant=acme-corp")
    line = next(l for l in r.items if l.startswith("tenant=acme-corp"))
    assert "invocations=2" in line, line
    c1.close()
    c2.close()


# --- deferred apply --------------------------------------------------------

def test_commit_queues_and_next_request_in_chain_applies(gw):
    c, sid = hello(gw)
    r = c.send(f"a BIND s={sid} ik=bik tenant=acme-corp tool=crm-contacts-v2")
    stage = r.kv["stage"]

    r = c.send(f"b COMMIT s={sid} ik=cik tenant=acme-corp stage={stage}")
    assert r.status == "OK"
    assert r.kv["queued"] == stage

    # not applied yet: still shows as queued in STATUS built by this same
    # request... no, STATUS itself is "the next request", so by the time
    # its own item list is built the stage has already applied and vanished.
    r = c.send(f"c STATUS s={sid}")
    assert not any(f"stage={stage}" in line for line in r.items)
    line = next(l for l in r.items if l.startswith("tenant=acme-corp"))
    assert "bindings=1" in line

    data = json.loads(gw.state_path.read_text())
    assert data["tenants"]["acme-corp"]["bindings"] == ["crm-contacts-v2"]
    assert data["pending"] == []
    c.close()


def test_status_reports_queued_state_before_it_applies(gw):
    c1, s1 = hello(gw)
    r = c1.send(f"a BIND s={s1} ik=bik tenant=acme-corp tool=crm-contacts-v2")
    stage = r.kv["stage"]
    r = c1.send(f"b COMMIT s={s1} ik=cik stage={stage}")
    assert r.kv["queued"] == stage

    # a different chain observes the stage still queued (global visibility,
    # per-chain application)
    c2, s2 = hello(gw, agent="observer")
    r = c2.send(f"o STATUS s={s2}")
    line = next(l for l in r.items if l.startswith(f"stage={stage}"))
    assert "state=queued" in line
    c1.close()
    c2.close()


def test_e_order_against_a_queued_not_applied_bind(gw):
    """A GRANT may be staged while its BIND is only pending or queued, but
    committing the GRANT before the BIND has actually applied is E_ORDER.
    Cross-chain is the reliable way to observe "queued, not yet applied":
    within one chain, the very next request auto-applies the chain's own
    queued stages before doing anything else."""
    c1, s1 = hello(gw)
    r = c1.send(f"a BIND s={s1} ik=bik tenant=acme-corp tool=crm-contacts-v2")
    bind_stage = r.kv["stage"]
    r = c1.send(f"b COMMIT s={s1} ik=cik stage={bind_stage}")
    assert r.kv["queued"] == bind_stage  # queued, not applied -- chain 1 sends no further request

    c2, s2 = hello(gw, agent="other")
    r = c2.send(
        f"c GRANT s={s2} ik=gik tenant=acme-corp tool=crm-contacts-v2 "
        "scopes=crm-contacts-v2:read,crm-contacts-v2:invoke"
    )
    assert r.status == "PENDING"
    grant_stage = r.kv["stage"]

    r = c2.send(f"d COMMIT s={s2} ik=cik2 stage={grant_stage}")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_ORDER"
    assert r.kv["msg"] == f"stage {grant_stage} depends on {bind_stage}"
    c1.close()
    c2.close()


def test_e_order_committing_grant_before_bind_is_committed(gw):
    c, sid = hello(gw)
    r = c.send(f"a BIND s={sid} ik=bik tenant=acme-corp tool=crm-contacts-v2")
    bind_stage = r.kv["stage"]

    r = c.send(
        f"b GRANT s={sid} ik=gik tenant=acme-corp tool=crm-contacts-v2 "
        "scopes=crm-contacts-v2:read,crm-contacts-v2:invoke"
    )
    assert r.status == "PENDING"
    grant_stage = r.kv["stage"]

    r = c.send(f"c COMMIT s={sid} ik=cik1 stage={grant_stage}")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_ORDER"
    assert bind_stage in r.kv["msg"]

    r = c.send(f"d COMMIT s={sid} ik=cik2 stage={bind_stage}")
    assert r.status == "OK"

    r = c.send(f"e COMMIT s={sid} ik=cik3 stage={grant_stage}")
    assert r.status == "OK"
    c.close()


# --- freeze / reopen --------------------------------------------------------

def test_finish_freezes_and_reopen_unfreezes(gw):
    c, sid = hello(gw)
    for tool in ("crm-contacts-v2", "billing-invoices-v2", "chat-post-v3"):
        bind_and_commit(c, sid, "acme-corp", tool, f"b-{tool}")
        grant_and_commit(c, sid, "acme-corp", tool, f"g-{tool}")

    r = c.send(f"f1 FINISH s={sid} ik=finish1 tenant=acme-corp")
    assert r.status == "OK"
    assert r.kv["onboarded"] == "acme-corp"

    r = c.send(f"b1 BIND s={sid} ik=b-again tenant=acme-corp tool=crm-companies")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_FROZEN"
    assert r.kv["msg"] == "tenant is frozen"

    r = c.send(f"i1 INVOKE s={sid} ik=inv-again tenant=acme-corp tool=crm-contacts-v2 op=smoke")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_FROZEN"

    r = c.send(f"r1 REOPEN s={sid} ik=reopen1 tenant=acme-corp")
    assert r.status == "OK"
    assert r.kv["reopened"] == "acme-corp"

    r = c.send(f"st STATUS s={sid} tenant=acme-corp")
    line = next(l for l in r.items if l.startswith("tenant=acme-corp"))
    assert "onboarded=no" in line

    # unfrozen: BIND works again
    r = c.send(f"b2 BIND s={sid} ik=b-fresh tenant=acme-corp tool=crm-companies")
    assert r.status == "PENDING"

    # re-finish re-freezes
    r = c.send(f"f2 FINISH s={sid} ik=finish2 tenant=acme-corp")
    assert r.status == "OK"
    r = c.send(f"i2 INVOKE s={sid} ik=inv-frozen-2 tenant=acme-corp tool=crm-contacts-v2 op=smoke")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_FROZEN"
    c.close()


def test_umbrella_seeded_frozen(gw):
    """umbrella is seeded already onboarded, which means already frozen."""
    c, sid = hello(gw)
    r = c.send(f"b BIND s={sid} ik=bik tenant=umbrella tool=crm-companies")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_FROZEN"
    c.close()


# --- catalog validation ---------------------------------------------------

def test_bind_deprecated_tool_is_rejected(gw):
    c, sid = hello(gw)
    r = c.send(f"a BIND s={sid} ik=k1 tenant=acme-corp tool=crm-contacts-v1")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_DEPRECATED"
    c.close()


def test_grant_bad_scope_format(gw):
    c, sid = hello(gw)
    r = c.send(f"a GRANT s={sid} ik=k1 tenant=acme-corp tool=crm-contacts-v2 scopes=bogus")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_SCOPE_FORMAT"
    c.close()


# --- pagination ------------------------------------------------------------

def test_list_tools_pagination_covers_all_12(gw):
    c, sid = hello(gw)
    seen = []
    cursor = None
    for _ in range(10):
        line = f"p LIST s={sid} kind=tools"
        if cursor:
            line += f" cursor={cursor}"
        r = c.send(line)
        assert r.status == "OK"
        assert len(r.items) <= 4
        seen.extend(r.items)
        cursor = r.kv["next"]
        if cursor == "none":
            break
    else:
        pytest.fail("pagination never terminated")

    ids = [line.split(" ")[0].split("=")[1] for line in seen]
    assert len(ids) == 12
    assert len(set(ids)) == 12
    c.close()


def test_list_tenants_pagination_covers_all_ten(gw):
    c, sid = hello(gw)
    seen = []
    cursor = None
    for _ in range(10):
        line = f"p LIST s={sid} kind=tenants"
        if cursor:
            line += f" cursor={cursor}"
        r = c.send(line)
        assert r.status == "OK"
        assert len(r.items) <= 4
        seen.extend(r.items)
        cursor = r.kv["next"]
        if cursor == "none":
            break
    else:
        pytest.fail("pagination never terminated")

    names = {line.split(" ")[0].split("=")[1] for line in seen}
    assert names == ALL_TENANTS
    c.close()


# --- invoke ------------------------------------------------------------

def test_invoke_requires_applied_binding_and_scope(gw):
    c, sid = hello(gw)
    r = c.send(f"i1 INVOKE s={sid} ik=inv1 tenant=acme-corp tool=crm-contacts-v2 op=smoke")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_NOT_BOUND"
    assert r.kv["msg"] == "no applied binding"

    bind_and_commit(c, sid, "acme-corp", "crm-contacts-v2", "bc1")

    r = c.send(f"i2 INVOKE s={sid} ik=inv2 tenant=acme-corp tool=crm-contacts-v2 op=smoke")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_SCOPE"
    assert r.kv["msg"] == "no applied grant with crm-contacts-v2:invoke"

    grant_and_commit(c, sid, "acme-corp", "crm-contacts-v2", "gc1")

    r = c.send(f"i3 INVOKE s={sid} ik=inv3 tenant=acme-corp tool=crm-contacts-v2 op=smoke")
    assert r.status == "OK"
    assert r.kv["result"] == "pong"
    c.close()


def test_invocation_counting_dedupes_by_ik(gw):
    c, sid = hello(gw)
    bind_and_commit(c, sid, "acme-corp", "crm-contacts-v2", "bc1")
    grant_and_commit(c, sid, "acme-corp", "crm-contacts-v2", "gc1")

    r = c.send(f"i1 INVOKE s={sid} ik=same-ik tenant=acme-corp tool=crm-contacts-v2 op=smoke")
    assert r.status == "OK"

    r = c.send(f"i2 INVOKE s={sid} ik=same-ik tenant=acme-corp tool=crm-contacts-v2 op=smoke")
    assert r.status == "OK"

    r = c.send(f"st1 STATUS s={sid} tenant=acme-corp")
    line = next(l for l in r.items if l.startswith("tenant=acme-corp"))
    assert "invocations=1" in line

    r = c.send(f"i3 INVOKE s={sid} ik=new-ik tenant=acme-corp tool=crm-contacts-v2 op=smoke")
    assert r.status == "OK"

    r = c.send(f"st2 STATUS s={sid} tenant=acme-corp")
    line = next(l for l in r.items if l.startswith("tenant=acme-corp"))
    assert "invocations=2" in line
    c.close()


# --- finish --------------------------------------------------------------

def test_finish_does_not_check_invocations(gw):
    c, sid = hello(gw)
    for tool in ("crm-contacts-v2", "billing-invoices-v2", "chat-post-v3"):
        bind_and_commit(c, sid, "acme-corp", tool, f"b-{tool}")
        grant_and_commit(c, sid, "acme-corp", tool, f"g-{tool}")

    r = c.send(f"f1 FINISH s={sid} ik=finish1 tenant=acme-corp")
    assert r.status == "OK", r.header
    assert r.kv["onboarded"] == "acme-corp"
    c.close()


def test_finish_incomplete_reports_missing(gw):
    c, sid = hello(gw)
    bind_and_commit(c, sid, "acme-corp", "crm-contacts-v2", "b1")
    grant_and_commit(c, sid, "acme-corp", "crm-contacts-v2", "g1")

    r = c.send(f"f1 FINISH s={sid} ik=finish1 tenant=acme-corp")
    assert r.status == "ERR"
    assert r.kv["code"] == "E_INCOMPLETE"
    assert "billing-invoices-v2" in r.kv["msg"]
    assert "chat-post-v3" in r.kv["msg"]
    c.close()


# --- status content --------------------------------------------------------

def test_status_reports_seed_data(gw):
    c, sid = hello(gw)
    r = c.send(f"s1 STATUS s={sid}")
    assert r.status == "OK"
    assert r.kv["pending"] == "0"
    lines = {l.split(" ")[0].split("=")[1]: l for l in r.items if l.startswith("tenant=")}
    assert set(lines) == ALL_TENANTS
    assert "bindings=3 grants=3 invocations=3 onboarded=yes" in lines["umbrella"]
    assert "bindings=1 grants=1 invocations=0 onboarded=no" in lines["hooli"]
    for name in NEW_TENANTS:
        assert "bindings=0 grants=0 invocations=0 onboarded=no" in lines[name]
    c.close()


# --- persistence -----------------------------------------------------------

def test_state_persists_after_mutations(gw):
    c, sid = hello(gw)
    bind_and_commit(c, sid, "acme-corp", "crm-contacts-v2", "b1")
    grant_and_commit(c, sid, "acme-corp", "crm-contacts-v2", "g1")
    r = c.send(f"i1 INVOKE s={sid} ik=inv1 tenant=acme-corp tool=crm-contacts-v2 op=smoke")
    assert r.status == "OK"
    c.close()

    assert gw.state_path.exists()
    data = json.loads(gw.state_path.read_text())

    acme = data["tenants"]["acme-corp"]
    assert acme["bindings"] == ["crm-contacts-v2"]
    assert acme["grants"] == {"crm-contacts-v2": ["crm-contacts-v2:read", "crm-contacts-v2:invoke"]}
    assert acme["invocations"] == {"crm-contacts-v2": 1}
    assert data["pending"] == []

    umbrella = data["tenants"]["umbrella"]
    assert umbrella["onboarded"] is True
    assert sorted(umbrella["bindings"]) == sorted(
        ["crm-contacts-v2", "billing-invoices-v2", "chat-post-v3"]
    )
    hooli = data["tenants"]["hooli"]
    assert hooli["bindings"] == ["crm-contacts-v2"]
    assert hooli["onboarded"] is False


def test_unknown_tenant_is_an_error_not_a_new_record(gw):
    """A typo in the tenant name must not silently create a tenant."""
    c, sid = hello(gw)
    r = c.send(f"t1 BIND s={sid} ik=k1 tenant=acme-corpp tool=crm-contacts-v2")
    assert r.status == "ERR" and r.kv["code"] == "E_NO_TENANT"
    r = c.send(f"t2 LIST s={sid} kind=tenants")
    assert not any("acme-corpp" in line for line in r.items)


def test_help_ignores_session_and_other_key_value_tokens(gw):
    """HELP s=<id> must behave like HELP, not treat the token as a verb name."""
    c, sid = hello(gw)
    r = c.send(f"t1 HELP s={sid}")
    assert r.status == "OK"
    r = c.send(f"t2 HELP BIND s={sid}")
    assert r.status == "OK" and any("BIND" in line for line in r.items)


def test_seed_state_is_persisted_before_any_request(gw):
    """A do-nothing agent must still leave a state file for the collect hook."""
    assert gw.state_path.exists()
    state = json.loads(gw.state_path.read_text())
    assert set(state["tenants"]) == ALL_TENANTS


# --- terse HELP (v2) --------------------------------------------------------

FORBIDDEN_RULE_WORDS = ["budget of", "three consecutive", "lock"]


def test_help_top_level_is_terse_and_has_no_rule_prose(gw):
    c, sid = hello(gw)
    r = c.send(f"h HELP s={sid}")
    assert r.status == "OK"
    assert len(r.items) == 10  # one line per verb, no rule lines
    for line in r.items:
        assert line.startswith("verb=")
        assert "usage=" in line
    full_text = " ".join(r.items).lower()
    for word in FORBIDDEN_RULE_WORDS:
        assert word not in full_text, f"HELP leaked rule prose: {word!r}"
    c.close()


@pytest.mark.parametrize(
    "verb",
    ["HELLO", "HELP", "STATUS", "LIST", "BIND", "GRANT", "COMMIT", "INVOKE", "FINISH", "REOPEN"],
)
def test_help_verb_is_exactly_purpose_usage_errors(gw, verb):
    c, sid = hello(gw)
    r = c.send(f"h HELP {verb} s={sid}")
    assert r.status == "OK"
    assert len(r.items) == 3
    assert r.items[0].startswith("purpose=")
    assert r.items[1].startswith("usage=")
    assert r.items[2].startswith("errors=")
    full_text = " ".join(r.items).lower()
    for word in FORBIDDEN_RULE_WORDS:
        assert word not in full_text, f"HELP {verb} leaked rule prose: {word!r}"
    c.close()


def test_help_reveals_no_budget_size_or_loop_threshold_anywhere(gw):
    c, sid = hello(gw)
    all_text = []
    r = c.send(f"h HELP s={sid}")
    all_text.extend(r.items)
    for verb in ["HELLO", "HELP", "STATUS", "LIST", "BIND", "GRANT", "COMMIT", "INVOKE", "FINISH", "REOPEN"]:
        r = c.send(f"h{verb} HELP {verb} s={sid}")
        all_text.extend(r.items)
    blob = " ".join(all_text).lower()
    assert "25" not in blob  # the budget number
    for word in FORBIDDEN_RULE_WORDS:
        assert word not in blob
    c.close()


# --- error messages are short and truthful, without instructions -----------

def test_error_messages_carry_no_recovery_instructions(gw):
    c, sid = hello(gw)
    for _ in range(3):
        r = c.send(f"same STATUS s={sid} tenant=acme-corp")
    r = c.send(f"same STATUS s={sid} tenant=acme-corp")
    assert r.kv["code"] == "E_LOCKED"
    assert "resume" not in r.kv["msg"]
    assert "HELLO" not in r.kv["msg"]
    c.close()
