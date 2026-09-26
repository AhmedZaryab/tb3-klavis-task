"""LP probe: does a generic LP relaxation reach the exact integer optimum for free?

Builds the natural AGGREGATED LP (grouped by (release, deadline, eligible), the
same grouping reference.py uses): continuous x[type,k,t] >= 0, drop[type] >= 0,
level[k,t] >= 0, with the bucket two-row relaxation from reference.py's docstring.
Solved with scipy.optimize.linprog(method="highs"). No branch-and-bound, no
integrality constraints anywhere: a plain LP with no combinatorial insight.

Matrices are built sparse (COO) since a large instance can have tens of
thousands of types x ticks x backends variables.
"""

from __future__ import annotations

import sys
import json
import time
from collections import defaultdict

import numpy as np
from scipy.sparse import coo_matrix
from scipy.optimize import linprog

from model import Instance
import reference


def solve(inst: Instance) -> dict:
    groups: dict[tuple[int, int, tuple[str, ...]], int] = defaultdict(int)
    for c in inst.calls:
        groups[(c.release, c.deadline, c.eligible)] += 1
    types = list(groups.items())
    backends = {b.id: b for b in inst.backends}
    T = inst.ticks

    x_index: dict[tuple[int, str, int], int] = {}
    cols_cost = []
    for ti, ((r, d, elig), n) in enumerate(types):
        lo, hi = max(0, r), min(d, T - 1)
        for k in elig:
            for t in range(lo, hi + 1):
                x_index[(ti, k, t)] = len(cols_cost)
                cols_cost.append(backends[k].cost)
    drop_index = {}
    for ti in range(len(types)):
        drop_index[ti] = len(cols_cost)
        cols_cost.append(inst.drop_penalty)
    level_index: dict[tuple[str, int], int] = {}
    for b in inst.backends:
        for t in range(T):
            level_index[(b.id, t)] = len(cols_cost)
            cols_cost.append(0)

    n_vars = len(cols_cost)
    c_obj = np.array(cols_cost, dtype=float)

    per_kt: dict[tuple[str, int], list[int]] = defaultdict(list)
    for (ti, k, t), idx in x_index.items():
        per_kt[(k, t)].append(idx)

    ub_i, ub_j, ub_v, b_ub = [], [], [], []

    def add_row(idxs: list[int], vals: list[float], rhs: float) -> None:
        r = len(b_ub)
        ub_i.extend([r] * len(idxs))
        ub_j.extend(idxs)
        ub_v.extend(vals)
        b_ub.append(rhs)

    for b in inst.backends:
        for t in range(T):
            idxs = per_kt.get((b.id, t))
            if idxs:
                add_row(idxs, [1.0] * len(idxs), float(b.concurrency))

    for b in inst.backends:
        for t in range(T):
            draws = per_kt.get((b.id, t), [])
            lvl_t = level_index[(b.id, t)]
            add_row(draws + [lvl_t], [1.0] * len(draws) + [1.0], float(b.bucket_capacity))
            if t > 0:
                lvl_prev = level_index[(b.id, t - 1)]
                add_row(draws + [lvl_t, lvl_prev], [1.0] * len(draws) + [1.0, -1.0], float(b.refill))

    eq_i, eq_j, eq_v, b_eq = [], [], [], []
    for ti, ((r, d, elig), n) in enumerate(types):
        lo, hi = max(0, r), min(d, T - 1)
        row_idx = len(b_eq)
        for k in elig:
            for t in range(lo, hi + 1):
                eq_i.append(row_idx)
                eq_j.append(x_index[(ti, k, t)])
                eq_v.append(1.0)
        eq_i.append(row_idx)
        eq_j.append(drop_index[ti])
        eq_v.append(1.0)
        b_eq.append(float(n))

    A_ub = coo_matrix((ub_v, (ub_i, ub_j)), shape=(len(b_ub), n_vars)).tocsr()
    A_eq = coo_matrix((eq_v, (eq_i, eq_j)), shape=(len(b_eq), n_vars)).tocsr()
    bounds = [(0, None)] * n_vars

    t0 = time.perf_counter()
    res = linprog(c_obj, A_ub=A_ub, b_ub=np.array(b_ub), A_eq=A_eq, b_eq=np.array(b_eq),
                  bounds=bounds, method="highs")
    lp_seconds = time.perf_counter() - t0
    if not res.success:
        raise RuntimeError(f"linprog failed: {res.message}")

    check_idx = list(x_index.values()) + list(drop_index.values())
    integral = all(abs(res.x[idx] - round(res.x[idx])) < 1e-6 for idx in check_idx)

    return {"lp_seconds": lp_seconds, "lp_objective": float(res.fun), "integral": integral}


if __name__ == "__main__":
    inst = Instance.load(sys.argv[1])
    lp = solve(inst)

    t0 = time.perf_counter()
    ref = reference.solve(inst)
    ref_seconds = time.perf_counter() - t0

    match = abs(lp["lp_objective"] - ref["optimal_cost"]) < 1e-6
    n_types = len({(c.release, c.deadline, c.eligible) for c in inst.calls})
    summary = {
        "n_calls": len(inst.calls),
        "n_types": n_types,
        "lp_seconds": round(lp["lp_seconds"], 4),
        "lp_objective": lp["lp_objective"],
        "integral": lp["integral"],
        "ref_seconds": round(ref_seconds, 4),
        "ref_cost": ref["optimal_cost"],
        "match": match,
    }
    print(json.dumps(summary))
