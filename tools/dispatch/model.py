"""Batch tool-call dispatch: instance format, plan format, and the checker.

Instance (JSON):
  ticks          T; ticks are 0..T-1
  drop_penalty   integer cost of not making a call
  backends       list of {id, cost, concurrency, bucket_capacity, refill}
  calls          list of {id, release, deadline, eligible}; deadline is inclusive

Bucket semantics, per backend k, per tick t (in this order):
  1. refill: level = min(bucket_capacity, level + refill); at t = 0 the level is bucket_capacity
  2. draws:  the number of calls dispatched to k at tick t must be <= level and <= concurrency
  3. level -= draws

Plan (JSON): {"plan": [{"call": id, "backend": k, "tick": t} | {"call": id, "drop": true}, ...]}
Every call appears exactly once. Cost = sum of backend cost per dispatched call + drop_penalty per drop.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Backend:
    id: str
    cost: int
    concurrency: int
    bucket_capacity: int
    refill: int


@dataclass(frozen=True)
class Call:
    id: str
    release: int
    deadline: int
    eligible: tuple[str, ...]


@dataclass(frozen=True)
class Instance:
    ticks: int
    drop_penalty: int
    backends: tuple[Backend, ...]
    calls: tuple[Call, ...]

    @staticmethod
    def from_dict(d: dict) -> "Instance":
        return Instance(
            ticks=int(d["ticks"]),
            drop_penalty=int(d["drop_penalty"]),
            backends=tuple(Backend(b["id"], int(b["cost"]), int(b["concurrency"]),
                                   int(b["bucket_capacity"]), int(b["refill"])) for b in d["backends"]),
            calls=tuple(Call(c["id"], int(c["release"]), int(c["deadline"]), tuple(c["eligible"]))
                        for c in d["calls"]),
        )

    def to_dict(self) -> dict:
        return {
            "ticks": self.ticks,
            "drop_penalty": self.drop_penalty,
            "backends": [vars(b) for b in self.backends],
            "calls": [{"id": c.id, "release": c.release, "deadline": c.deadline, "eligible": list(c.eligible)}
                      for c in self.calls],
        }

    @staticmethod
    def load(path: str) -> "Instance":
        with open(path) as f:
            return Instance.from_dict(json.load(f))


def check_plan(inst: Instance, plan: dict) -> tuple[bool, int, str]:
    """Return (feasible, cost, reason). Cost is only meaningful when feasible."""
    if not isinstance(plan, dict) or not isinstance(plan.get("plan"), list):
        return False, 0, "plan must be an object with a 'plan' list"
    calls = {c.id: c for c in inst.calls}
    backends = {b.id: b for b in inst.backends}
    seen: set[str] = set()
    draws: dict[tuple[str, int], int] = defaultdict(int)
    cost = 0
    for entry in plan["plan"]:
        if not isinstance(entry, dict) or "call" not in entry:
            return False, 0, "entry without a call id"
        cid = entry["call"]
        if cid not in calls:
            return False, 0, f"unknown call {cid!r}"
        if cid in seen:
            return False, 0, f"call {cid!r} listed twice"
        seen.add(cid)
        if entry.get("drop") is True:
            cost += inst.drop_penalty
            continue
        k, t = entry.get("backend"), entry.get("tick")
        if k not in backends or not isinstance(t, int) or isinstance(t, bool):
            return False, 0, f"call {cid!r}: bad backend or tick"
        c = calls[cid]
        if k not in c.eligible:
            return False, 0, f"call {cid!r}: backend {k!r} not eligible"
        if not (c.release <= t <= c.deadline) or not (0 <= t < inst.ticks):
            return False, 0, f"call {cid!r}: tick {t} outside its window"
        draws[(k, t)] += 1
        cost += backends[k].cost
    if len(seen) != len(calls):
        return False, 0, f"{len(calls) - len(seen)} calls missing from the plan"
    for b in inst.backends:
        level = b.bucket_capacity
        for t in range(inst.ticks):
            if t > 0:
                level = min(b.bucket_capacity, level + b.refill)
            d = draws.get((b.id, t), 0)
            if d > b.concurrency:
                return False, 0, f"backend {b.id!r} tick {t}: {d} draws exceed concurrency {b.concurrency}"
            if d > level:
                return False, 0, f"backend {b.id!r} tick {t}: {d} draws exceed bucket level {level}"
            level -= d
    return True, cost, "ok"


def plan_cost(inst: Instance, plan: dict) -> int:
    ok, cost, reason = check_plan(inst, plan)
    if not ok:
        raise ValueError(reason)
    return cost
