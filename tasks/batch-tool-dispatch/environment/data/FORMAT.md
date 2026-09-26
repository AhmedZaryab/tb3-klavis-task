# Instance and plan formats

## Instance

```json
{
  "ticks": 1000,
  "drop_penalty": 40,
  "backends": [
    {"id": "srv-00", "cost": 2, "concurrency": 5, "bucket_capacity": 36, "refill": 1}
  ],
  "calls": [
    {"id": "call-000000", "release": 17, "deadline": 33, "eligible": ["srv-00", "srv-03"]}
  ]
}
```

- `ticks`: the number of ticks; valid ticks are `0` to `ticks - 1`.
- `drop_penalty`: the cost of dropping a call.
- `backends[].cost`: the cost of dispatching one call to that server.
- `backends[].concurrency`: the maximum number of calls that server accepts in one tick.
- `backends[].bucket_capacity`, `backends[].refill`: the token bucket. The level starts at `bucket_capacity`
  at tick 0. At every later tick the level first becomes `min(bucket_capacity, level + refill)`. Each call
  dispatched to the server at that tick then consumes one token, so the number of calls dispatched to a
  server at a tick can be at most its level after the refill, and at most its `concurrency`.
- `calls[].release`, `calls[].deadline`: a call may be dispatched at any tick `t` with `release <= t <= deadline`.
- `calls[].eligible`: the servers that may serve the call.

All numbers are integers. Call ids and server ids are unique strings.

## Plan

```json
{
  "plan": [
    {"call": "call-000000", "backend": "srv-03", "tick": 20},
    {"call": "call-000001", "drop": true}
  ]
}
```

Every call in the instance appears exactly once, either dispatched (`backend` and `tick`) or dropped
(`"drop": true`). A plan is feasible when every dispatched call is on an eligible server at a tick inside
its window and no server's concurrency or bucket is ever exceeded. Its cost is the sum of `cost` over
dispatched calls plus `drop_penalty` per dropped call.

A plan can be checked with `python3 /app/instances/model.py INSTANCE PLAN`.
