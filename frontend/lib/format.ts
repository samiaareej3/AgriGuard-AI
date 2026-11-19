import type { DecisionOutcome, OperationStatus } from "./types";

export const LABELS: Record<string, string> = {
  healthy: "Healthy",
  early_blight: "Early Blight",
  late_blight: "Late Blight",
  uncertain: "Review required",
};

export const SERIES_VAR: Record<string, string> = {
  healthy: "var(--series-healthy)",
  early_blight: "var(--series-early)",
  late_blight: "var(--series-late)",
  uncertain: "var(--series-unclassified)",
};

export const OUTCOME_LABEL: Record<DecisionOutcome, string> = {
  AUTHORIZED: "Authorized",
  PENDING_APPROVAL: "Awaiting approval",
  BLOCKED: "Blocked",
  REVIEW_REQUIRED: "Review required",
  SKIP: "No spray needed",
};

export const OP_STATUS_LABEL: Record<OperationStatus, string> = {
  PENDING_APPROVAL: "Awaiting approval",
  BLOCKED: "Blocked",
  DISPATCHED: "Dispatched",
  RUNNING: "Spraying",
  COMPLETED: "Completed",
  FAILED: "Failed",
  ABORTED: "Aborted",
  REJECTED: "Rejected",
  EXPIRED: "Expired",
};

export const RULE_LABEL: Record<string, string> = {
  MODEL_RESULT_SUPPORTED: "Supported model result",
  CONFIDENCE_THRESHOLD: "Confidence threshold",
  CONFIDENCE_MARGIN: "Unambiguous prediction",
  SUPPORTED_SCOPE: "Crop/disease in scope",
  DEVICE_REGISTERED: "Device registered",
  DEVICE_ONLINE: "Device online",
  DEVICE_HEALTHY: "Device healthy",
  COOLDOWN: "Cooldown elapsed",
  DURATION_LIMIT: "Duration within limit",
  NO_ACTIVE_OPERATION: "No overlapping operation",
  EMERGENCY_STOP_INACTIVE: "Emergency stop inactive",
  WEATHER_SUITABLE: "Weather suitable",
  OPERATOR_APPROVAL: "Operator approval",
};

export function pct(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function num(v: number | null | undefined, digits = 0, unit = ""): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v.toFixed(digits)}${unit}`;
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "never";
  const s = Math.round((now - new Date(iso).getTime()) / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
}

export function duration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

export function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  const [prefix, rest] = id.split("_");
  return rest ? `${prefix}_${rest.slice(0, 6)}` : id.slice(0, 10);
}
