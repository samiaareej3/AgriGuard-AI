"use client";

import { useState } from "react";
import Link from "next/link";
import { Check, ChevronDown, ChevronLeft, ChevronRight, OctagonAlert, SprayCan, Timer, X } from "lucide-react";
import { ErrorState, EmptyState, OpStatusPill, PageHeader, SimBadge, StatCard, TimeAgo } from "@/components/common";
import { DecisionPanel } from "@/components/decision-panel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LABELS, dateTime, duration, pct, shortId } from "@/lib/format";
import { useAction, useDevices, useEstop, useOperations, usePolicy, useSummary } from "@/lib/queries";
import type { SprayOperation } from "@/lib/types";

const TABS: [string, string | undefined][] = [
  ["Awaiting approval", "PENDING_APPROVAL"],
  ["Active", "DISPATCHED,RUNNING"],
  ["Completed", "COMPLETED"],
  ["Blocked", "BLOCKED"],
  ["Failed / aborted", "FAILED,ABORTED,EXPIRED,REJECTED"],
  ["All", undefined],
];

export default function OperationsPage() {
  const [tab, setTab] = useState("0");
  const [page, setPage] = useState(1);
  const status = TABS[Number(tab)][1];
  const ops = useOperations(status, page);
  const summary = useSummary();
  const policy = usePolicy();
  const estop = useEstop();
  const devices = useDevices();
  const now = Date.now();
  const cooling = (devices.data ?? []).filter((d) => d.last_spray_completed_at && policy.data &&
    now - new Date(d.last_spray_completed_at).getTime() < policy.data.cooldown_s * 1000);
  const totalPages = ops.data ? Math.max(1, Math.ceil(ops.data.total / ops.data.page_size)) : 1;

  return (
    <>
      <PageHeader title="Spray operations" description="Every operation passes the safety engine twice: at scan time and again at approval. Only simulated pumps are driven in this build." />
      {estop.data?.active && (
        <div role="alert" className="mb-4 flex items-center gap-2 rounded-xl border border-critical/40 bg-critical/10 p-3 text-sm text-red-800 dark:text-red-300">
          <OctagonAlert className="size-4" /> Emergency stop is active. Approvals will be blocked until it is reset.
        </div>
      )}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Awaiting approval" value={summary.data?.operations.pending_approval ?? "—"} icon={SprayCan} tone={summary.data?.operations.pending_approval ? "warning" : "default"} />
        <StatCard label="Active now" value={summary.data?.operations.active ?? "—"} icon={Timer} />
        <StatCard label="Completed" value={summary.data?.operations.completed ?? "—"} icon={Check} tone="good" />
        <StatCard label="Blocked / failed" value={summary.data ? summary.data.operations.blocked + summary.data.operations.failed : "—"} icon={X} tone="critical" />
      </div>
      {policy.data && (
        <p className="mb-4 text-xs text-muted-foreground">
          Policy v{policy.data.version}: {policy.data.spray_duration_s}s spray (max {policy.data.max_spray_duration_s}s) · cooldown {duration(policy.data.cooldown_s)} ·
          approval {policy.data.require_operator_approval ? "required" : "not required"} · approvals expire after {duration(policy.data.pending_approval_ttl_s)}
          {cooling.length > 0 && <> · cooling down: {cooling.map((d) => d.name).join(", ")}</>}
        </p>
      )}
      <Tabs value={tab} onValueChange={(v) => { setTab(v); setPage(1); }} className="mb-4">
        <TabsList className="h-auto flex-wrap">
          {TABS.map(([label], i) => <TabsTrigger key={label} value={String(i)}>{label}</TabsTrigger>)}
        </TabsList>
      </Tabs>
      {ops.isError ? <ErrorState error={ops.error} onRetry={() => ops.refetch()} /> : ops.isLoading ? (
        <div className="space-y-3">{Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-24 rounded-xl" />)}</div>
      ) : !ops.data?.items.length ? (
        <EmptyState icon={SprayCan} title="No operations in this view" description="Operations are created when a confident disease detection targets a device." />
      ) : (
        <div className="space-y-3">
          {ops.data.items.map((op) => <OperationCard key={op.id} op={op} deviceName={devices.data?.find((d) => d.id === op.device_id)?.name} />)}
          <div className="flex items-center justify-end gap-2 text-xs text-muted-foreground">
            Page {page} of {totalPages}
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} aria-label="Previous page"><ChevronLeft className="size-4" /></Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} aria-label="Next page"><ChevronRight className="size-4" /></Button>
          </div>
        </div>
      )}
    </>
  );
}

function OperationCard({ op, deviceName }: { op: SprayOperation; deviceName?: string }) {
  const { can } = useAuth();
  const [open, setOpen] = useState(op.status === "PENDING_APPROVAL");
  const [note, setNote] = useState("");
  const keys = [["operations"], ["summary"], ["devices"]];
  const approve = useAction(() => api<SprayOperation>(`/spray/operations/${op.id}/approve`, { body: { note: note || null } }), {
    success: (r) => (r.status === "DISPATCHED" ? "Approved: SPRAY command dispatched" : `Not dispatched: ${r.decision.reasons[0] ?? r.status}`),
    invalidate: keys,
  });
  const reject = useAction(() => api<SprayOperation>(`/spray/operations/${op.id}/reject`, { body: { note: note || null } }), { success: "Operation rejected", invalidate: keys });
  const pending = op.status === "PENDING_APPROVAL";

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="flex flex-row flex-wrap items-center gap-3 p-4">
        <OpStatusPill status={op.status} />
        <CardTitle className="text-sm">{LABELS[op.label ?? ""] ?? "Unknown"} · {pct(op.confidence)}</CardTitle>
        {op.simulated && <SimBadge />}
        <span className="text-xs text-muted-foreground">{deviceName ?? op.device_id ?? "no device"} · {op.duration_s}s · <TimeAgo iso={op.created_at} /></span>
        {pending && op.expires_at && <span className="text-xs text-amber-700 dark:text-amber-300">expires <TimeAgo iso={op.expires_at} /></span>}
        <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          Details <ChevronDown className={`size-4 transition-transform ${open ? "rotate-180" : ""}`} />
        </Button>
      </CardHeader>
      {open && (
        <CardContent className="space-y-4 border-t p-4">
          <DecisionPanel decision={op.decision} />
          {pending && (
            can("operator") ? (
              <div className="flex flex-col gap-2 rounded-lg bg-muted/50 p-3 sm:flex-row sm:items-center">
                <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Optional note for the audit log" aria-label="Approval note" className="bg-background" maxLength={500} />
                <div className="flex gap-2">
                  <Button onClick={() => approve.mutate(undefined)} disabled={approve.isPending || reject.isPending}><Check className="size-4" /> Approve &amp; re-check</Button>
                  <Button variant="outline" onClick={() => reject.mutate(undefined)} disabled={approve.isPending || reject.isPending}><X className="size-4" /> Reject</Button>
                </div>
              </div>
            ) : <p className="text-xs text-muted-foreground">Viewer accounts cannot approve operations.</p>
          )}
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">Audit trail</p>
            <ol className="space-y-1.5 border-l pl-4 text-sm">
              {op.history.map((h, i) => (
                <li key={i}><span className="font-medium">{h.status}</span> <span className="text-muted-foreground">· {h.actor} · {dateTime(h.ts)}</span><p className="text-xs text-muted-foreground">{h.message}</p></li>
              ))}
            </ol>
          </div>
          <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span>Operation <code>{shortId(op.id)}</code></span>
            {op.command_id && <span>Command <code>{shortId(op.command_id)}</code></span>}
            {op.scan_id && <Link className="underline" href={`/scans/${op.scan_id}`}>View scan</Link>}
          </div>
        </CardContent>
      )}
    </Card>
  );
}
