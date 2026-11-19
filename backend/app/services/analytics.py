"""Dashboard summary and analytics computed from persisted records.

Aggregation is done in Python over a bounded, projected query so it behaves
identically on MongoDB Atlas and on the in-memory store. Ranges are explicit
and reported back; empty ranges return zeros, never invented values.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

from app.core.timeutil import ensure_utc, utcnow
from app.db.client import Database
from app.services.devices import DeviceService
from app.services.policy import EmergencyStopService

MAX_DOCS = 20000


class AnalyticsService:
    def __init__(self, db: Database, devices: DeviceService, estop: EmergencyStopService) -> None:
        self.db, self.devices, self.estop = db, devices, estop

    def summary(self) -> dict[str, Any]:
        now = utcnow()
        day_ago = now - timedelta(hours=24)
        devices = self.devices.list_out()
        scans_24h = list(self.db.scans.find({"created_at": {"$gte": day_ago}},
                                            {"prediction.label": 1, "prediction.status": 1, "decision.outcome": 1}))
        op_counts = Counter(d["status"] for d in self.db.spray_events.find({}, {"status": 1}).limit(MAX_DOCS))
        return {
            "generated_at": now,
            "scans": {
                "total": self.db.scans.count_documents({}),
                "last_24h": len(scans_24h),
                "diseased_last_24h": sum(1 for s in scans_24h
                                         if s["prediction"].get("label") in ("early_blight", "late_blight")),
                "review_required_last_24h": sum(1 for s in scans_24h
                                                if s["decision"].get("outcome") == "REVIEW_REQUIRED"),
                "simulated_total": self.db.scans.count_documents({"simulated": True}),
            },
            "devices": {
                "total": len(devices),
                "online": sum(1 for d in devices if d.connectivity == "online"),
                "offline": sum(1 for d in devices if d.connectivity != "online"),
                "simulated": sum(1 for d in devices if d.simulated),
                "real": sum(1 for d in devices if not d.simulated),
            },
            "operations": {
                "pending_approval": op_counts.get("PENDING_APPROVAL", 0),
                "active": op_counts.get("DISPATCHED", 0) + op_counts.get("RUNNING", 0),
                "completed": op_counts.get("COMPLETED", 0),
                "blocked": op_counts.get("BLOCKED", 0),
                "failed": op_counts.get("FAILED", 0),
                "aborted": op_counts.get("ABORTED", 0),
                "by_status": dict(op_counts),
            },
            "emergency_stop": self.estop.get().model_dump(),
        }

    def analytics(self, days: int) -> dict[str, Any]:
        now = utcnow()
        start = (now - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        scans = list(self.db.scans.find(
            {"created_at": {"$gte": start}},
            {"created_at": 1, "prediction.label": 1, "prediction.status": 1, "prediction.confidence": 1,
             "decision.outcome": 1, "simulated": 1, "device_id": 1},
        ).limit(MAX_DOCS))
        ops = list(self.db.spray_events.find(
            {"created_at": {"$gte": start}}, {"created_at": 1, "status": 1, "duration_s": 1, "simulated": 1}
        ).limit(MAX_DOCS))

        day_keys = [(start + timedelta(days=i)).date().isoformat() for i in range(days)]
        per_day: dict[str, Counter] = defaultdict(Counter)
        conf_sum: dict[str, float] = defaultdict(float)
        conf_n: dict[str, int] = defaultdict(int)
        outcomes = Counter()
        labels = Counter()
        histogram = Counter()
        by_device = Counter()
        for s in scans:
            day = ensure_utc(s["created_at"]).date().isoformat()
            p = s.get("prediction", {})
            label = p.get("label") or "uncertain"
            per_day[day][label] += 1
            labels[label] += 1
            outcomes[s.get("decision", {}).get("outcome", "UNKNOWN")] += 1
            by_device[s.get("device_id") or "dashboard upload"] += 1
            c = p.get("confidence")
            if c is not None:
                conf_sum[day] += c
                conf_n[day] += 1
                histogram[min(int(c * 10), 9)] += 1

        ops_per_day: dict[str, Counter] = defaultdict(Counter)
        op_status = Counter()
        sprayed_seconds = 0.0
        for o in ops:
            day = ensure_utc(o["created_at"]).date().isoformat()
            ops_per_day[day][o["status"]] += 1
            op_status[o["status"]] += 1
            if o["status"] == "COMPLETED":
                sprayed_seconds += o.get("duration_s", 0)

        return {
            "range": {"start": start, "end": now, "days": days},
            "totals": {"scans": len(scans), "operations": len(ops),
                       "simulated_scans": sum(1 for s in scans if s.get("simulated")),
                       "completed_spray_seconds": round(sprayed_seconds, 1),
                       "truncated": len(scans) >= MAX_DOCS or len(ops) >= MAX_DOCS},
            "scans_per_day": [
                {"date": d, "healthy": per_day[d]["healthy"], "early_blight": per_day[d]["early_blight"],
                 "late_blight": per_day[d]["late_blight"], "uncertain": per_day[d]["uncertain"],
                 "avg_confidence": round(conf_sum[d] / conf_n[d], 4) if conf_n[d] else None}
                for d in day_keys
            ],
            "operations_per_day": [
                {"date": d, **{k: ops_per_day[d][k] for k in
                               ("COMPLETED", "BLOCKED", "FAILED", "ABORTED", "REJECTED", "EXPIRED",
                                "PENDING_APPROVAL", "DISPATCHED", "RUNNING")}}
                for d in day_keys
            ],
            "label_distribution": dict(labels),
            "decision_outcomes": dict(outcomes),
            "operation_status": dict(op_status),
            "confidence_histogram": [{"bucket": f"{i * 10}-{i * 10 + 10}%", "count": histogram[i]} for i in range(10)],
            "scans_by_device": dict(by_device.most_common(10)),
        }
