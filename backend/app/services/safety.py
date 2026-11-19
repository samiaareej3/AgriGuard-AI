"""Spray authorization (safety) engine.

NON-NEGOTIABLE: a disease prediction never activates a pump by itself. This
module is a pure, deterministic function of an explicit context snapshot — no
I/O, no clock reads, no model calls — so every rule can be unit-tested and every
decision is reproducible from its audit record.

Fail-safe principle: a critical condition that is *unknown* (``None``) counts as
a failure. Outcomes, by precedence:

1. ``REVIEW_REQUIRED`` — prediction unavailable, uncertain, below threshold or
   ambiguous. A human must re-scan / inspect; nothing is sprayed.
2. ``SKIP``            — confidently healthy; no spray needed.
3. ``BLOCKED``         — any other critical rule failed or is unknown.
4. ``PENDING_APPROVAL``— all safety rules pass but operator approval is required.
5. ``AUTHORIZED``      — every rule passes (including approval when required).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.core.timeutil import ensure_utc
from app.schemas.device import Telemetry
from app.schemas.scan import Prediction
from app.schemas.spray import Decision, RuleResult, SprayPolicy

HEALTHY_LABEL = "healthy"
SUPPORTED_CROP = "tomato"


@dataclass(frozen=True)
class DeviceSnapshot:
    id: str
    connectivity: Literal["online", "offline", "never_seen"]
    reported_status: str | None
    telemetry: Telemetry | None
    last_spray_completed_at: datetime | None
    max_spray_duration_s: float


@dataclass(frozen=True)
class WeatherSnapshot:
    available: bool
    wind_kmh: float | None = None
    precipitation_probability_pct: float | None = None
    source: str | None = None


@dataclass(frozen=True)
class SafetyContext:
    prediction: Prediction | None
    model_labels: tuple[str, ...]
    device: DeviceSnapshot | None
    active_operation_ids: tuple[str, ...]
    emergency_stop_active: bool | None
    policy: SprayPolicy
    requested_duration_s: float
    operator_approved: bool
    now: datetime
    weather: WeatherSnapshot | None = None
    stage: Literal["scan", "approval"] = "scan"
    extra_warnings: tuple[str, ...] = field(default_factory=tuple)


def _rule(rule: str, passed: bool | None, message: str, critical: bool = True) -> RuleResult:
    return RuleResult(rule=rule, passed=passed, critical=critical, message=message)


def _prediction_rules(ctx: SafetyContext) -> list[RuleResult]:
    p, policy = ctx.prediction, ctx.policy
    rules: list[RuleResult] = []

    if p is None or p.status == "MODEL_UNAVAILABLE":
        rules.append(_rule("MODEL_RESULT_SUPPORTED", None, "No model result available"))
    elif p.status != "CONFIDENT" or p.label is None:
        rules.append(_rule("MODEL_RESULT_SUPPORTED", False, "Model result is uncertain; review required"))
    elif p.label not in ctx.model_labels:
        rules.append(_rule("MODEL_RESULT_SUPPORTED", False, f"Label '{p.label}' is not a supported model class"))
    else:
        rules.append(_rule("MODEL_RESULT_SUPPORTED", True, f"Supported class '{p.label}'"))

    # Re-check confidence independently of the inference service's own threshold.
    conf = p.confidence if p else None
    if conf is None:
        rules.append(_rule("CONFIDENCE_THRESHOLD", None, "Confidence unknown"))
    else:
        ok = conf >= policy.confidence_threshold
        rules.append(_rule(
            "CONFIDENCE_THRESHOLD", ok,
            f"Confidence {conf:.1%} {'≥' if ok else '<'} threshold {policy.confidence_threshold:.0%}",
        ))

    probs = sorted((p.probabilities.values() if p else []), reverse=True)
    if len(probs) < 2:
        rules.append(_rule("CONFIDENCE_MARGIN", None, "Class probabilities unavailable"))
    else:
        margin = probs[0] - probs[1]
        ok = margin >= policy.min_confidence_margin
        rules.append(_rule(
            "CONFIDENCE_MARGIN", ok,
            f"Top-2 margin {margin:.1%} {'≥' if ok else '<'} required {policy.min_confidence_margin:.0%}",
        ))

    crop_ok = p is not None and p.crop == SUPPORTED_CROP
    label = p.label if p else None
    in_scope = crop_ok and label is not None and (label in policy.sprayable_labels or label == HEALTHY_LABEL)
    rules.append(_rule(
        "SUPPORTED_SCOPE", in_scope if label is not None else None,
        f"{(p.crop if p else 'unknown')}/{label or 'unknown'} "
        + ("is within supported spray scope" if in_scope else "is outside supported scope"),
    ))
    return rules


def _device_rules(ctx: SafetyContext) -> list[RuleResult]:
    d, policy = ctx.device, ctx.policy
    rules: list[RuleResult] = []
    if d is None:
        rules.append(_rule("DEVICE_REGISTERED", False, "No registered target device"))
        rules.append(_rule("DEVICE_ONLINE", None, "Device unknown"))
        rules.append(_rule("DEVICE_HEALTHY", None, "Device unknown"))
        rules.append(_rule("COOLDOWN", None, "Device unknown"))
        rules.append(_rule("DURATION_LIMIT", None, "Device unknown"))
        return rules

    rules.append(_rule("DEVICE_REGISTERED", True, f"Device {d.id} is registered"))
    rules.append(_rule(
        "DEVICE_ONLINE", d.connectivity == "online",
        "Device online" if d.connectivity == "online" else f"Device is {d.connectivity.replace('_', ' ')}",
    ))

    t = d.telemetry
    problems: list[str] = []
    unknown: list[str] = []
    if d.reported_status is None:
        unknown.append("status")
    elif d.reported_status != "ok":
        problems.append(f"reported status '{d.reported_status}'")
    if t is None or t.tank_level_pct is None:
        unknown.append("tank level")
    elif t.tank_level_pct < policy.min_tank_level_pct:
        problems.append(f"tank {t.tank_level_pct:.0f}% < {policy.min_tank_level_pct:.0f}%")
    if t is None or t.battery_pct is None:
        unknown.append("battery")
    elif t.battery_pct < policy.min_battery_pct:
        problems.append(f"battery {t.battery_pct:.0f}% < {policy.min_battery_pct:.0f}%")
    if t is not None and t.pump_state == "fault":
        problems.append("pump fault")
    if problems:
        rules.append(_rule("DEVICE_HEALTHY", False, "Unhealthy: " + ", ".join(problems)))
    elif unknown:
        rules.append(_rule("DEVICE_HEALTHY", None, "Unknown: " + ", ".join(unknown)))
    else:
        rules.append(_rule("DEVICE_HEALTHY", True, "Status ok, tank and battery above minimums"))

    last = ensure_utc(d.last_spray_completed_at)
    if last is None:
        rules.append(_rule("COOLDOWN", True, "No previous spray on this device"))
    else:
        elapsed = (ctx.now - last).total_seconds()
        ok = elapsed >= policy.cooldown_s
        rules.append(_rule(
            "COOLDOWN", ok,
            f"{elapsed:.0f}s since last spray (cooldown {policy.cooldown_s:.0f}s)"
            + ("" if ok else f"; wait {policy.cooldown_s - elapsed:.0f}s"),
        ))

    limit = min(policy.max_spray_duration_s, d.max_spray_duration_s)
    dur = ctx.requested_duration_s
    ok = 0 < dur <= limit
    rules.append(_rule("DURATION_LIMIT", ok, f"Requested {dur:g}s, limit {limit:g}s"))
    return rules


def _system_rules(ctx: SafetyContext) -> list[RuleResult]:
    rules: list[RuleResult] = []
    if ctx.active_operation_ids:
        rules.append(_rule(
            "NO_ACTIVE_OPERATION", False, f"Operation already active: {', '.join(ctx.active_operation_ids)}"
        ))
    else:
        rules.append(_rule("NO_ACTIVE_OPERATION", True, "No spray operation active on device"))

    if ctx.emergency_stop_active is None:
        rules.append(_rule("EMERGENCY_STOP_INACTIVE", None, "Emergency-stop state unknown"))
    else:
        rules.append(_rule(
            "EMERGENCY_STOP_INACTIVE", not ctx.emergency_stop_active,
            "Emergency stop ACTIVE" if ctx.emergency_stop_active else "Emergency stop not active",
        ))

    wp = ctx.policy.weather
    if not wp.enabled:
        rules.append(_rule("WEATHER_SUITABLE", True, "Weather check disabled by policy", critical=False))
    else:
        w = ctx.weather
        if w is None or not w.available:
            rules.append(_rule("WEATHER_SUITABLE", None, "Weather data unavailable", critical=wp.blocking))
        else:
            issues = []
            if w.wind_kmh is not None and w.wind_kmh > wp.max_wind_kmh:
                issues.append(f"wind {w.wind_kmh:.0f} km/h > {wp.max_wind_kmh:.0f}")
            if (w.precipitation_probability_pct is not None
                    and w.precipitation_probability_pct > wp.max_precip_probability_pct):
                issues.append(f"rain probability {w.precipitation_probability_pct:.0f}% > {wp.max_precip_probability_pct:.0f}%")
            if w.wind_kmh is None and w.precipitation_probability_pct is None:
                rules.append(_rule("WEATHER_SUITABLE", None, "Weather values missing", critical=wp.blocking))
            elif issues:
                rules.append(_rule("WEATHER_SUITABLE", False, "Unsuitable: " + "; ".join(issues), critical=wp.blocking))
            else:
                rules.append(_rule("WEATHER_SUITABLE", True, "Wind and rain within limits", critical=wp.blocking))
    return rules


def evaluate(ctx: SafetyContext) -> Decision:
    """Evaluate every rule and derive a single outcome (see module docstring)."""
    pred_rules = _prediction_rules(ctx)
    rules = pred_rules + _device_rules(ctx) + _system_rules(ctx)

    if ctx.policy.require_operator_approval:
        approval = _rule(
            "OPERATOR_APPROVAL", ctx.operator_approved,
            "Approved by operator" if ctx.operator_approved else "Awaiting operator approval",
            critical=False,
        )
    else:
        approval = _rule("OPERATOR_APPROVAL", True, "Approval not required by policy", critical=False)
    rules.append(approval)

    def failed(r: RuleResult) -> bool:
        return r.passed is not True

    pred_gate = {"MODEL_RESULT_SUPPORTED", "CONFIDENCE_THRESHOLD", "CONFIDENCE_MARGIN"}
    review = [r for r in rules if r.rule in pred_gate and failed(r)]
    critical_fail = [r for r in rules if r.critical and failed(r)]
    warnings = [r.message for r in rules if not r.critical and r.passed is False and r.rule != "OPERATOR_APPROVAL"]
    warnings += [r.message for r in rules if not r.critical and r.passed is None]
    warnings += list(ctx.extra_warnings)

    label = ctx.prediction.label if ctx.prediction else None
    if review:
        outcome, reasons = "REVIEW_REQUIRED", [r.message for r in review]
    elif label == HEALTHY_LABEL:
        outcome, reasons = "SKIP", ["No disease detected; spraying not needed"]
    elif critical_fail:
        outcome, reasons = "BLOCKED", [r.message for r in critical_fail]
    elif failed(approval):
        outcome, reasons = "PENDING_APPROVAL", ["All safety rules passed; operator approval required"]
    else:
        outcome, reasons = "AUTHORIZED", ["All safety rules passed"]

    return Decision(
        outcome=outcome,
        reasons=reasons + [f"Warning: {w}" for w in warnings],
        rules=rules,
        policy_version=ctx.policy.version,
        evaluated_at=ctx.now,
        stage=ctx.stage,
    )
