"use client";

import Link from "next/link";
import {
  AlertTriangle, ArrowRight, Cpu, Hourglass, ScanSearch, ShieldAlert, SprayCan, Activity,
} from "lucide-react";
import {
  ConnectivityPill, EmptyState, ErrorState, LabelPill, LoadingGrid, OpStatusPill, OutcomePill, PageHeader, SimBadge,
  StatCard, TimeAgo,
} from "@/components/common";
import { ChartFrame, DISEASE_SERIES, StackedBars, shortDate } from "@/components/charts";
import { ScanImage } from "@/components/scan-image";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { pct } from "@/lib/format";
import { useAnalytics, useDevices, useOperations, useScans, useSummary } from "@/lib/queries";
import { EventList } from "@/components/event-list";

export default function OverviewPage() {
  const summary = useSummary();
  const devices = useDevices();
  const scans = useScans({ page_size: 5 });
  const pending = useOperations("PENDING_APPROVAL");
  const analytics = useAnalytics(14);

  if (summary.isError) return <ErrorState error={summary.error} onRetry={() => summary.refetch()} />;
  const s = summary.data;

  return (
    <>
      <PageHeader
        title="Operations overview"
        description="Crop health, device fleet and spray safety at a glance. Counts come from stored records."
        actions={
          <Button asChild>
            <Link href="/detect"><ScanSearch className="size-4" /> New scan</Link>
          </Button>
        }
      />
      {!s ? (
        <LoadingGrid />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Scans (24 h)" value={s.scans.last_24h} hint={`${s.scans.total} total · ${s.scans.simulated_total} simulated`} icon={ScanSearch} />
          <StatCard label="Disease detected (24 h)" value={s.scans.diseased_last_24h} hint={`${s.scans.review_required_last_24h} sent to manual review`}
            icon={AlertTriangle} tone={s.scans.diseased_last_24h ? "warning" : "default"} />
          <StatCard label="Devices online" value={`${s.devices.online}/${s.devices.total}`} hint={`${s.devices.simulated} simulated · ${s.devices.real} hardware`}
            icon={Cpu} tone={s.devices.total && s.devices.online === s.devices.total ? "good" : s.devices.offline ? "critical" : "default"} />
          <StatCard label="Awaiting approval" value={s.operations.pending_approval} hint={`${s.operations.active} active · ${s.operations.completed} completed`}
            icon={Hourglass} tone={s.operations.pending_approval ? "warning" : "default"} />
        </div>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-3">
        <div className="min-w-0 space-y-6 xl:col-span-2">
          {analytics.data && (
            <ChartFrame
              title="Scans per day by result"
              description={`Last 14 days · ${analytics.data.totals.scans} scans (${analytics.data.totals.simulated_scans} simulated)`}
              series={DISEASE_SERIES}
              table={{
                columns: ["Date", "Healthy", "Early Blight", "Late Blight", "Review"],
                rows: analytics.data.scans_per_day.map((d) => [d.date, d.healthy, d.early_blight, d.late_blight, d.uncertain]),
              }}
            >
              {analytics.data.totals.scans === 0 ? (
                <EmptyState title="No scans in this period" description="Upload a leaf image or trigger a simulated capture." />
              ) : (
                <StackedBars data={analytics.data.scans_per_day} xKey="date" series={DISEASE_SERIES} xFormatter={shortDate} />
              )}
            </ChartFrame>
          )}

          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-sm">Recent scans</CardTitle>
              <Button variant="ghost" size="sm" asChild><Link href="/scans">View all <ArrowRight className="size-4" /></Link></Button>
            </CardHeader>
            <CardContent>
              {scans.isLoading ? <LoadingGrid count={2} className="xl:grid-cols-2" /> : scans.data?.items.length ? (
                <ul className="divide-y">
                  {scans.data.items.map((scan) => (
                    <li key={scan.id}>
                      <Link href={`/scans/${scan.id}`} className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-muted/60">
                        <ScanImage scanId={scan.id} alt="Leaf thumbnail" className="size-11 shrink-0 rounded-lg" />
                        <div className="min-w-0 flex-1">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <LabelPill label={scan.prediction.label} status={scan.prediction.status} />
                            <span className="tabular text-xs text-muted-foreground">{pct(scan.prediction.confidence)}</span>
                            {scan.simulated && <SimBadge />}
                          </div>
                          <p className="mt-0.5 truncate text-xs text-muted-foreground">
                            <TimeAgo iso={scan.created_at} /> · {scan.source}
                          </p>
                        </div>
                        <OutcomePill outcome={scan.decision.outcome} />
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState icon={ScanSearch} title="No scans yet" action={<Button asChild size="sm"><Link href="/detect">Run first scan</Link></Button>} />
              )}
            </CardContent>
          </Card>
        </div>

        <div className="min-w-0 space-y-6">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="flex items-center gap-2 text-sm"><SprayCan className="size-4" /> Approval queue</CardTitle>
              <Button variant="ghost" size="sm" asChild><Link href="/operations">Open <ArrowRight className="size-4" /></Link></Button>
            </CardHeader>
            <CardContent>
              {pending.data?.items.length ? (
                <ul className="space-y-2">
                  {pending.data.items.slice(0, 4).map((op) => (
                    <li key={op.id} className="flex items-center justify-between gap-2 rounded-lg border p-2.5 text-sm">
                      <div className="min-w-0">
                        <p className="truncate font-medium">{op.label === "late_blight" ? "Late Blight" : "Early Blight"} · {pct(op.confidence)}</p>
                        <p className="text-xs text-muted-foreground"><TimeAgo iso={op.created_at} /></p>
                      </div>
                      <OpStatusPill status={op.status} />
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-sm text-muted-foreground">Nothing awaiting approval.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2 text-sm"><Cpu className="size-4" /> Device fleet</CardTitle></CardHeader>
            <CardContent>
              {devices.data?.length ? (
                <ul className="space-y-2">
                  {devices.data.map((d) => (
                    <li key={d.id} className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-sm">
                      <div className="min-w-0">
                        <p className="font-medium">{d.name}</p>
                        <p className="text-xs text-muted-foreground">Seen <TimeAgo iso={d.last_seen} /></p>
                      </div>
                      <div className="flex shrink-0 items-center gap-1.5">
                        {d.simulated && <SimBadge />}
                        <ConnectivityPill state={d.connectivity} />
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState icon={Cpu} title="No devices" action={<Button asChild size="sm" variant="outline"><Link href="/devices">Add device</Link></Button>} />
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="flex items-center gap-2 text-sm"><Activity className="size-4" /> Recent activity</CardTitle></CardHeader>
            <CardContent>
              <EventList events={s?.recent_events ?? []} />
            </CardContent>
          </Card>

          {s?.model.state !== "ready" && s && (
            <div className="flex items-start gap-2 rounded-xl border border-serious/40 bg-serious/10 p-3 text-sm">
              <ShieldAlert className="mt-0.5 size-4 shrink-0" />
              <p>Classifier state is <b>{s.model.state}</b>. Scans return &ldquo;Review required&rdquo; until the model is loaded.</p>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
