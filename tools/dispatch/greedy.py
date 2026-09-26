"""Baseline planner: earliest deadline first, cheapest eligible server with a token and a free slot."""

from __future__ import annotations

import json
import sys
from collections import defaultdict

from model import Instance, check_plan


def solve(inst: Instance) -> dict:
    backends = {b.id: b for b in inst.backends}
    level = {b.id: b.bucket_capacity for b in inst.backends}
    draws: dict[tuple[str, int], int] = defaultdict(int)
    pending = sorted(inst.calls, key=lambda c: (c.deadline, c.release))
    plan = []
    waiting: list = []
    i = 0
    for t in range(inst.ticks):
        for b in inst.backends:
            if t > 0:
                level[b.id] = min(b.bucket_capacity, level[b.id] + b.refill)
        while i < len(pending) and pending[i].release <= t:
            waiting.append(pending[i])
            i += 1
        waiting.sort(key=lambda c: c.deadline)
        still = []
        for c in waiting:
            if c.deadline < t:
                plan.append({"call": c.id, "drop": True})
                continue
            choice = None
            for k in sorted(c.eligible, key=lambda k: backends[k].cost):
                if level[k] > 0 and draws[(k, t)] < backends[k].concurrency:
                    choice = k
                    break
            if choice is None:
                still.append(c)
                continue
            level[choice] -= 1
            draws[(choice, t)] += 1
            plan.append({"call": c.id, "backend": choice, "tick": t})
        waiting = still
    for c in waiting:
        plan.append({"call": c.id, "drop": True})
    plan.sort(key=lambda e: e["call"])
    return {"plan": plan}


if __name__ == "__main__":
    inst = Instance.load(sys.argv[1])
    out = solve(inst)
    ok, cost, reason = check_plan(inst, out)
    assert ok, reason
    with open(sys.argv[2], "w") as f:
        json.dump(out, f)
    print(cost)
