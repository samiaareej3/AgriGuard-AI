"use client";

import { useEffect, useMemo, useState } from "react";
import { Activity, Cpu, Radio } from "lucide-react";
import { ChartFrame, Lines, clock } from "@/components/charts";
import { ConnectivityPill, EmptyState, PageHeader, SimBadge, TimeAgo } from "@/components/common";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { num } from "@/lib/format";
import { useDevices, useTelemetry } from "@/lib/queries";
import { useRealtime } from "@/lib/realtime";
import type { LiveEvent, Telemetry } from "@/lib/types";

type Point = { ts: string; temperature_c: number | null; humidity_pct: number | null; tank_level_pct: number | null; battery_pct: number | null };

const toPoint = (ts: string, t: Telemetry): Point => ({
  ts, temperature_c: t.temperature_c, humidity_pct: t.humidity_pct, tank_level_pct: t.tank_level_pct, battery_pct: t.battery_pct,
});

const EVENT_LABEL: Record<string, string> = {
  "scan.created": "Scan", "spray.updated": "Spray", "device.connectivity": "Connectivity", "device.updated": "Device",
  "command.queued": "Command", "estop.changed": "E-stop", "policy.updated": "Policy", "log.created": "Log",
};

export default function MonitoringPage() {
  const devices = useDevices();
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [minutes, setMinutes] = useState("15");
  const history = useTelemetry(deviceId, Number(minutes));
  const { events, subscribe, state } = useRealtime();
  const [live, setLive] = useState<Point[]>([]);

  useEffect(() => {
    if (!deviceId && devices.data?.length) setDeviceId(devices.data[0].id);
  }, [devices.data, deviceId]);

  useEffect(() => setLive([]), [deviceId, minutes]);

  useEffect(() => subscribe((e: LiveEvent) => {
    if (e.type !== "device.heartbeat" || e.data.id !== deviceId) return;
    const t = e.data.telemetry as Telemetry;
    setLive((prev) => [...prev, toPoint(String(e.data.ts ?? e.ts), t)].slice(-400));
  }), [subscribe, deviceId]);

  const points: Point[] = useMemo(() => {
    const base = (history.data ?? []).map((p) => toPoint(p.ts, p.telemetry));
    const lastTs = base.length ? base[base.length - 1].ts : "";
    const cutoff = Date.now() - Number(minutes) * 60000;
    return [...base, ...live.filter((p) => p.ts > lastTs)].filter((p) => new Date(p.ts).getTime() >= cutoff);
  }, [history.data, live, minutes]);

  const device = devices.data?.find((d) => d.id === deviceId);
  const latest = points[points.length - 1];

  return (
    <>
      <PageHeader title="Live monitoring" description="Heartbeats and sensor telemetry stream in real time over WebSocket. Simulated values are labelled."
        actions={<span className="flex items-center gap-1.5 text-xs text-muted-foreground"><Radio className={`size-4 ${state === "live" ? "text-good" : "text-warning"}`} /> Stream {state}</span>} />

      <div className="mb-6 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {devices.data?.map((d) => (
          <button key={d.id} onClick={() => setDeviceId(d.id)} aria-pressed={d.id === deviceId}
            className={`rounded-xl border bg-card p-4 text-left transition-colors hover:bg-muted/40 focus-visible:outline-2 focus-visible:outline-primary ${d.id === deviceId ? "ring-2 ring-primary" : ""}`}>
            <div className="flex items-center justify-between gap-2">
              <p className="truncate text-sm font-medium">{d.name}</p>
              <ConnectivityPill state={d.connectivity} />
            </div>
            <p className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">{d.simulated && <SimBadge />} seen <TimeAgo iso={d.last_seen} /></p>
          </button>
        ))}
      </div>

      {!devices.data?.length ? (
        <EmptyState icon={Cpu} title="No devices to monitor" description="Add a simulated device on the Devices page." />
      ) : (
        <div className="grid gap-6 xl:grid-cols-3">
          <div className="min-w-0 space-y-6 xl:col-span-2">
            <div className="flex flex-wrap items-center gap-2">
              <Select value={deviceId ?? undefined} onValueChange={setDeviceId}>
                <SelectTrigger className="w-64" aria-label="Device"><SelectValue placeholder="Device" /></SelectTrigger>
                <SelectContent>{devices.data.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}</SelectContent>
              </Select>
              <Select value={minutes} onValueChange={setMinutes}>
                <SelectTrigger className="w-36" aria-label="Time window"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="5">Last 5 min</SelectItem>
                  <SelectItem value="15">Last 15 min</SelectItem>
                  <SelectItem value="60">Last hour</SelectItem>
                </SelectContent>
              </Select>
              {device?.simulated && <SimBadge />}
              <span className="text-xs text-muted-foreground">{points.length} readings</span>
            </div>
            <div className="grid gap-3 sm:grid-cols-4">
              {[
                ["Temperature", num(latest?.temperature_c, 1, " °C")],
                ["Humidity", num(latest?.humidity_pct, 0, " %")],
                ["Tank level", num(latest?.tank_level_pct, 0, " %")],
                ["Battery", num(latest?.battery_pct, 0, " %")],
              ].map(([k, v]) => (
                <div key={k} className="rounded-xl border bg-card p-3">
                  <p className="text-xs text-muted-foreground">{k}</p>
                  <p className="tabular text-xl font-semibold">{v}</p>
                </div>
              ))}
            </div>
            {points.length === 0 ? (
              <EmptyState icon={Activity} title="No telemetry in this window" description={device?.connectivity === "online" ? "Waiting for the next heartbeat…" : "Device is not sending heartbeats."} />
            ) : (
              <>
                <ChartFrame title="Temperature (°C)" description={device?.simulated ? "Simulated sensor" : "Device sensor"}
                  table={{ columns: ["Time", "°C"], rows: points.map((p) => [clock(p.ts), p.temperature_c ?? "—"]) }} height={200}>
                  <Lines data={points} xKey="ts" xFormatter={clock} series={[{ key: "temperature_c", label: "Temperature", color: "var(--series-early)" }]} yFormatter={(v) => `${v.toFixed(1)}`} />
                </ChartFrame>
                <ChartFrame title="Tank level and battery (%)" series={[{ key: "tank_level_pct", label: "Tank level", color: "var(--series-late)" }, { key: "battery_pct", label: "Battery", color: "var(--series-healthy)" }]}
                  table={{ columns: ["Time", "Tank %", "Battery %"], rows: points.map((p) => [clock(p.ts), p.tank_level_pct ?? "—", p.battery_pct ?? "—"]) }} height={200}>
                  <Lines data={points} xKey="ts" xFormatter={clock} domain={[0, 100]}
                    series={[{ key: "tank_level_pct", label: "Tank level", color: "var(--series-late)" }, { key: "battery_pct", label: "Battery", color: "var(--series-healthy)" }]} />
                </ChartFrame>
              </>
            )}
          </div>
          <Card className="h-fit">
            <CardHeader><CardTitle className="flex items-center gap-2 text-sm"><Activity className="size-4" /> Live event feed</CardTitle></CardHeader>
            <CardContent>
              {events.length === 0 ? <p className="text-sm text-muted-foreground">Waiting for events…</p> : (
                <ol className="max-h-[640px] space-y-2 overflow-y-auto pr-1" aria-live="polite">
                  {events.filter((e) => e.type !== "log.created").slice(0, 60).map((e, i) => (
                    <li key={e.id ?? i} className="rounded-lg border p-2 text-xs">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium">{EVENT_LABEL[e.type] ?? e.type}</span>
                        <span className="text-muted-foreground"><TimeAgo iso={e.ts} /></span>
                      </div>
                      <p className="mt-0.5 text-muted-foreground">{describe(e)}</p>
                      {e.simulated && <SimBadge className="mt-1" />}
                    </li>
                  ))}
                </ol>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </>
  );
}

function describe(e: LiveEvent): string {
  const d = e.data as Record<string, unknown>;
  switch (e.type) {
    case "scan.created": {
      const p = d.prediction as { display_label: string };
      const dec = d.decision as { outcome: string };
      return `${p?.display_label} → ${dec?.outcome}`;
    }
    case "spray.updated": return `Operation ${String(d.id).slice(0, 10)} → ${d.status}`;
    case "device.connectivity": return `${d.name} is ${d.state}`;
    case "command.queued": return `${d.type} queued for ${String(d.device_id).slice(0, 10)}`;
    case "estop.changed": return d.active ? "Emergency stop ACTIVATED" : "Emergency stop reset";
    case "policy.updated": return `Policy v${d.version}`;
    default: return String(d.name ?? d.message ?? "");
  }
}
