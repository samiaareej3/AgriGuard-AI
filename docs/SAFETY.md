# Spray authorization and safety engine

**Non-negotiable:** a disease prediction never activates a pump by itself.

`backend/app/services/safety.py` is a **pure, deterministic function**: `evaluate(SafetyContext) -> Decision`.
No I/O, no clock reads, no model calls. Every input is captured in an explicit snapshot, every rule result is
recorded, and decisions are reproducible from their audit record. 30+ unit tests cover each rule
(`backend/tests/test_safety.py`) and the API flows (`test_scan_and_spray_flows.py`).

## Rules

| Rule | Critical | Fails when… |
|---|---|---|
| `MODEL_RESULT_SUPPORTED` | yes | No model result, result uncertain, or label not a model class |
| `CONFIDENCE_THRESHOLD` | yes | Confidence below policy threshold (re-checked independently of the classifier) |
| `CONFIDENCE_MARGIN` | yes | Top-2 probabilities closer than the minimum margin |
| `SUPPORTED_SCOPE` | yes | Crop ≠ tomato, or label not in the sprayable scope (early/late blight) |
| `DEVICE_REGISTERED` | yes | No target device |
| `DEVICE_ONLINE` | yes | Device offline / never seen |
| `DEVICE_HEALTHY` | yes | Reported status ≠ ok, tank < min, battery < min, pump fault, **or any of these unknown** |
| `COOLDOWN` | yes | Less than `cooldown_s` since the device's last pump activation |
| `DURATION_LIMIT` | yes | Requested duration ≤ 0 or above min(policy max, device capability) |
| `NO_ACTIVE_OPERATION` | yes | Another operation is dispatched/running on the device |
| `EMERGENCY_STOP_INACTIVE` | yes | E-stop active **or its state cannot be read** |
| `WEATHER_SUITABLE` | configurable (default advisory) | Wind or rain probability above limits, or data unavailable |
| `OPERATOR_APPROVAL` | gate | Approval required by policy and not yet given |

A critical rule whose condition is **unknown (`null`) counts as a failure.**

## Outcomes (precedence order)

1. `REVIEW_REQUIRED`: prediction unavailable/uncertain/below threshold/ambiguous. Nothing is sprayed; re-scan or inspect.
2. `SKIP`: confidently healthy; spraying not needed.
3. `BLOCKED`: any other critical rule failed or unknown. Reasons recorded.
4. `PENDING_APPROVAL`: every safety rule passed; waiting for an operator.
5. `AUTHORIZED`: everything passed (including approval, or approval not required by policy).

## Operation lifecycle

```
scan ─► evaluate ─┬─ REVIEW_REQUIRED / SKIP  (no operation created)
                  ├─ BLOCKED                 (operation recorded as BLOCKED)
                  └─ PENDING_APPROVAL ──approve──► re-evaluate ALL rules ─┬─ BLOCKED
                         │  └─reject─► REJECTED                           └─ claim device ─► DISPATCHED
                         └─ TTL ─► EXPIRED                                        │ device ack
                                                                                  ▼
                              ack timeout ─► FAILED                            RUNNING
                                                       result ok ─► COMPLETED │ result fail ─► FAILED
                                    no completion in duration+grace ─► FAILED + precautionary STOP
              any open state ── emergency stop ──► ABORTED + STOP to every device
```

- **No overlap:** dispatch atomically sets `devices.active_operation_id` only if it is empty (MongoDB
  conditional update), so concurrent approvals cannot start two sprays on one device (tested with threads).
- **Cooldown** starts whenever the pump may have run (any acknowledged SPRAY, including failures/aborts).
- **Bounded duration:** server limit (policy + device capability) and firmware hard cap (`MAX_SPRAY_MS`).
- **Idempotent device feedback:** repeated ack/result calls never change state twice.

## Policy

Stored in `settings.spray_policy`, edited by admins in Settings, versioned (`expected_version` optimistic
concurrency), every change audited with a diff. Decisions record the `policy_version` they used.

Defaults: threshold 0.75 · margin 0.15 · approval required · 3 s spray (max 10 s) · cooldown 60 s ·
offline after 30 s · tank ≥ 10 % · battery ≥ 20 % · approvals expire after 15 min · ack timeout 20 s ·
weather advisory (wind ≤ 15 km/h, rain probability ≤ 60 %).

## Emergency stop

- Operators activate it from the top bar on every page (`POST /safety/emergency-stop`, reason required).
- Effects: open operations → `ABORTED`, queued SPRAY commands cancelled, `STOP` queued to every device
  (delivered before anything else), heartbeat responses report `emergency_stop_active: true`, all new
  decisions `BLOCKED`.
- Only an **admin** can reset it, with a reason. Both actions are audited at `critical`/`warning` level.

## Physical demonstrations

The software drives **simulated** pumps only. If the prototype is demonstrated physically, use **water
only** unless your institution has separately approved a procedure. AgriGuard gives no chemical, dosing or
pesticide-use guidance.
