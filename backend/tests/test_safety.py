"""Unit tests for every spray-authorization rule (pure function, no I/O)."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.schemas.device import Telemetry
from app.schemas.scan import Prediction
from app.schemas.spray import SprayPolicy, WeatherPolicy
from app.services.safety import DeviceSnapshot, SafetyContext, WeatherSnapshot, evaluate

NOW = datetime(2026, 11, 18, 12, 0, tzinfo=timezone.utc)
LABELS = ("early_blight", "healthy", "late_blight")


def pred(label="early_blight", conf=0.92, status="CONFIDENT", probs=None, crop="tomato") -> Prediction:
    probs = probs or {"early_blight": conf, "healthy": (1 - conf) / 2, "late_blight": (1 - conf) / 2}
    return Prediction(status=status, crop=crop, label=label if status == "CONFIDENT" else None,
                      display_label=label or "Review", top_label=label, confidence=conf, probabilities=probs,
                      threshold=0.75, timestamp=NOW)


def device(**kw) -> DeviceSnapshot:
    base = dict(id="dev_1", connectivity="online", reported_status="ok",
                telemetry=Telemetry(battery_pct=80, tank_level_pct=70, pump_state="idle"),
                last_spray_completed_at=None, max_spray_duration_s=10)
    base.update(kw)
    return DeviceSnapshot(**base)


def ctx(**kw) -> SafetyContext:
    base = dict(prediction=pred(), model_labels=LABELS, device=device(), active_operation_ids=(),
                emergency_stop_active=False, policy=SprayPolicy(weather=WeatherPolicy(enabled=False)),
                requested_duration_s=3, operator_approved=True, now=NOW)
    base.update(kw)
    return SafetyContext(**base)


def rule(decision, name):
    return next(r for r in decision.rules if r.rule == name)


def test_all_rules_pass_authorized():
    d = evaluate(ctx())
    assert d.outcome == "AUTHORIZED"
    assert all(r.passed for r in d.rules)


def test_approval_required_gives_pending():
    d = evaluate(ctx(operator_approved=False))
    assert d.outcome == "PENDING_APPROVAL"
    assert rule(d, "OPERATOR_APPROVAL").passed is False


def test_approval_not_required_by_policy():
    p = SprayPolicy(require_operator_approval=False, weather=WeatherPolicy(enabled=False))
    assert evaluate(ctx(operator_approved=False, policy=p)).outcome == "AUTHORIZED"


def test_healthy_is_skip_even_if_device_offline():
    d = evaluate(ctx(prediction=pred("healthy", probs={"early_blight": 0.02, "healthy": 0.95, "late_blight": 0.03},
                                     conf=0.95), device=device(connectivity="offline")))
    assert d.outcome == "SKIP"


@pytest.mark.parametrize("p", [
    None,
    Prediction(status="MODEL_UNAVAILABLE", display_label="x", threshold=0.75, timestamp=NOW),
    pred(status="UNCERTAIN", conf=0.5),
])
def test_missing_or_uncertain_prediction_requires_review(p):
    d = evaluate(ctx(prediction=p))
    assert d.outcome == "REVIEW_REQUIRED"


def test_below_threshold_requires_review_even_if_marked_confident():
    # The engine re-checks confidence independently of the inference service.
    d = evaluate(ctx(prediction=pred(conf=0.70, probs={"early_blight": 0.70, "healthy": 0.1, "late_blight": 0.2})))
    assert d.outcome == "REVIEW_REQUIRED"
    assert rule(d, "CONFIDENCE_THRESHOLD").passed is False


def test_small_margin_requires_review():
    d = evaluate(ctx(prediction=pred(conf=0.80, probs={"early_blight": 0.80, "healthy": 0.0, "late_blight": 0.70})))
    assert rule(d, "CONFIDENCE_MARGIN").passed is False
    assert d.outcome == "REVIEW_REQUIRED"


def test_unsupported_label_requires_review():
    d = evaluate(ctx(prediction=pred(label="leaf_mold"), model_labels=LABELS))
    assert d.outcome == "REVIEW_REQUIRED"
    assert rule(d, "MODEL_RESULT_SUPPORTED").passed is False


def test_out_of_scope_crop_blocked():
    d = evaluate(ctx(prediction=pred(crop="potato")))
    assert d.outcome == "BLOCKED"
    assert rule(d, "SUPPORTED_SCOPE").passed is False


def test_label_not_sprayable_blocked():
    p = SprayPolicy(sprayable_labels=["late_blight"], weather=WeatherPolicy(enabled=False))
    d = evaluate(ctx(policy=p))
    assert d.outcome == "BLOCKED"


def test_no_device_blocked():
    d = evaluate(ctx(device=None))
    assert d.outcome == "BLOCKED"
    assert rule(d, "DEVICE_REGISTERED").passed is False


@pytest.mark.parametrize("state", ["offline", "never_seen"])
def test_offline_device_blocked(state):
    d = evaluate(ctx(device=device(connectivity=state)))
    assert d.outcome == "BLOCKED"
    assert rule(d, "DEVICE_ONLINE").passed is False


@pytest.mark.parametrize("dev,expected", [
    (device(reported_status="error"), False),
    (device(reported_status=None), None),
    (device(telemetry=Telemetry(battery_pct=80, tank_level_pct=5)), False),
    (device(telemetry=Telemetry(battery_pct=10, tank_level_pct=70)), False),
    (device(telemetry=Telemetry(battery_pct=80)), None),          # tank unknown
    (device(telemetry=None), None),
    (device(telemetry=Telemetry(battery_pct=80, tank_level_pct=70, pump_state="fault")), False),
])
def test_device_health(dev, expected):
    d = evaluate(ctx(device=dev))
    assert rule(d, "DEVICE_HEALTHY").passed is expected
    assert d.outcome == "BLOCKED"  # unknown critical condition => fail-safe block


def test_active_operation_blocked():
    d = evaluate(ctx(active_operation_ids=("op_1",)))
    assert d.outcome == "BLOCKED"
    assert "op_1" in rule(d, "NO_ACTIVE_OPERATION").message


def test_cooldown():
    recent = device(last_spray_completed_at=NOW - timedelta(seconds=30))
    d = evaluate(ctx(device=recent))
    assert d.outcome == "BLOCKED" and rule(d, "COOLDOWN").passed is False
    old = device(last_spray_completed_at=NOW - timedelta(seconds=61))
    assert evaluate(ctx(device=old)).outcome == "AUTHORIZED"


def test_duration_limit_policy_and_device():
    assert rule(evaluate(ctx(requested_duration_s=11)), "DURATION_LIMIT").passed is False
    assert rule(evaluate(ctx(device=device(max_spray_duration_s=2))), "DURATION_LIMIT").passed is False
    assert rule(evaluate(ctx(requested_duration_s=0)), "DURATION_LIMIT").passed is False


def test_emergency_stop_active_or_unknown_blocks():
    assert evaluate(ctx(emergency_stop_active=True)).outcome == "BLOCKED"
    d = evaluate(ctx(emergency_stop_active=None))
    assert d.outcome == "BLOCKED" and rule(d, "EMERGENCY_STOP_INACTIVE").passed is None


def test_weather_advisory_by_default():
    p = SprayPolicy()  # weather enabled, non-blocking
    d = evaluate(ctx(policy=p, weather=WeatherSnapshot(available=True, wind_kmh=30, precipitation_probability_pct=10)))
    assert d.outcome == "AUTHORIZED"
    assert any("wind" in r for r in d.reasons)
    d2 = evaluate(ctx(policy=p, weather=None))
    assert d2.outcome == "AUTHORIZED" and any("unavailable" in r for r in d2.reasons)


def test_weather_blocking_when_configured():
    p = SprayPolicy(weather=WeatherPolicy(enabled=True, blocking=True))
    windy = WeatherSnapshot(available=True, wind_kmh=30, precipitation_probability_pct=10)
    assert evaluate(ctx(policy=p, weather=windy)).outcome == "BLOCKED"
    rainy = WeatherSnapshot(available=True, wind_kmh=5, precipitation_probability_pct=90)
    assert evaluate(ctx(policy=p, weather=rainy)).outcome == "BLOCKED"
    assert evaluate(ctx(policy=p, weather=None)).outcome == "BLOCKED"  # unknown => fail-safe
    calm = WeatherSnapshot(available=True, wind_kmh=5, precipitation_probability_pct=10)
    assert evaluate(ctx(policy=p, weather=calm)).outcome == "AUTHORIZED"


def test_review_takes_precedence_over_block():
    d = evaluate(ctx(prediction=pred(status="UNCERTAIN", conf=0.4), emergency_stop_active=True))
    assert d.outcome == "REVIEW_REQUIRED"


def test_decision_is_deterministic_and_records_policy_version():
    c = ctx(policy=SprayPolicy(version=7, weather=WeatherPolicy(enabled=False)))
    assert evaluate(c) == evaluate(replace(c))
    assert evaluate(c).policy_version == 7
