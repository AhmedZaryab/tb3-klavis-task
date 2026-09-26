"""Build the seed data for the support-desk-gateway task.

Writes one JSON document that the gateway loads at startup and the verifier
reads to compute the expected end state. The eighteen escalations are
authored by hand so that each exercises a known combination of runbook
rules; the surrounding customers, invoices and tickets are generated from a
fixed seed so that searches return realistic, non-trivial result sets.

Usage: python3 tools/desk/generate.py <out.json>
"""

import json
import random
import sys
from datetime import date

TODAY = "2026-09-14"
SEED = 20260914

FIRST = ["Nadia", "Tomas", "Aiko", "Priya", "Lukas", "Mateo", "Zofia", "Idris", "Hanna",
         "Kwame", "Elif", "Rafael", "Ingrid", "Omar", "Sven", "Leila", "Bastian", "Chiara",
         "Yusuf", "Marta", "Owen", "Farah", "Niklas", "Amara"]
LAST = ["Okafor", "Lindqvist", "Tanaka", "Raman", "Novak", "Alvarez", "Kowalski", "Bello",
        "Virtanen", "Mensah", "Demir", "Costa", "Berg", "Haddad", "Larsen", "Nasser", "Weber",
        "Ricci", "Aydin", "Silva", "Byrne", "Karimi", "Vogel", "Adeyemi"]
LOCALES = ["en-US", "fr-FR", "de-DE"]
CHANNELS = ["email", "chat"]
PLANS = ["monthly", "annual", "enterprise"]
MONTHLY_PRICES = [2900, 4900, 7900, 12900, 19900]
ANNUAL_PRICES = [29000, 49000, 60000, 99000, 120000]


def customer(cid, name, email, locale, channel, plan, flags=()):
    return {
        "id": cid,
        "name": name,
        "email": email,
        "locale": locale,
        "contact_channel": channel,
        "plan": plan,
        "flags": list(flags),
    }


def invoice(iid, cid, amount, start, end, status="paid"):
    return {
        "id": iid,
        "customer_id": cid,
        "amount_cents": amount,
        "currency": "USD",
        "status": status,
        "period_start": start,
        "period_end": end,
    }


def ticket(tid, email, subject, body, status="open", closed_by=None):
    return {
        "id": tid,
        "requester_email": email,
        "subject": subject,
        "body": body,
        "status": status,
        "closed_by": closed_by,
        "opened_at": "2026-09-1" + str(len(tid) % 4),
    }


def escalation(eid, tid, reason, released=True, released_by=None):
    return {
        "id": eid,
        "ticket_id": tid,
        "reason": reason,
        "released": released,
        "released_by": released_by,
    }


def build():
    rng = random.Random(SEED)
    customers, invoices, tickets, escalations, refunds = [], [], [], [], []

    # --- hand-authored escalation customers -------------------------------
    customers += [
        customer("C-1001", "Nadia Okafor", "nadia.okafor@brightloom.example", "en-US", "email", "monthly"),
        customer("C-1002", "Tomas Lindqvist", "tomas@lindqvist-studio.example", "fr-FR", "chat", "monthly"),
        customer("C-1003", "Aiko Tanaka", "aiko.tanaka@kitsune.example", "en-US", "email", "monthly"),
        customer("C-1004", "Priya Raman", "priya@ramanlabs.example", "en-US", "email", "annual"),
        customer("C-1005", "Lukas Novak", "lukas.novak@novakgroup.example", "en-US", "email", "enterprise"),
        customer("C-1006", "Mateo Alvarez", "mateo@alvarez.example", "en-US", "email", "monthly", ["chargeback_pending"]),
        customer("C-1007", "Zofia Kowalski", "zofia@kowalski.example", "en-US", "email", "monthly"),
        customer("C-1008", "Idris Bello", "idris.bello@bellofoods.example", "en-US", "email", "monthly"),
        customer("C-1009", "Hanna Virtanen", "hanna@virtanen.example", "en-US", "email", "monthly"),
        customer("C-1010", "Kwame Mensah", "kwame@mensah.example", "de-DE", "email", "monthly"),
        customer("C-1011", "Elif Demir", "elif.demir@demir.example", "en-US", "email", "monthly"),
        customer("C-1012", "Rafael Costa", "rafael@costa.example", "en-US", "chat", "annual"),
        customer("C-1016", "Ingrid Berg", "ingrid@berg.example", "en-US", "email", "monthly", ["chargeback_pending"]),
        customer("C-1017", "Omar Haddad", "omar@haddad.example", "de-DE", "chat", "annual"),
        customer("C-1018", "Sven Larsen", "sven@larsen.example", "fr-FR", "chat", "enterprise"),
        # look-alike of C-1001: same first name, similar surname, its own invoices
        customer("C-1103", "Nadia Okafor-Lindqvist", "n.okafor@okalind.example", "en-US", "email", "monthly"),
    ]
    invoices += [
        invoice("INV-2001", "C-1001", 4900, "2026-09-01", "2026-10-01"),
        invoice("INV-2002", "C-1002", 12900, "2026-08-20", "2026-09-20"),
        invoice("INV-2003", "C-1003", 7900, "2026-09-10", "2026-10-10"),
        invoice("INV-2004", "C-1004", 99000, "2026-03-05", "2027-03-05"),
        invoice("INV-2005", "C-1005", 250000, "2026-07-01", "2027-07-01"),
        invoice("INV-2006", "C-1006", 4900, "2026-09-03", "2026-10-03"),
        invoice("INV-2007", "C-1007", 2900, "2026-09-08", "2026-10-08"),
        invoice("INV-2008", "C-1008", 7900, "2026-08-01", "2026-09-01"),
        invoice("INV-2009", "C-1009", 4900, "2026-09-02", "2026-10-02"),
        invoice("INV-2010", "C-1010", 2900, "2026-09-04", "2026-10-04"),
        invoice("INV-2011", "C-1011", 12900, "2026-09-12", "2026-10-12", status="open"),
        invoice("INV-2016", "C-1011", 19900, "2026-09-12", "2026-10-12"),
        invoice("INV-2012", "C-1012", 60000, "2025-10-20", "2026-10-20"),
        invoice("INV-2013", "C-1016", 4900, "2026-09-06", "2026-10-06"),
        invoice("INV-2017", "C-1017", 120000, "2026-01-15", "2027-01-15"),
        invoice("INV-2018", "C-1018", 180000, "2026-05-01", "2027-05-01"),
        invoice("INV-2103", "C-1103", 7900, "2026-09-09", "2026-10-09"),
    ]
    # a refund that already happened before the shift (rule: one refund per invoice)
    refunds.append({"id": "re_seed_0001", "invoice_id": "INV-2009", "amount_cents": 1500,
                    "idempotency_key": "seed-partial-INV-2009", "reason": "goodwill"})

    tickets += [
        ticket("T-701", "nadia.okafor@brightloom.example", "Cancel and refund", "Please cancel my plan and refund the rest of invoice INV-2001."),
        ticket("T-702", "tomas@lindqvist-studio.example", "Remboursement", "Je souhaite annuler. Facture INV-2002."),
        ticket("T-703", "aiko.tanaka@kitsune.example", "Refund request", "Cancelling. Please refund invoice INV-2103 for the unused time."),
        ticket("T-704", "priya@ramanlabs.example", "Downgrade and refund", "We no longer need the annual plan; refund the unused months of INV-2004."),
        ticket("T-705", "lukas.novak@novakgroup.example", "Contract cancellation", "Terminating the agreement; refund the remaining term on INV-2005."),
        ticket("T-706", "mateo@alvarez.example", "Refund now", "Refund INV-2006 immediately or I dispute it with my bank."),
        ticket("T-707", "zofia@kowalski.example", "Refund", "Refund INV-2007 please.", status="closed", closed_by="customer"),
        ticket("T-708", "idris.bello@bellofoods.example", "Refund for August", "I did not use the service in August. Refund INV-2008."),
        ticket("T-709", "hanna@virtanen.example", "Cancel", "Cancel and refund what is left of INV-2009."),
        ticket("T-710", "kwame@mensah.example", "Kuendigung", "Bitte kuendigen und den Rest von INV-2010 erstatten."),
        ticket("T-711", "elif.demir@demir.example", "Refund", "Cancel my subscription and refund INV-2011."),
        ticket("T-712", "rafael@costa.example", "Refund unused", "Refund the unused part of INV-2012, we are leaving."),
        # follow-ups (new tickets from the same or new customers, released later)
        ticket("T-713", "aiko.tanaka@kitsune.example", "Re: Refund request", "Sorry, wrong number earlier. The invoice is INV-2003."),
        ticket("T-714", "elif.demir@demir.example", "Re: Refund", "I meant the paid one, INV-2016. Please refund that."),
        ticket("T-715", "nadia.okafor@brightloom.example", "Re: Cancel and refund", "Has the refund for INV-2001 gone out? Please refund it."),
        ticket("T-716", "ingrid@berg.example", "Refund", "Refund INV-2013, I am cancelling."),
        ticket("T-717", "omar@haddad.example", "Erstattung", "Bitte den ungenutzten Rest von INV-2017 erstatten."),
        ticket("T-718", "sven@larsen.example", "Fin de contrat", "Nous resilions. Merci de rembourser INV-2018."),
    ]
    escalations += [
        escalation("E-01", "T-701", "refund_request"),
        escalation("E-02", "T-702", "refund_request"),
        escalation("E-03", "T-703", "refund_request"),
        escalation("E-04", "T-704", "refund_request"),
        escalation("E-05", "T-705", "refund_request"),
        escalation("E-06", "T-706", "refund_request"),
        escalation("E-07", "T-707", "refund_request"),
        escalation("E-08", "T-708", "refund_request"),
        escalation("E-09", "T-709", "refund_request"),
        escalation("E-10", "T-710", "refund_request"),
        escalation("E-11", "T-711", "refund_request"),
        escalation("E-12", "T-712", "refund_request"),
        escalation("E-13", "T-713", "customer_replied", released=False, released_by="E-03"),
        escalation("E-14", "T-714", "customer_replied", released=False, released_by="E-11"),
        escalation("E-15", "T-715", "customer_replied", released=False, released_by="E-01"),
        escalation("E-16", "T-716", "refund_request", released=False, released_by="E-04"),
        escalation("E-17", "T-717", "refund_request", released=False, released_by="E-10"),
        escalation("E-18", "T-718", "refund_request", released=False, released_by="E-12"),
    ]

    # --- generated background customers -----------------------------------
    used_names = {c["name"] for c in customers}
    next_c, next_i, next_t = 1200, 2300, 800
    while len(customers) < 48:
        name = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if name in used_names:
            continue
        used_names.add(name)
        cid = f"C-{next_c}"
        next_c += 1
        plan = rng.choice(PLANS)
        email = name.lower().replace(" ", ".") + f"@{rng.choice(LAST).lower()}.example"
        customers.append(customer(cid, name, email, rng.choice(LOCALES), rng.choice(CHANNELS), plan,
                                  ["chargeback_pending"] if rng.random() < 0.08 else []))
        for _ in range(rng.randint(1, 3)):
            if plan == "monthly":
                start = date(2026, rng.randint(6, 9), rng.randint(1, 28))
                end = date(start.year + (start.month == 12), start.month % 12 + 1, start.day)
                amount = rng.choice(MONTHLY_PRICES)
            else:
                start = date(2025, rng.randint(1, 12), rng.randint(1, 28))
                end = date(start.year + 1, start.month, start.day)
                amount = rng.choice(ANNUAL_PRICES) if plan == "annual" else rng.randint(150, 400) * 1000
            invoices.append(invoice(f"INV-{next_i}", cid, amount, start.isoformat(), end.isoformat(),
                                    status=rng.choice(["paid", "paid", "paid", "open", "void"])))
            next_i += 1
        if rng.random() < 0.5:
            tickets.append(ticket(f"T-{next_t}", email, rng.choice(["Login issue", "Invoice copy", "Feature question", "Export failing"]),
                                  rng.choice(["Cannot log in since Monday.", "Please send a copy of my last invoice.",
                                              "Does the API support webhooks?", "CSV export returns an empty file."]),
                                  status=rng.choice(["open", "closed"]), closed_by=rng.choice([None, "agent"])))
            next_t += 1

    return {
        "clock": TODAY,
        "budget": 240,
        "rate_limit": {"prefix": "billing_", "calls": 6, "window_s": 10},
        "customers": customers,
        "invoices": invoices,
        "refunds": refunds,
        "tickets": tickets,
        "escalations": escalations,
        "resolution_codes": ["REFUNDED", "REFERRED_FINANCE", "CHARGEBACK_HOLD", "NEEDS_INFO", "NO_REFUND_DUE", "WITHDRAWN"],
        "templates": ["refunded", "referred", "hold", "needs_info", "no_refund"],
    }


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "seed.json"
    with open(out, "w") as f:
        json.dump(build(), f, indent=1, sort_keys=False)
        f.write("\n")
    print(out)
