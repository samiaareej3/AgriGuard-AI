"use client";

import { useState } from "react";
import { BarChart3 } from "lucide-react";
import { ChartFrame, DISEASE_SERIES, Lines, SimpleBars, StackedBars, shortDate } from "@/components/charts";
import { EmptyState, ErrorState, LoadingGrid, PageHeader, StatCard } from "@/components/common";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { OP_STATUS_LABEL, OUTCOME_LABEL, dateTime, duration } from "@/lib/format";
import { useAnalytics } from "@/lib/queries";
import type { DecisionOutcome, OperationStatus } from "@/lib/types";
import { CheckCircle2, FlaskConical, ScanSearch, Timer } from "lucide-react";

export default function AnalyticsPage() {
  const [days, setDays] = useState("14");
  const a = useAnalytics(Number(days));

  return (
    <>
      <PageHeader
        title="Analytics"
        description="Trends computed from stored scans and operations. Nothing here is extrapolated or invented."
        actions={
          <Tabs value={days} onValueChange={setDays}>
            <TabsList>
              {["7", "14", "30", "90"].map((d) => <TabsTrigger key={d} value={d}>{d} days</TabsTrigger>)}
            </TabsList>
          </Tabs>
        }
      />
      {a.isError ? <ErrorState error={a.error} onRetry={() => a.refetch()} /> : !a.data ? <LoadingGrid /> : (
        <>
          <p className="mb-4 text-xs text-muted-foreground">
            Range: {dateTime(a.data.range.start)} to {dateTime(a.data.range.end)} (UTC day buckets)
            {a.data.totals.truncated && " · result truncated at 20,000 records"}
          </p>
          <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Scans" value={a.data.totals.scans} icon={ScanSearch} />
            <StatCard label="Simulated scans" value={a.data.totals.simulated_scans} icon={FlaskConical} hint="Demo data share" />
            <StatCard label="Spray operations" value={a.data.totals.operations} icon={Timer} />
            <StatCard label="Completed spray time" value={duration(a.data.totals.completed_spray_seconds)} icon={CheckCircle2} tone="good" />
          </div>
          {a.data.totals.scans === 0 && a.data.totals.operations === 0 ? (
            <EmptyState icon={BarChart3} title="No records in this range" description="Run scans (uploads or simulated captures) and charts will populate from the stored data." />
          ) : (
            <div className="grid gap-6 xl:grid-cols-2">
              <div className="xl:col-span-2">
                <ChartFrame title="Scans per day by result" series={DISEASE_SERIES}
                  table={{ columns: ["Date", "Healthy", "Early Blight", "Late Blight", "Review"], rows: a.data.scans_per_day.map((d) => [d.date, d.healthy, d.early_blight, d.late_blight, d.uncertain]) }}>
                  <StackedBars data={a.data.scans_per_day} xKey="date" series={DISEASE_SERIES} xFormatter={shortDate} />
                </ChartFrame>
              </div>
              <ChartFrame title="Safety decision outcomes" description="Scan-time decisions"
                table={{ columns: ["Outcome", "Scans"], rows: Object.entries(a.data.decision_outcomes).map(([k, v]) => [OUTCOME_LABEL[k as DecisionOutcome] ?? k, v]) }}>
                <SimpleBars data={Object.entries(a.data.decision_outcomes).map(([k, v]) => ({ name: OUTCOME_LABEL[k as DecisionOutcome] ?? k, value: v }))} xKey="name" yKey="value" label="Scans" />
              </ChartFrame>
              <ChartFrame title="Spray operation status" description="Operations created in range"
                table={{ columns: ["Status", "Operations"], rows: Object.entries(a.data.operation_status).map(([k, v]) => [OP_STATUS_LABEL[k as OperationStatus] ?? k, v]) }}>
                {Object.keys(a.data.operation_status).length ? (
                  <SimpleBars data={Object.entries(a.data.operation_status).map(([k, v]) => ({ name: OP_STATUS_LABEL[k as OperationStatus] ?? k, value: v }))} xKey="name" yKey="value" label="Operations" />
                ) : <EmptyState title="No operations in range" />}
              </ChartFrame>
              <ChartFrame title="Model confidence distribution" description="Top-class confidence of all scans"
                table={{ columns: ["Confidence", "Scans"], rows: a.data.confidence_histogram.map((b) => [b.bucket, b.count]) }}>
                <SimpleBars data={a.data.confidence_histogram} xKey="bucket" yKey="count" label="Scans" />
              </ChartFrame>
              <ChartFrame title="Average confidence per day" description="Days without scans are gaps, not zeros"
                table={{ columns: ["Date", "Avg confidence"], rows: a.data.scans_per_day.map((d) => [d.date, d.avg_confidence === null ? "—" : `${(d.avg_confidence * 100).toFixed(1)}%`]) }}>
                <Lines data={a.data.scans_per_day.map((d) => ({ date: d.date, avg: d.avg_confidence }))} xKey="date" xFormatter={shortDate}
                  series={[{ key: "avg", label: "Avg confidence", color: "var(--series-late)" }]} yFormatter={(v) => `${Math.round(v * 100)}%`} domain={[0, 1]} connectNulls={false} />
              </ChartFrame>
            </div>
          )}
        </>
      )}
    </>
  );
}
