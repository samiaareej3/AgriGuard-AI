// Mirrors backend/app/schemas/*. Keep in sync with the OpenAPI spec at /api/v1/openapi.json.

export type Role = "viewer" | "operator" | "admin";

export interface User {
  id: string;
  username: string;
  role: Role;
  created_at: string;
  is_default_password: boolean;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Telemetry {
  temperature_c: number | null;
  humidity_pct: number | null;
  battery_pct: number | null;
  tank_level_pct: number | null;
  rssi_dbm: number | null;
  pump_state: "idle" | "running" | "fault" | null;
}

export type Connectivity = "online" | "offline" | "never_seen";

export interface Device {
  id: string;
  name: string;
  source: "simulator" | "esp32";
  simulated: boolean;
  location: string | null;
  firmware_version: string | null;
  capabilities: { camera: boolean; pump: boolean; sensors: string[]; max_spray_duration_s: number };
  connectivity: Connectivity;
  reported_status: "ok" | "warning" | "error" | null;
  last_seen: string | null;
  last_telemetry: Telemetry | null;
  uptime_s: number | null;
  created_at: string;
  last_spray_completed_at: string | null;
}

export interface TelemetryPoint {
  ts: string;
  simulated: boolean;
  telemetry: Telemetry;
}

export interface DeviceCommand {
  id: string;
  device_id: string;
  type: "SPRAY" | "STOP";
  params: Record<string, unknown>;
  status: string;
  operation_id: string | null;
  created_at: string;
  expires_at: string | null;
  delivered_at: string | null;
  acknowledged_at: string | null;
  finished_at: string | null;
  result_message: string | null;
}

export type DecisionOutcome = "AUTHORIZED" | "PENDING_APPROVAL" | "BLOCKED" | "REVIEW_REQUIRED" | "SKIP";

export interface RuleResult {
  rule: string;
  passed: boolean | null;
  critical: boolean;
  message: string;
}

export interface Decision {
  outcome: DecisionOutcome;
  reasons: string[];
  rules: RuleResult[];
  policy_version: number;
  evaluated_at: string;
  stage: "scan" | "approval";
}

export type DiseaseLabel = "healthy" | "early_blight" | "late_blight";

export interface Prediction {
  status: "CONFIDENT" | "UNCERTAIN" | "MODEL_UNAVAILABLE";
  crop: string;
  label: DiseaseLabel | null;
  display_label: string;
  top_label: DiseaseLabel | null;
  confidence: number | null;
  probabilities: Record<string, number>;
  threshold: number;
  model_version: string | null;
  inference_ms: number | null;
  warnings: string[];
  timestamp: string;
}

export interface Scan {
  id: string;
  created_at: string;
  source: "dashboard" | "device" | "simulator";
  simulated: boolean;
  device_id: string | null;
  submitted_by: string | null;
  original_filename: string | null;
  content_type: string;
  size_bytes: number;
  quality: { width: number; height: number; brightness: number; sharpness: number; green_ratio: number };
  prediction: Prediction;
  decision: Decision;
  spray_operation_id: string | null;
  notes: string | null;
}

export type OperationStatus =
  | "PENDING_APPROVAL"
  | "BLOCKED"
  | "DISPATCHED"
  | "RUNNING"
  | "COMPLETED"
  | "FAILED"
  | "ABORTED"
  | "REJECTED"
  | "EXPIRED";

export interface SprayOperation {
  id: string;
  scan_id: string | null;
  device_id: string | null;
  simulated: boolean;
  status: OperationStatus;
  label: string | null;
  confidence: number | null;
  duration_s: number;
  decision: Decision;
  command_id: string | null;
  approved_by: string | null;
  created_at: string;
  updated_at: string;
  expires_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  history: { ts: string; status: OperationStatus; actor: string; message: string }[];
}

export interface WeatherPolicy {
  enabled: boolean;
  blocking: boolean;
  max_wind_kmh: number;
  max_precip_probability_pct: number;
}

export interface SprayPolicy {
  version: number;
  confidence_threshold: number;
  min_confidence_margin: number;
  sprayable_labels: string[];
  require_operator_approval: boolean;
  spray_duration_s: number;
  max_spray_duration_s: number;
  cooldown_s: number;
  device_offline_timeout_s: number;
  min_tank_level_pct: number;
  min_battery_pct: number;
  pending_approval_ttl_s: number;
  command_ack_timeout_s: number;
  weather: WeatherPolicy;
  updated_at: string | null;
  updated_by: string | null;
}

export interface EmergencyStop {
  active: boolean;
  activated_at: string | null;
  activated_by: string | null;
  reason: string | null;
  reset_at: string | null;
  reset_by: string | null;
  reset_reason: string | null;
}

export interface LiveEvent {
  id?: string;
  type: string;
  ts: string;
  simulated?: boolean;
  data: Record<string, unknown>;
}

export interface Summary {
  generated_at: string;
  scans: { total: number; last_24h: number; diseased_last_24h: number; review_required_last_24h: number; simulated_total: number };
  devices: { total: number; online: number; offline: number; simulated: number; real: number };
  operations: { pending_approval: number; active: number; completed: number; blocked: number; failed: number; aborted: number; by_status: Record<string, number> };
  emergency_stop: EmergencyStop;
  recent_events: LiveEvent[];
  model: { state: string; version: string | null };
  database_mode: "mongodb" | "memory";
}

export interface Analytics {
  range: { start: string; end: string; days: number };
  totals: { scans: number; operations: number; simulated_scans: number; completed_spray_seconds: number; truncated: boolean };
  scans_per_day: { date: string; healthy: number; early_blight: number; late_blight: number; uncertain: number; avg_confidence: number | null }[];
  operations_per_day: ({ date: string } & Record<string, number | string>)[];
  label_distribution: Record<string, number>;
  decision_outcomes: Record<string, number>;
  operation_status: Record<string, number>;
  confidence_histogram: { bucket: string; count: number }[];
  scans_by_device: Record<string, number>;
}

export interface ExternalData<T> {
  available: boolean;
  freshness: "live" | "cached" | "stale" | "unavailable";
  fetched_at: string | null;
  age_seconds: number | null;
  source: string;
  source_url: string;
  license: string;
  attribution: string;
  error: string | null;
  data: T | null;
}

export interface Forecast {
  location: { name: string; lat: number; lon: number; elevation_m: number; timezone: string };
  current: Record<string, number | string>;
  current_units: Record<string, string>;
  next_3h_max_precipitation_probability: number | null;
  daily: Record<string, (number | string | null)[]>;
  daily_units: Record<string, string>;
  hourly: Record<string, (number | string | null)[]>;
  blight_favourable_hours_7d: number;
  blight_heuristic_note: string;
}

export interface Climate {
  location: { name: string; lat: number; lon: number };
  series: ({ date: string } & Record<string, number | null | string>)[];
  units: Record<string, string>;
  latest_available_date: string | null;
}

export interface DataSource {
  id: string;
  name: string;
  url: string;
  license: string;
  attribution?: string;
  status: "integrated" | "not_integrated" | "reference";
  used_for?: string;
  note?: string;
}

export interface SystemInfo {
  app: { name: string; version: string; environment: string };
  database: { mode: string; name: string; persistent: boolean };
  model: {
    state: string;
    error: string | null;
    model_version: string | null;
    architecture: string | null;
    classes: { id: string; name: string }[];
    input_size: number | null;
    preprocessing: string | null;
    trained_at: string | null;
    metrics: ModelMetrics | null;
    dataset: Record<string, unknown>;
    disclaimer: string;
  };
  simulator: { enabled: boolean; tick_seconds: number; devices: number };
  uploads: { max_mb: number; retention_days: number; allowed: string[] };
  location: { name: string; lat: number; lon: number };
  security: { dev_admin_password_in_use: boolean; cors_origins: string[]; token_ttl_minutes: number };
  realtime: { websocket_subscribers: number };
}

export interface ModelMetrics {
  split: string;
  n_test: number;
  accuracy: number;
  macro_precision: number;
  macro_recall: number;
  macro_f1: number;
  per_class: Record<string, { precision: number; recall: number; f1: number; support: number }>;
  confusion_matrix: { labels: string[]; rows_true_cols_pred: number[][] };
  at_recommended_threshold: { threshold: number; coverage: number; accuracy_on_confident: number; routed_to_review: number };
  inference_time: { device: string; single_image_ms_mean: number; single_image_ms_p95: number; batch32_throughput_img_per_s: number };
  caveat: string;
}

export interface SimulatorStatus {
  enabled: boolean;
  tick_seconds: number;
  devices: {
    device_id: string;
    connected: boolean;
    mode: string;
    tank_level_pct: number;
    battery_pct: number;
    pump_running: boolean;
    fail_next_command: boolean;
    ignore_commands: boolean;
    sensor_fault: boolean;
  }[];
  samples: Record<string, string[]>;
}

export interface LogEntry {
  id: string;
  ts: string;
  level: "debug" | "info" | "warning" | "error" | "critical";
  category: string;
  action: string;
  message: string;
  actor: string | null;
  device_id: string | null;
  simulated: boolean;
  request_id: string | null;
  context: Record<string, unknown>;
}
