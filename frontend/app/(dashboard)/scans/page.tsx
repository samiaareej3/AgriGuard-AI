"use client";

import { useState } from "react";
import Link from "next/link";
import { ChevronLeft, ChevronRight, History, Search, X } from "lucide-react";
import {
  ConfidenceBar, EmptyState, ErrorState, LabelPill, OutcomePill, PageHeader, SimBadge, TimeAgo,
} from "@/components/common";
import { ScanImage } from "@/components/scan-image";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { shortId } from "@/lib/format";
import { useDevices, useScans, type ScanFilters } from "@/lib/queries";

const ALL = "all";

export default function ScansPage() {
  const [q, setQ] = useState("");
  const [filters, setFilters] = useState<ScanFilters>({ page: 1, page_size: 20 });
  const devices = useDevices();
  const scans = useScans(filters);
  const set = (patch: Partial<ScanFilters>) => setFilters((f) => ({ ...f, page: 1, ...patch }));
  const active = Boolean(filters.q || filters.label || filters.outcome || filters.device_id || filters.source || filters.date_from || filters.date_to);
  const totalPages = scans.data ? Math.max(1, Math.ceil(scans.data.total / scans.data.page_size)) : 1;

  return (
    <>
      <PageHeader title="Scan history" description="Every scan with its prediction, safety decision and source. Simulated captures are labelled." />
      <form
        className="mb-4 grid gap-3 rounded-xl border bg-card p-4 sm:grid-cols-2 lg:grid-cols-6"
        onSubmit={(e) => { e.preventDefault(); set({ q: q.trim() || undefined }); }}
        aria-label="Scan filters"
      >
        <div className="space-y-1 lg:col-span-2">
          <Label htmlFor="q" className="text-xs">Search</Label>
          <div className="relative">
            <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" aria-hidden />
            <Input id="q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="ID, filename, label, notes" className="pl-8" />
          </div>
        </div>
        <FilterSelect label="Result" value={filters.label} onChange={(v) => set({ label: v })}
          options={[["healthy", "Healthy"], ["early_blight", "Early Blight"], ["late_blight", "Late Blight"], ["uncertain", "Review required"]]} />
        <FilterSelect label="Decision" value={filters.outcome} onChange={(v) => set({ outcome: v })}
          options={[["PENDING_APPROVAL", "Awaiting approval"], ["AUTHORIZED", "Authorized"], ["BLOCKED", "Blocked"], ["REVIEW_REQUIRED", "Review required"], ["SKIP", "No spray needed"]]} />
        <FilterSelect label="Source" value={filters.source} onChange={(v) => set({ source: v })}
          options={[["dashboard", "Dashboard upload"], ["simulator", "Simulator"], ["device", "Hardware device"]]} />
        <FilterSelect label="Device" value={filters.device_id} onChange={(v) => set({ device_id: v })}
          options={(devices.data ?? []).map((d) => [d.id, d.name])} />
        <div className="space-y-1">
          <Label htmlFor="from" className="text-xs">From</Label>
          <Input id="from" type="date" value={filters.date_from?.slice(0, 10) ?? ""}
            onChange={(e) => set({ date_from: e.target.value ? new Date(e.target.value + "T00:00:00").toISOString() : undefined })} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="to" className="text-xs">To</Label>
          <Input id="to" type="date" value={filters.date_to?.slice(0, 10) ?? ""}
            onChange={(e) => set({ date_to: e.target.value ? new Date(e.target.value + "T23:59:59").toISOString() : undefined })} />
        </div>
        <div className="flex items-end gap-2 lg:col-span-4">
          <Button type="submit" size="sm"><Search className="size-4" /> Search</Button>
          {active && (
            <Button type="button" size="sm" variant="ghost" onClick={() => { setQ(""); setFilters({ page: 1, page_size: 20 }); }}>
              <X className="size-4" /> Clear filters
            </Button>
          )}
          <span className="ml-auto text-xs text-muted-foreground" aria-live="polite">{scans.data ? `${scans.data.total} scan(s)` : ""}</span>
        </div>
      </form>

      {scans.isError ? (
        <ErrorState error={scans.error} onRetry={() => scans.refetch()} />
      ) : scans.isLoading ? (
        <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-16 rounded-xl" />)}</div>
      ) : !scans.data?.items.length ? (
        <EmptyState icon={History} title={active ? "No scans match these filters" : "No scans yet"}
          description={active ? "Try widening the date range or clearing filters." : "Scans from uploads, the simulator and devices appear here."} />
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-muted/60 text-left text-xs text-muted-foreground">
                <tr>
                  <th className="px-4 py-2.5 font-medium">Scan</th>
                  <th className="px-4 py-2.5 font-medium">Result</th>
                  <th className="hidden px-4 py-2.5 font-medium md:table-cell">Confidence</th>
                  <th className="px-4 py-2.5 font-medium">Decision</th>
                  <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Source</th>
                  <th className="hidden px-4 py-2.5 font-medium sm:table-cell">When</th>
                </tr>
              </thead>
              <tbody>
                {scans.data.items.map((s) => (
                  <tr key={s.id} className="border-t hover:bg-muted/40">
                    <td className="px-4 py-2.5">
                      <Link href={`/scans/${s.id}`} className="flex items-center gap-3 font-medium hover:underline">
                        <ScanImage scanId={s.id} alt="" className="size-10 rounded-md" />
                        <span className="font-mono text-xs">{shortId(s.id)}</span>
                      </Link>
                    </td>
                    <td className="px-4 py-2.5"><LabelPill label={s.prediction.label} status={s.prediction.status} /></td>
                    <td className="hidden px-4 py-2.5 md:table-cell"><ConfidenceBar value={s.prediction.confidence} threshold={s.prediction.threshold} /></td>
                    <td className="px-4 py-2.5"><OutcomePill outcome={s.decision.outcome} /></td>
                    <td className="hidden px-4 py-2.5 lg:table-cell">
                      <span className="flex items-center gap-1.5 capitalize">{s.source}{s.simulated && <SimBadge />}</span>
                    </td>
                    <td className="hidden px-4 py-2.5 text-muted-foreground sm:table-cell"><TimeAgo iso={s.created_at} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t px-4 py-2.5 text-xs text-muted-foreground">
            <span>Page {filters.page} of {totalPages}</span>
            <div className="flex gap-1">
              <Button variant="outline" size="sm" disabled={(filters.page ?? 1) <= 1} onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) - 1 }))} aria-label="Previous page">
                <ChevronLeft className="size-4" />
              </Button>
              <Button variant="outline" size="sm" disabled={(filters.page ?? 1) >= totalPages} onClick={() => setFilters((f) => ({ ...f, page: (f.page ?? 1) + 1 }))} aria-label="Next page">
                <ChevronRight className="size-4" />
              </Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function FilterSelect({ label, value, onChange, options }: {
  label: string; value?: string; onChange: (v: string | undefined) => void; options: (readonly [string, string] | string[])[];
}) {
  const id = `f-${label.toLowerCase()}`;
  return (
    <div className="space-y-1">
      <Label htmlFor={id} className="text-xs">{label}</Label>
      <Select value={value ?? ALL} onValueChange={(v) => onChange(v === ALL ? undefined : v)}>
        <SelectTrigger id={id} className="w-full"><SelectValue /></SelectTrigger>
        <SelectContent>
          <SelectItem value={ALL}>All</SelectItem>
          {options.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
        </SelectContent>
      </Select>
    </div>
  );
}
