from __future__ import annotations

from fastapi import APIRouter, Query

from app.routes.deps import Admin, Operator, ServicesDep, Viewer
from app.schemas.base import Page
from app.schemas.spray import (
    Decision, EmergencyStopRequest, EmergencyStopState, EvaluateRequest, OperatorNote, SprayOperationOut,
    SprayPolicy, SprayPolicyUpdate,
)

router = APIRouter(tags=["spray & safety"])


@router.get("/spray/operations", response_model=Page[SprayOperationOut])
def list_operations(_: Viewer, services: ServicesDep, status: str | None = Query(None, max_length=200),
                    device_id: str | None = None, page: int = Query(1, ge=1),
                    page_size: int = Query(25, ge=1, le=100)) -> Page[SprayOperationOut]:
    docs, total = services.spray.list(status, device_id, page, page_size)
    return Page[SprayOperationOut](items=[services.spray.to_out(d) for d in docs], total=total, page=page,
                                   page_size=page_size)


@router.get("/spray/operations/{op_id}", response_model=SprayOperationOut)
def get_operation(op_id: str, _: Viewer, services: ServicesDep) -> SprayOperationOut:
    return services.spray.to_out(services.spray.get_doc(op_id))


@router.post("/spray/operations/{op_id}/approve", response_model=SprayOperationOut,
             summary="Approve: re-evaluates ALL safety rules before dispatching")
def approve(op_id: str, body: OperatorNote, user: Operator, services: ServicesDep) -> SprayOperationOut:
    return services.spray.to_out(services.spray.approve(op_id, user.actor, body.note))


@router.post("/spray/operations/{op_id}/reject", response_model=SprayOperationOut)
def reject(op_id: str, body: OperatorNote, user: Operator, services: ServicesDep) -> SprayOperationOut:
    return services.spray.to_out(services.spray.reject(op_id, user.actor, body.note))


@router.post("/spray/evaluate", response_model=Decision, summary="Dry-run the safety engine (no side effects)")
def evaluate(body: EvaluateRequest, _: Viewer, services: ServicesDep) -> Decision:
    return services.spray.evaluate_dry_run(body.scan_id, body.device_id)


@router.get("/spray/policy", response_model=SprayPolicy)
def get_policy(_: Viewer, services: ServicesDep) -> SprayPolicy:
    return services.policy.get()


@router.put("/spray/policy", response_model=SprayPolicy)
def update_policy(body: SprayPolicyUpdate, admin: Admin, services: ServicesDep) -> SprayPolicy:
    old = services.policy.get()
    new = services.policy.update(body, admin.actor)
    changed = {k: [old.model_dump()[k], v] for k, v in new.model_dump().items()
               if k not in ("version", "updated_at", "updated_by") and old.model_dump()[k] != v}
    services.audit.record("policy", "updated", f"Spray policy updated to v{new.version}", actor=admin.actor,
                          context={"changes": changed})
    services.bus.publish("policy.updated", new.model_dump())
    return new


@router.get("/safety/emergency-stop", response_model=EmergencyStopState)
def estop_state(_: Viewer, services: ServicesDep) -> EmergencyStopState:
    return services.estop.get()


@router.post("/safety/emergency-stop", response_model=EmergencyStopState,
             summary="ACTIVATE emergency stop (operator). Aborts operations and sends STOP to all devices.")
def estop_activate(body: EmergencyStopRequest, user: Operator, services: ServicesDep) -> EmergencyStopState:
    state, changed = services.estop.activate(user.actor, body.reason)
    aborted = services.spray.abort_all(user.actor, body.reason)  # always re-send STOP, even if already active
    if changed:
        services.audit.record("safety", "estop_activated", f"EMERGENCY STOP activated: {body.reason}",
                              level="critical", actor=user.actor, context={"aborted_operations": aborted})
    services.bus.publish("estop.changed", state.model_dump())
    return state


@router.post("/safety/emergency-stop/reset", response_model=EmergencyStopState,
             summary="Reset emergency stop (admin only)")
def estop_reset(body: EmergencyStopRequest, admin: Admin, services: ServicesDep) -> EmergencyStopState:
    state, changed = services.estop.reset(admin.actor, body.reason)
    if changed:
        services.audit.record("safety", "estop_reset", f"Emergency stop reset: {body.reason}",
                              level="warning", actor=admin.actor)
        services.bus.publish("estop.changed", state.model_dump())
    return state
