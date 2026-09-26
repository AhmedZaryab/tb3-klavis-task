import pytest

from model import Instance, check_plan
from generate import generate
# import order matters: OR-Tools' native min-cost-flow lib must not load before
# PuLP/HiGHS or HiGHS segfaults on its first solve (see test below).
import crosscheck
import reference
import greedy


SEEDS = range(100, 120)


@pytest.mark.parametrize("seed", SEEDS)
def test_reference_matches_crosscheck(seed):
    inst = generate(seed, ticks=30, n_backends=3, n_calls=60)
    # crosscheck (PuLP/HiGHS) must run before reference (OR-Tools) in this process:
    # loading OR-Tools' native min-cost-flow lib first corrupts HiGHS's state and
    # segfaults on the next solve. See RESULTS.md for the environment note.
    cross = crosscheck.solve(inst)
    ref = reference.solve(inst)
    assert ref["optimal_cost"] == cross["optimal_cost"]
    ok, cost, reason = check_plan(inst, ref)
    assert ok and cost == ref["optimal_cost"], reason
    ok, cost, reason = check_plan(inst, cross)
    assert ok and cost == cross["optimal_cost"], reason


@pytest.mark.parametrize("seed", SEEDS)
def test_greedy_feasible_and_not_better_than_optimal(seed):
    inst = generate(seed, ticks=30, n_backends=3, n_calls=60)
    ref = reference.solve(inst)
    g = greedy.solve(inst)
    ok, cost, reason = check_plan(inst, g)
    assert ok, reason
    assert cost >= ref["optimal_cost"]


def _tiny_instance():
    return Instance.from_dict({
        "ticks": 4,
        "drop_penalty": 100,
        "backends": [{"id": "a", "cost": 1, "concurrency": 1, "bucket_capacity": 1, "refill": 0}],
        "calls": [
            {"id": "c0", "release": 0, "deadline": 3, "eligible": ["a"]},
            {"id": "c1", "release": 0, "deadline": 3, "eligible": ["a"]},
        ],
    })


def test_check_plan_missing_call():
    inst = _tiny_instance()
    plan = {"plan": [{"call": "c0", "backend": "a", "tick": 0}]}
    ok, cost, reason = check_plan(inst, plan)
    assert not ok and "missing" in reason


def test_check_plan_duplicated_call():
    inst = _tiny_instance()
    plan = {"plan": [
        {"call": "c0", "backend": "a", "tick": 0},
        {"call": "c0", "backend": "a", "tick": 1},
        {"call": "c1", "drop": True},
    ]}
    ok, cost, reason = check_plan(inst, plan)
    assert not ok and "twice" in reason


def test_check_plan_ineligible_backend():
    inst = Instance.from_dict({
        "ticks": 4,
        "drop_penalty": 100,
        "backends": [
            {"id": "a", "cost": 1, "concurrency": 1, "bucket_capacity": 1, "refill": 0},
            {"id": "b", "cost": 1, "concurrency": 1, "bucket_capacity": 1, "refill": 0},
        ],
        "calls": [
            {"id": "c0", "release": 0, "deadline": 3, "eligible": ["a"]},
            {"id": "c1", "release": 0, "deadline": 3, "eligible": ["a"]},
        ],
    })
    plan = {"plan": [
        {"call": "c0", "backend": "b", "tick": 0},
        {"call": "c1", "drop": True},
    ]}
    ok, cost, reason = check_plan(inst, plan)
    assert not ok and "eligible" in reason


def test_check_plan_tick_outside_window():
    inst = _tiny_instance()
    plan = {"plan": [
        {"call": "c0", "backend": "a", "tick": 4},
        {"call": "c1", "drop": True},
    ]}
    ok, cost, reason = check_plan(inst, plan)
    assert not ok and "window" in reason


def test_check_plan_concurrency_exceeded():
    inst = Instance.from_dict({
        "ticks": 2,
        "drop_penalty": 100,
        "backends": [{"id": "a", "cost": 1, "concurrency": 1, "bucket_capacity": 5, "refill": 0}],
        "calls": [
            {"id": "c0", "release": 0, "deadline": 1, "eligible": ["a"]},
            {"id": "c1", "release": 0, "deadline": 1, "eligible": ["a"]},
        ],
    })
    plan = {"plan": [
        {"call": "c0", "backend": "a", "tick": 0},
        {"call": "c1", "backend": "a", "tick": 0},
    ]}
    ok, cost, reason = check_plan(inst, plan)
    assert not ok and "concurrency" in reason


def test_check_plan_bucket_exceeded():
    inst = Instance.from_dict({
        "ticks": 1,
        "drop_penalty": 100,
        "backends": [{"id": "a", "cost": 1, "concurrency": 5, "bucket_capacity": 1, "refill": 0}],
        "calls": [
            {"id": "c0", "release": 0, "deadline": 0, "eligible": ["a"]},
            {"id": "c1", "release": 0, "deadline": 0, "eligible": ["a"]},
        ],
    })
    plan = {"plan": [
        {"call": "c0", "backend": "a", "tick": 0},
        {"call": "c1", "backend": "a", "tick": 0},
    ]}
    ok, cost, reason = check_plan(inst, plan)
    assert not ok and "bucket level" in reason


def test_bucket_semantics_hand_simulated():
    # capacity 3, refill 1: draw 3 at t=0 ok, draw 1 at t=1 ok, draw 2 at t=1 not ok.
    inst = Instance.from_dict({
        "ticks": 2,
        "drop_penalty": 100,
        "backends": [{"id": "a", "cost": 1, "concurrency": 10, "bucket_capacity": 3, "refill": 1}],
        "calls": [{"id": f"c{i}", "release": 0, "deadline": 1, "eligible": ["a"]} for i in range(5)],
    })
    plan_ok = {"plan": [
        {"call": "c0", "backend": "a", "tick": 0},
        {"call": "c1", "backend": "a", "tick": 0},
        {"call": "c2", "backend": "a", "tick": 0},
        {"call": "c3", "backend": "a", "tick": 1},
        {"call": "c4", "drop": True},
    ]}
    ok, cost, reason = check_plan(inst, plan_ok)
    assert ok, reason
    assert cost == 4 * inst.backends[0].cost + inst.drop_penalty

    plan_bad = {"plan": [
        {"call": "c0", "backend": "a", "tick": 0},
        {"call": "c1", "backend": "a", "tick": 0},
        {"call": "c2", "backend": "a", "tick": 0},
        {"call": "c3", "backend": "a", "tick": 1},
        {"call": "c4", "backend": "a", "tick": 1},
    ]}
    ok, cost, reason = check_plan(inst, plan_bad)
    assert not ok and "bucket level" in reason
