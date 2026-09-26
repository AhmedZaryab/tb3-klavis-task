"""Independent exact solver: direct integer formulation via PuLP + CBC.

Variables: x[c,k,t] in {0,1} for call c, eligible backend k, tick t in
[max(0,release), min(deadline, ticks-1)]; drop[c] in {0,1}.

Per-call: sum_{k,t} x[c,k,t] + drop[c] = 1.
Per (k,t): sum_c x[c,k,t] <= concurrency[k].
Bucket, per backend k: level[k,t] >= 0, with
    level[k,0] + draws[k,0] <= bucket_capacity
    level[k,t] + draws[k,t] <= level[k,t-1] + refill   (t >= 1)
    level[k,t] + draws[k,t] <= bucket_capacity
This two-row relaxation is exact (see reference.py docstring).

Only meant for small instances (<= ~200 calls, <= ~60 ticks).
"""

from __future__ import annotations

import sys
import json

import pulp

from model import Instance, check_plan


def solve(inst: Instance) -> dict:
    backends = {b.id: b for b in inst.backends}
    prob = pulp.LpProblem("dispatch", pulp.LpMinimize)

    x: dict[tuple[str, str, int], pulp.LpVariable] = {}
    windows: dict[str, list[tuple[str, int]]] = {}
    for c in inst.calls:
        lo, hi = max(0, c.release), min(c.deadline, inst.ticks - 1)
        opts = [(k, t) for k in c.eligible for t in range(lo, hi + 1)]
        windows[c.id] = opts
        for k, t in opts:
            x[(c.id, k, t)] = pulp.LpVariable(f"x_{c.id}_{k}_{t}", cat="Binary")
    drop = {c.id: pulp.LpVariable(f"drop_{c.id}", cat="Binary") for c in inst.calls}

    for c in inst.calls:
        prob += pulp.lpSum(x[(c.id, k, t)] for k, t in windows[c.id]) + drop[c.id] == 1

    draws_by_kt: dict[tuple[str, int], list[pulp.LpVariable]] = {}
    for c in inst.calls:
        for k, t in windows[c.id]:
            draws_by_kt.setdefault((k, t), []).append(x[(c.id, k, t)])

    for b in inst.backends:
        for t in range(inst.ticks):
            terms = draws_by_kt.get((b.id, t), [])
            if terms:
                prob += pulp.lpSum(terms) <= b.concurrency

    level: dict[tuple[str, int], pulp.LpVariable] = {}
    for b in inst.backends:
        for t in range(inst.ticks):
            level[(b.id, t)] = pulp.LpVariable(f"level_{b.id}_{t}", lowBound=0)

    for b in inst.backends:
        for t in range(inst.ticks):
            draws = pulp.lpSum(draws_by_kt.get((b.id, t), []))
            prob += level[(b.id, t)] + draws <= b.bucket_capacity
            if t > 0:
                prob += level[(b.id, t)] + draws <= level[(b.id, t - 1)] + b.refill

    obj = pulp.lpSum(backends[k].cost * x[(c.id, k, t)] for c in inst.calls for k, t in windows[c.id])
    obj += pulp.lpSum(inst.drop_penalty * drop[c.id] for c in inst.calls)
    prob += obj

    # CBC's bundled binary is x86_64-only and fails with "Bad CPU type" on
    # Apple Silicon without Rosetta; fall back to HiGHS, still driven through PuLP.
    try:
        status = prob.solve(pulp.PULP_CBC_CMD(msg=False))
    except (pulp.PulpSolverError, OSError):
        status = prob.solve(pulp.HiGHS(msg=False))
    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(f"solver status {pulp.LpStatus[status]}")

    plan = []
    for c in inst.calls:
        if drop[c.id].value() > 0.5:
            plan.append({"call": c.id, "drop": True})
            continue
        for k, t in windows[c.id]:
            if x[(c.id, k, t)].value() > 0.5:
                plan.append({"call": c.id, "backend": k, "tick": t})
                break
    plan.sort(key=lambda e: e["call"])
    return {"plan": plan, "optimal_cost": int(round(pulp.value(prob.objective)))}


if __name__ == "__main__":
    inst = Instance.load(sys.argv[1])
    out = solve(inst)
    ok, cost, reason = check_plan(inst, out)
    assert ok and cost == out["optimal_cost"], (ok, cost, out["optimal_cost"], reason)
    with open(sys.argv[2], "w") as f:
        json.dump({"plan": out["plan"]}, f)
    print(cost)
