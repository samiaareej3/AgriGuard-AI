"use client";

import { useEffect, useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle, BrainCircuit, ChevronLeft, ChevronRight, KeyRound, ScrollText, Server, ShieldCheck, UserPlus, Users } from "lucide-react";
import { ErrorState, PageHeader, Pill, TimeAgo } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LABELS, dateTime, pct } from "@/lib/format";
import { useAction, useLogs, usePolicy, useSystemInfo, useUsers } from "@/lib/queries";
import type { SprayPolicy } from "@/lib/types";

export default function SettingsPage() {
  const { can } = useAuth();
  return (
    <>
      <PageHeader title="Settings" description="Safety policy, model information, accounts and system configuration." />
      <Tabs defaultValue="policy">
        <TabsList className="mb-4 h-auto flex-wrap">
          <TabsTrigger value="policy"><ShieldCheck className="size-4" /> Safety policy</TabsTrigger>
          <TabsTrigger value="model"><BrainCircuit className="size-4" /> Model</TabsTrigger>
          <TabsTrigger value="account"><KeyRound className="size-4" /> Account</TabsTrigger>
          {can("admin") && <TabsTrigger value="users"><Users className="size-4" /> Users</TabsTrigger>}
          <TabsTrigger value="system"><Server className="size-4" /> System</TabsTrigger>
          <TabsTrigger value="audit"><ScrollText className="size-4" /> Audit log</TabsTrigger>
        </TabsList>
        <TabsContent value="policy"><PolicyForm /></TabsContent>
        <TabsContent value="model"><ModelCard /></TabsContent>
        <TabsContent value="account"><AccountCard /></TabsContent>
        {can("admin") && <TabsContent value="users"><UsersCard /></TabsContent>}
        <TabsContent value="system"><SystemCard /></TabsContent>
        <TabsContent value="audit"><AuditLog /></TabsContent>
      </Tabs>
    </>
  );
}

const policySchema = z.object({
  confidence_threshold: z.coerce.number().min(0.5).max(0.99),
  min_confidence_margin: z.coerce.number().min(0).max(0.9),
  require_operator_approval: z.boolean(),
  spray_duration_s: z.coerce.number().gt(0).max(60),
  max_spray_duration_s: z.coerce.number().gt(0).max(60),
  cooldown_s: z.coerce.number().min(0).max(86400),
  device_offline_timeout_s: z.coerce.number().min(5).max(3600),
  min_tank_level_pct: z.coerce.number().min(0).max(100),
  min_battery_pct: z.coerce.number().min(0).max(100),
  pending_approval_ttl_s: z.coerce.number().min(30).max(86400),
  command_ack_timeout_s: z.coerce.number().min(3).max(600),
  weather: z.object({
    enabled: z.boolean(),
    blocking: z.boolean(),
    max_wind_kmh: z.coerce.number().gt(0).max(100),
    max_precip_probability_pct: z.coerce.number().min(0).max(100),
  }),
}).refine((v) => v.spray_duration_s <= v.max_spray_duration_s, { path: ["spray_duration_s"], message: "Cannot exceed the maximum duration" });
type PolicyValues = z.infer<typeof policySchema>;

const FIELDS: { name: keyof PolicyValues; label: string; help: string; step?: string }[] = [
  { name: "confidence_threshold", label: "Confidence threshold (0.50–0.99)", help: "Below this, predictions become “Review required”.", step: "0.01" },
  { name: "min_confidence_margin", label: "Minimum top-2 margin", help: "Rejects ambiguous predictions between two classes.", step: "0.01" },
  { name: "spray_duration_s", label: "Spray duration (s)", help: "Requested pump run time per operation.", step: "0.5" },
  { name: "max_spray_duration_s", label: "Maximum spray duration (s)", help: "Hard limit; also capped by device capability.", step: "0.5" },
  { name: "cooldown_s", label: "Cooldown between sprays (s)", help: "Per device, after any pump activation." },
  { name: "device_offline_timeout_s", label: "Offline after no heartbeat for (s)", help: "Devices are marked offline after this." },
  { name: "min_tank_level_pct", label: "Minimum tank level (%)", help: "Device is unhealthy below this." },
  { name: "min_battery_pct", label: "Minimum battery (%)", help: "Device is unhealthy below this." },
  { name: "pending_approval_ttl_s", label: "Approval window (s)", help: "Pending operations expire after this." },
  { name: "command_ack_timeout_s", label: "Command acknowledgement timeout (s)", help: "Operation fails if the device does not acknowledge." },
];

function PolicyForm() {
  const { can } = useAuth();
  const policy = usePolicy();
  const editable = can("admin");
  const form = useForm<PolicyValues>({ resolver: zodResolver(policySchema) as never });
  useEffect(() => { if (policy.data) form.reset(policy.data as unknown as PolicyValues); }, [policy.data, form]);
  const save = useAction((v: PolicyValues) => api<SprayPolicy>("/spray/policy", { method: "PUT", body: { ...v, expected_version: policy.data?.version } }), {
    success: (p) => `Policy saved as v${p.version}`, invalidate: [["policy"]],
  });
  if (policy.isError) return <ErrorState error={policy.error} onRetry={() => policy.refetch()} />;
  if (!policy.data) return <Skeleton className="h-96 rounded-xl" />;
  const err = form.formState.errors;
  return (
    <form onSubmit={form.handleSubmit((v) => save.mutate(v))} noValidate>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Spray authorization policy · v{policy.data.version}</CardTitle>
          <CardDescription>
            Last changed by {policy.data.updated_by ?? "system"} <TimeAgo iso={policy.data.updated_at} />.
            Sprayable classes: {policy.data.sprayable_labels.map((l) => LABELS[l] ?? l).join(", ")} (fixed to the model&apos;s validated scope).
            {!editable && " Read-only: admin role required to edit."}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <fieldset disabled={!editable} className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
            {FIELDS.map((f) => (
              <div key={f.name} className="space-y-1">
                <Label htmlFor={f.name}>{f.label}</Label>
                <Input id={f.name} type="number" step={f.step ?? "1"} {...form.register(f.name)} aria-invalid={!!err[f.name]} aria-describedby={`${f.name}-help`} />
                <p id={`${f.name}-help`} className={`text-xs ${err[f.name] ? "text-critical" : "text-muted-foreground"}`}>{(err[f.name]?.message as string) ?? f.help}</p>
              </div>
            ))}
          </fieldset>
          <fieldset disabled={!editable} className="grid gap-4 rounded-lg border p-4 sm:grid-cols-2">
            <legend className="px-1 text-sm font-medium">Approval &amp; weather</legend>
            <ToggleRow form={form} name="require_operator_approval" label="Require operator approval" help="Strongly recommended. When off, authorized operations dispatch automatically." />
            <ToggleRow form={form} name="weather.enabled" label="Check weather" help="Wind and rain probability from the cached Open-Meteo forecast." />
            <ToggleRow form={form} name="weather.blocking" label="Weather is blocking" help="If off, weather problems are warnings only." />
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label htmlFor="wind">Max wind (km/h)</Label>
                <Input id="wind" type="number" {...form.register("weather.max_wind_kmh")} />
              </div>
              <div className="space-y-1">
                <Label htmlFor="rain">Max rain probability (%)</Label>
                <Input id="rain" type="number" {...form.register("weather.max_precip_probability_pct")} />
              </div>
            </div>
          </fieldset>
          {form.watch("require_operator_approval") === false && (
            <p className="flex items-center gap-2 text-sm text-amber-700 dark:text-amber-300"><AlertTriangle className="size-4" /> Automatic dispatch is enabled: all other safety rules still apply.</p>
          )}
          {editable && (
            <div className="flex gap-2">
              <Button type="submit" disabled={save.isPending || !form.formState.isDirty}>Save policy</Button>
              <Button type="button" variant="ghost" onClick={() => form.reset(policy.data as unknown as PolicyValues)} disabled={!form.formState.isDirty}>Discard changes</Button>
            </div>
          )}
        </CardContent>
      </Card>
    </form>
  );
}

function ToggleRow({ form, name, label, help }: { form: ReturnType<typeof useForm<PolicyValues>>; name: "require_operator_approval" | "weather.enabled" | "weather.blocking"; label: string; help: string }) {
  return (
    <Controller control={form.control} name={name} render={({ field }) => (
      <div className="flex items-start justify-between gap-3">
        <div>
          <Label htmlFor={name}>{label}</Label>
          <p className="text-xs text-muted-foreground">{help}</p>
        </div>
        <Switch id={name} checked={!!field.value} onCheckedChange={field.onChange} />
      </div>
    )} />
  );
}

function ModelCard() {
  const info = useSystemInfo();
  if (info.isError) return <ErrorState error={info.error} onRetry={() => info.refetch()} />;
  if (!info.data) return <Skeleton className="h-96 rounded-xl" />;
  const m = info.data.model;
  const met = m.metrics;
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Classifier</CardTitle>
          <CardDescription>{m.disclaimer}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <Row k="State" v={<Pill tone={m.state === "ready" ? "good" : "serious"} icon={BrainCircuit}>{m.state}</Pill>} />
          {m.error && <Row k="Error" v={m.error} />}
          <Row k="Version" v={m.model_version ?? "—"} />
          <Row k="Architecture" v={m.architecture ?? "—"} />
          <Row k="Classes" v={m.classes.map((c) => c.name).join(", ") || "—"} />
          <Row k="Input / preprocessing" v={`${m.input_size ?? "?"}px · ${m.preprocessing ?? "—"}`} />
          <Row k="Trained" v={dateTime(m.trained_at)} />
          <Row k="Dataset" v={`${m.dataset.dataset ?? "—"} (${m.dataset.license ?? "license unknown"})`} />
          <Row k="Split" v={String(m.dataset.split_method ?? "—")} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Measured performance</CardTitle>
          <CardDescription>{met ? met.split : "No evaluation recorded"}</CardDescription>
        </CardHeader>
        {met && (
          <CardContent className="space-y-4 text-sm">
            <div className="grid grid-cols-3 gap-3">
              {[["Accuracy", met.accuracy], ["Macro F1", met.macro_f1], ["Macro recall", met.macro_recall]].map(([k, v]) => (
                <div key={k as string} className="rounded-lg bg-muted/60 p-3"><p className="text-xs text-muted-foreground">{k}</p><p className="tabular text-xl font-semibold">{pct(v as number, 1)}</p></div>
              ))}
            </div>
            <table className="w-full text-sm">
              <caption className="mb-1 text-left text-xs text-muted-foreground">Per class (n = {met.n_test} held-out test images)</caption>
              <thead className="text-left text-xs text-muted-foreground"><tr><th className="py-1">Class</th><th>Precision</th><th>Recall</th><th>F1</th><th>n</th></tr></thead>
              <tbody className="tabular">
                {Object.entries(met.per_class).map(([c, r]) => (
                  <tr key={c} className="border-t"><td className="py-1">{LABELS[c] ?? c}</td><td>{pct(r.precision, 1)}</td><td>{pct(r.recall, 1)}</td><td>{pct(r.f1, 1)}</td><td>{r.support}</td></tr>
                ))}
              </tbody>
            </table>
            <table className="w-full text-xs">
              <caption className="mb-1 text-left text-muted-foreground">Confusion matrix (rows = true, columns = predicted)</caption>
              <thead><tr><th /> {met.confusion_matrix.labels.map((l) => <th key={l} className="px-1 py-1 font-medium">{LABELS[l]}</th>)}</tr></thead>
              <tbody className="tabular">
                {met.confusion_matrix.rows_true_cols_pred.map((row, i) => (
                  <tr key={i} className="border-t"><th className="py-1 pr-2 text-left font-medium">{LABELS[met.confusion_matrix.labels[i]]}</th>{row.map((v, j) => <td key={j} className={`text-center ${i === j ? "font-semibold" : "text-muted-foreground"}`}>{v}</td>)}</tr>
                ))}
              </tbody>
            </table>
            <p className="text-xs text-muted-foreground">
              At threshold {pct(met.at_recommended_threshold.threshold)}: {pct(met.at_recommended_threshold.coverage, 1)} of test images auto-labelled with{" "}
              {pct(met.at_recommended_threshold.accuracy_on_confident, 1)} accuracy; {met.at_recommended_threshold.routed_to_review} routed to review.
              Inference ≈ {met.inference_time.single_image_ms_mean} ms/image ({met.inference_time.device}).
            </p>
            <p className="flex items-start gap-2 rounded-lg border border-warning/40 bg-warning/10 p-2 text-xs"><AlertTriangle className="mt-0.5 size-3.5 shrink-0" />{met.caveat}</p>
          </CardContent>
        )}
      </Card>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return <div className="grid grid-cols-[150px_1fr] gap-2"><span className="text-muted-foreground">{k}</span><span className="min-w-0 break-words">{v}</span></div>;
}

const pwSchema = z.object({
  current_password: z.string().min(1, "Required"),
  new_password: z.string().min(10, "At least 10 characters"),
  confirm: z.string(),
}).refine((v) => v.new_password === v.confirm, { path: ["confirm"], message: "Passwords do not match" });

function AccountCard() {
  const { user, refresh } = useAuth();
  const form = useForm<z.infer<typeof pwSchema>>({ resolver: zodResolver(pwSchema), defaultValues: { current_password: "", new_password: "", confirm: "" } });
  const change = useAction((v: z.infer<typeof pwSchema>) => api("/auth/change-password", { body: { current_password: v.current_password, new_password: v.new_password } }), {
    success: "Password changed", onSuccess: () => { form.reset(); refresh(); },
  });
  const e = form.formState.errors;
  return (
    <Card className="max-w-xl">
      <CardHeader>
        <CardTitle className="text-base">{user?.username}</CardTitle>
        <CardDescription className="capitalize">Role: {user?.role}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {user?.is_default_password && (
          <p role="alert" className="flex items-center gap-2 rounded-lg border border-critical/30 bg-critical/10 p-3 text-sm"><AlertTriangle className="size-4" /> You are using the development default password. Change it now.</p>
        )}
        <form className="space-y-3" onSubmit={form.handleSubmit((v) => change.mutate(v))} noValidate>
          {(["current_password", "new_password", "confirm"] as const).map((n) => (
            <div key={n} className="space-y-1">
              <Label htmlFor={n}>{n === "current_password" ? "Current password" : n === "new_password" ? "New password" : "Confirm new password"}</Label>
              <Input id={n} type="password" autoComplete={n === "current_password" ? "current-password" : "new-password"} {...form.register(n)} aria-invalid={!!e[n]} />
              {e[n] && <p className="text-xs text-critical">{e[n]?.message}</p>}
            </div>
          ))}
          <Button type="submit" disabled={change.isPending}>Change password</Button>
        </form>
      </CardContent>
    </Card>
  );
}

const userSchema = z.object({
  username: z.string().min(3).max(32).regex(/^[a-zA-Z0-9_.-]+$/, "Letters, digits, . _ - only"),
  password: z.string().min(10, "At least 10 characters"),
  role: z.enum(["viewer", "operator", "admin"]),
});

function UsersCard() {
  const users = useUsers(true);
  const form = useForm<z.infer<typeof userSchema>>({ resolver: zodResolver(userSchema), defaultValues: { username: "", password: "", role: "operator" } });
  const create = useAction((v: z.infer<typeof userSchema>) => api("/users", { body: v }), { success: "User created", invalidate: [["users"]], onSuccess: () => form.reset() });
  const e = form.formState.errors;
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Card>
        <CardHeader><CardTitle className="text-base">Accounts</CardTitle></CardHeader>
        <CardContent>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground"><tr><th className="py-1">User</th><th>Role</th><th>Created</th></tr></thead>
            <tbody>
              {users.data?.map((u) => (
                <tr key={u.id} className="border-t"><td className="py-2">{u.username}{u.is_default_password && <span className="ml-2 text-xs text-critical">default password</span>}</td><td className="capitalize">{u.role}</td><td className="text-muted-foreground"><TimeAgo iso={u.created_at} /></td></tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add user</CardTitle>
          <CardDescription>Viewer: read-only · Operator: scans, approvals, e-stop · Admin: policy, users, e-stop reset</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-3" onSubmit={form.handleSubmit((v) => create.mutate(v))} noValidate>
            <div className="space-y-1"><Label htmlFor="nu">Username</Label><Input id="nu" {...form.register("username")} aria-invalid={!!e.username} />{e.username && <p className="text-xs text-critical">{e.username.message}</p>}</div>
            <div className="space-y-1"><Label htmlFor="np">Password</Label><Input id="np" type="password" autoComplete="new-password" {...form.register("password")} aria-invalid={!!e.password} />{e.password && <p className="text-xs text-critical">{e.password.message}</p>}</div>
            <div className="space-y-1">
              <Label htmlFor="nr">Role</Label>
              <Controller control={form.control} name="role" render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id="nr" className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="viewer">Viewer</SelectItem><SelectItem value="operator">Operator</SelectItem><SelectItem value="admin">Admin</SelectItem></SelectContent>
                </Select>
              )} />
            </div>
            <Button type="submit" disabled={create.isPending}><UserPlus className="size-4" /> Create user</Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function SystemCard() {
  const info = useSystemInfo();
  if (!info.data) return <Skeleton className="h-64 rounded-xl" />;
  const s = info.data;
  return (
    <Card className="max-w-3xl">
      <CardHeader>
        <CardTitle className="text-base">{s.app.name} {s.app.version}</CardTitle>
        <CardDescription>Server configuration is set through environment variables (backend/.env); see docs/SETUP.md.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <Row k="Environment" v={s.app.environment} />
        <Row k="Database" v={s.database.persistent ? `MongoDB (${s.database.name})` : <Pill tone="warning" icon={AlertTriangle}>In-memory (not persistent)</Pill>} />
        <Row k="Simulator" v={s.simulator.enabled ? `Enabled · ${s.simulator.devices} device(s) · tick ${s.simulator.tick_seconds}s` : "Disabled"} />
        <Row k="Uploads" v={`${s.uploads.allowed.join(", ")} · max ${s.uploads.max_mb} MB · images kept ${s.uploads.retention_days} days`} />
        <Row k="Location" v={`${s.location.name} (${s.location.lat}, ${s.location.lon})`} />
        <Row k="CORS allowlist" v={s.security.cors_origins.join(", ")} />
        <Row k="Session lifetime" v={`${s.security.token_ttl_minutes} minutes`} />
        <Row k="Live connections" v={s.realtime.websocket_subscribers} />
        {s.security.dev_admin_password_in_use && <p className="flex items-center gap-2 text-critical"><AlertTriangle className="size-4" /> ADMIN_PASSWORD not set: development default in use.</p>}
      </CardContent>
    </Card>
  );
}

function AuditLog() {
  const [category, setCategory] = useState("all");
  const [level, setLevel] = useState("all");
  const [page, setPage] = useState(1);
  const logs = useLogs({ category: category === "all" ? undefined : category, level: level === "all" ? undefined : level, page });
  const pages = logs.data ? Math.max(1, Math.ceil(logs.data.total / logs.data.page_size)) : 1;
  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center gap-2">
        <CardTitle className="mr-auto text-base">Audit log</CardTitle>
        <Select value={category} onValueChange={(v) => { setCategory(v); setPage(1); }}>
          <SelectTrigger className="w-40" aria-label="Category"><SelectValue /></SelectTrigger>
          <SelectContent>{["all", "scan", "spray", "command", "device", "safety", "policy", "auth", "simulator"].map((c) => <SelectItem key={c} value={c}>{c === "all" ? "All categories" : c}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={level} onValueChange={(v) => { setLevel(v); setPage(1); }}>
          <SelectTrigger className="w-36" aria-label="Level"><SelectValue /></SelectTrigger>
          <SelectContent>{["all", "info", "warning", "error", "critical"].map((c) => <SelectItem key={c} value={c}>{c === "all" ? "All levels" : c}</SelectItem>)}</SelectContent>
        </Select>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {logs.isError ? <ErrorState error={logs.error} /> : (
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground"><tr><th className="py-1 pr-3">Time</th><th className="pr-3">Level</th><th className="pr-3">Category</th><th className="pr-3">Message</th><th>Actor</th></tr></thead>
            <tbody>
              {logs.data?.items.map((l) => (
                <tr key={l.id} className="border-t align-top">
                  <td className="whitespace-nowrap py-1.5 pr-3 text-xs text-muted-foreground">{dateTime(l.ts)}</td>
                  <td className="pr-3"><span className={`text-xs font-medium ${l.level === "error" || l.level === "critical" ? "text-critical" : l.level === "warning" ? "text-amber-700 dark:text-amber-300" : ""}`}>{l.level}</span></td>
                  <td className="pr-3 text-xs">{l.category}</td>
                  <td className="pr-3">{l.message}{l.simulated && <span className="ml-1 text-xs text-sim">(simulated)</span>}</td>
                  <td className="text-xs text-muted-foreground">{l.actor ?? "system"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="mt-3 flex items-center justify-end gap-2 text-xs text-muted-foreground">
          {logs.data?.total ?? 0} entries · page {page}/{pages}
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} aria-label="Previous page"><ChevronLeft className="size-4" /></Button>
          <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)} aria-label="Next page"><ChevronRight className="size-4" /></Button>
        </div>
      </CardContent>
    </Card>
  );
}
