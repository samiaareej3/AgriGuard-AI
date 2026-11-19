"use client";

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  BatteryMedium, Copy, Cpu, Droplets, FlaskConical, KeyRound, Plug, PlugZap, Plus, ScanSearch, Trash2, Unplug, Wifi, Zap,
} from "lucide-react";
import { toast } from "sonner";
import { ConnectivityPill, EmptyState, ErrorState, LoadingGrid, PageHeader, Pill, SimBadge, TimeAgo } from "@/components/common";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { duration, num } from "@/lib/format";
import { useAction, useDevices, useSimulator } from "@/lib/queries";
import type { Device, Scan, SimulatorStatus } from "@/lib/types";

const KEYS = [["devices"], ["simulator"], ["summary"]];

export default function DevicesPage() {
  const devices = useDevices();
  const sim = useSimulator();
  const { can } = useAuth();
  const simDevices = devices.data?.filter((d) => d.simulated) ?? [];
  const realDevices = devices.data?.filter((d) => !d.simulated) ?? [];

  return (
    <>
      <PageHeader
        title="Device management"
        description="Simulated ESP32-CAM units run the same device API contract the real firmware will use. Swap the simulator for hardware without touching the dashboard."
        actions={can("operator") && (<><AddSimDialog /><RegisterDeviceDialog /></>)}
      />
      {devices.isError ? <ErrorState error={devices.error} onRetry={() => devices.refetch()} /> : !devices.data ? <LoadingGrid count={2} className="xl:grid-cols-2" /> : (
        <div className="space-y-8">
          <section aria-labelledby="sim-h">
            <div className="mb-3 flex items-center gap-2">
              <h2 id="sim-h" className="text-sm font-semibold">Simulated devices</h2>
              <SimBadge />
              {sim.data && !sim.data.enabled && <span className="text-xs text-muted-foreground">Simulator disabled by configuration</span>}
            </div>
            {simDevices.length ? (
              <div className="grid gap-4 xl:grid-cols-2">
                {simDevices.map((d) => <DeviceCard key={d.id} device={d} sim={sim.data?.devices.find((s) => s.device_id === d.id)} />)}
              </div>
            ) : <EmptyState icon={FlaskConical} title="No simulated devices" description="Add one to demo the full detect → approve → spray workflow." />}
          </section>
          <section aria-labelledby="hw-h">
            <h2 id="hw-h" className="mb-3 text-sm font-semibold">Hardware devices (ESP32-CAM)</h2>
            {realDevices.length ? (
              <div className="grid gap-4 xl:grid-cols-2">{realDevices.map((d) => <DeviceCard key={d.id} device={d} />)}</div>
            ) : (
              <EmptyState icon={Cpu} title="No hardware registered yet"
                description="When the prototype is ready, register it here, flash the token into the firmware config and it will appear with live telemetry. See docs/ESP32_INTEGRATION.md." />
            )}
          </section>
        </div>
      )}
    </>
  );
}

function Metric({ icon: Icon, label, value }: { icon: React.ElementType; label: string; value: string }) {
  return (
    <div className="rounded-lg bg-muted/60 p-2.5">
      <p className="flex items-center gap-1 text-[11px] text-muted-foreground"><Icon className="size-3" aria-hidden />{label}</p>
      <p className="tabular mt-0.5 text-sm font-semibold">{value}</p>
    </div>
  );
}

function DeviceCard({ device: d, sim }: { device: Device; sim?: SimulatorStatus["devices"][number] }) {
  const { can } = useAuth();
  const t = d.last_telemetry;
  const del = useAction(() => api(`/devices/${d.id}`, { method: "DELETE" }), { success: "Device deleted", invalidate: KEYS });
  return (
    <Card className="gap-0 py-0">
      <CardHeader className="flex flex-row flex-wrap items-start gap-2 p-4">
        <div className="min-w-0 flex-1">
          <CardTitle className="truncate text-base">{d.name}</CardTitle>
          <p className="mt-0.5 text-xs text-muted-foreground">{d.location ?? "No location"} · fw {d.firmware_version ?? "?"} · <span className="font-mono">{d.id}</span></p>
        </div>
        <div className="flex items-center gap-1.5">
          <SimBadge simulated={d.simulated} />
          <ConnectivityPill state={d.connectivity} />
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-4 pt-0">
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
          <Metric icon={Droplets} label="Tank" value={num(t?.tank_level_pct, 0, "%")} />
          <Metric icon={BatteryMedium} label="Battery" value={num(t?.battery_pct, 0, "%")} />
          <Metric icon={Zap} label="Pump" value={t?.pump_state ?? "—"} />
          <Metric icon={Wifi} label="Signal" value={num(t?.rssi_dbm, 0, " dBm")} />
          <Metric icon={Cpu} label="Uptime" value={duration(d.uptime_s)} />
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          {d.reported_status && (
            <Pill tone={d.reported_status === "ok" ? "good" : d.reported_status === "warning" ? "warning" : "critical"} icon={Cpu}>
              Reports “{d.reported_status}”
            </Pill>
          )}
          <span>Last heartbeat <TimeAgo iso={d.last_seen} /></span>
          {d.last_spray_completed_at && <span>· last spray <TimeAgo iso={d.last_spray_completed_at} /></span>}
        </div>
        {d.simulated && sim && can("operator") && <SimControls device={d} sim={sim} />}
        {!d.simulated && can("admin") && <RotateToken device={d} />}
        {can("admin") && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="sm" className="text-critical"><Trash2 className="size-4" /> Delete device</Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Delete {d.name}?</AlertDialogTitle>
                <AlertDialogDescription>Its token stops working immediately and queued commands are cancelled. Historical scans and operations are kept.</AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction className="bg-critical text-white hover:bg-critical/90" onClick={() => del.mutate(undefined)}>Delete</AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </CardContent>
    </Card>
  );
}

function SimControls({ device: d, sim }: { device: Device; sim: SimulatorStatus["devices"][number] }) {
  const [sample, setSample] = useState("random");
  const [tank, setTank] = useState<number[] | null>(null);
  const conn = useAction((action: string) => api(`/simulator/devices/${d.id}/connection`, { body: { action } }), {
    success: "Simulator updated", invalidate: KEYS,
  });
  const faults = useAction((body: Record<string, unknown>) => api(`/simulator/devices/${d.id}`, { method: "PATCH", body }), {
    success: "Simulator updated", invalidate: KEYS,
  });
  const scan = useAction(() => api<Scan>(`/simulator/devices/${d.id}/scan`, { body: { sample_class: sample === "random" ? null : sample } }), {
    success: (s) => `Simulated scan: ${s.prediction.display_label} → ${s.decision.outcome.replace("_", " ").toLowerCase()}`,
    invalidate: [["scans"], ["operations"], ["summary"]],
  });
  return (
    <div className="space-y-3 rounded-lg border border-dashed border-sim/40 bg-sim/5 p-3">
      <p className="flex items-center gap-1.5 text-xs font-medium text-sim"><FlaskConical className="size-3.5" /> Simulator controls (demo only)</p>
      <div className="flex flex-wrap gap-2">
        {sim.connected ? (
          <>
            <Button size="sm" variant="outline" onClick={() => conn.mutate("disconnect")}><Unplug className="size-4" /> Graceful disconnect</Button>
            <Button size="sm" variant="outline" onClick={() => conn.mutate("connection_lost")}><PlugZap className="size-4" /> Simulate signal loss</Button>
          </>
        ) : (
          <Button size="sm" variant="outline" onClick={() => conn.mutate("connect")}><Plug className="size-4" /> Reconnect</Button>
        )}
        <div className="flex items-center gap-1">
          <Select value={sample} onValueChange={setSample}>
            <SelectTrigger size="sm" className="w-44" aria-label="Sample image class"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="random">Random sample</SelectItem>
              <SelectItem value="healthy">Healthy sample</SelectItem>
              <SelectItem value="early_blight">Early blight sample</SelectItem>
              <SelectItem value="late_blight">Late blight sample</SelectItem>
            </SelectContent>
          </Select>
          <Button size="sm" onClick={() => scan.mutate(undefined)} disabled={!sim.connected || scan.isPending} title={sim.connected ? undefined : "Device offline"}>
            <ScanSearch className="size-4" /> Capture
          </Button>
        </div>
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className="flex items-center justify-between gap-2 text-xs">Fail next command
          <Switch checked={sim.fail_next_command} onCheckedChange={(v) => faults.mutate({ fail_next_command: v })} />
        </label>
        <label className="flex items-center justify-between gap-2 text-xs">Ignore commands
          <Switch checked={sim.ignore_commands} onCheckedChange={(v) => faults.mutate({ ignore_commands: v })} />
        </label>
        <label className="flex items-center justify-between gap-2 text-xs">Sensor fault
          <Switch checked={sim.sensor_fault} onCheckedChange={(v) => faults.mutate({ sensor_fault: v })} />
        </label>
      </div>
      <div className="flex items-center gap-3 text-xs">
        <span className="w-24 shrink-0">Tank {Math.round(tank?.[0] ?? sim.tank_level_pct)}%</span>
        <Slider aria-label="Simulated tank level" min={0} max={100} step={1} value={tank ?? [sim.tank_level_pct]} onValueChange={setTank}
          onValueCommit={(v) => { faults.mutate({ tank_level_pct: v[0] }); setTank(null); }} />
        <Button size="sm" variant="ghost" onClick={() => faults.mutate({ tank_level_pct: 100, battery_pct: 100 })}>Refill &amp; charge</Button>
      </div>
    </div>
  );
}

function TokenReveal({ token, onClose }: { token: string; onClose: () => void }) {
  return (
    <div className="space-y-3">
      <p className="text-sm">Copy this device token now. It is shown <b>once</b>; only a hash is stored.</p>
      <div className="flex gap-2">
        <Input readOnly value={token} className="font-mono text-xs" aria-label="Device token" />
        <Button variant="outline" size="icon" aria-label="Copy token" onClick={() => navigator.clipboard.writeText(token).then(() => toast.success("Copied"))}><Copy className="size-4" /></Button>
      </div>
      <DialogFooter><Button onClick={onClose}>Done</Button></DialogFooter>
    </div>
  );
}

function RotateToken({ device }: { device: Device }) {
  const [token, setToken] = useState<string | null>(null);
  const rotate = useAction(() => api<{ device_token: string }>(`/devices/${device.id}/rotate-token`, { body: {} }), { onSuccess: (r) => setToken(r.device_token) });
  return (
    <Dialog open={!!token} onOpenChange={(o) => !o && setToken(null)}>
      <Button size="sm" variant="outline" onClick={() => rotate.mutate(undefined)}><KeyRound className="size-4" /> Rotate token</Button>
      <DialogContent>
        <DialogHeader><DialogTitle>New token for {device.name}</DialogTitle><DialogDescription>The previous token no longer works.</DialogDescription></DialogHeader>
        {token && <TokenReveal token={token} onClose={() => setToken(null)} />}
      </DialogContent>
    </Dialog>
  );
}

const deviceSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(64),
  location: z.string().trim().max(120).optional(),
});

function RegisterDeviceDialog() {
  const [open, setOpen] = useState(false);
  const [token, setToken] = useState<string | null>(null);
  const form = useForm<z.infer<typeof deviceSchema>>({ resolver: zodResolver(deviceSchema), defaultValues: { name: "", location: "" } });
  const create = useAction((v: z.infer<typeof deviceSchema>) => api<{ device_token: string }>("/devices", { body: { ...v, source: "esp32" } }), {
    success: "Device registered", invalidate: KEYS, onSuccess: (r) => setToken(r.device_token),
  });
  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setToken(null); form.reset(); } }}>
      <DialogTrigger asChild><Button variant="outline"><Cpu className="size-4" /> Register hardware</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Register an ESP32-CAM device</DialogTitle>
          <DialogDescription>Creates a device identity and a one-time API token for the firmware.</DialogDescription>
        </DialogHeader>
        {token ? <TokenReveal token={token} onClose={() => setOpen(false)} /> : (
          <form className="space-y-3" onSubmit={form.handleSubmit((v) => create.mutate(v))} noValidate>
            <div className="space-y-1.5">
              <Label htmlFor="dev-name">Name</Label>
              <Input id="dev-name" {...form.register("name")} aria-invalid={!!form.formState.errors.name} />
              {form.formState.errors.name && <p className="text-xs text-critical">{form.formState.errors.name.message}</p>}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="dev-loc">Location</Label>
              <Input id="dev-loc" {...form.register("location")} placeholder="e.g. Plot 3, row 12" />
            </div>
            <DialogFooter><Button type="submit" disabled={create.isPending}>Register</Button></DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}

function AddSimDialog() {
  const [open, setOpen] = useState(false);
  const form = useForm<z.infer<typeof deviceSchema>>({ resolver: zodResolver(deviceSchema), defaultValues: { name: "", location: "Demo farm (simulated)" } });
  const create = useAction((v: z.infer<typeof deviceSchema>) => api("/simulator/devices", { body: v }), {
    success: "Simulated device created", invalidate: KEYS, onSuccess: () => { setOpen(false); form.reset(); },
  });
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild><Button><Plus className="size-4" /> Add simulated device</Button></DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>Add simulated ESP32-CAM</DialogTitle><DialogDescription>Starts heartbeating immediately. Clearly labelled as simulated everywhere.</DialogDescription></DialogHeader>
        <form className="space-y-3" onSubmit={form.handleSubmit((v) => create.mutate(v))} noValidate>
          <div className="space-y-1.5">
            <Label htmlFor="sim-name">Name</Label>
            <Input id="sim-name" {...form.register("name")} aria-invalid={!!form.formState.errors.name} />
            {form.formState.errors.name && <p className="text-xs text-critical">{form.formState.errors.name.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="sim-loc">Location</Label>
            <Input id="sim-loc" {...form.register("location")} />
          </div>
          <DialogFooter><Button type="submit" disabled={create.isPending}>Create</Button></DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
