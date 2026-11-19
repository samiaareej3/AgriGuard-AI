"use client";

import { use } from "react";
import Link from "next/link";
import { ArrowLeft, Info } from "lucide-react";
import { ConfidenceBar, ErrorState, LabelPill, OpStatusPill, PageHeader, SimBadge } from "@/components/common";
import { DecisionPanel } from "@/components/decision-panel";
import { ScanImage } from "@/components/scan-image";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { LABELS, dateTime, num, pct } from "@/lib/format";
import { useScan } from "@/lib/queries";
import { useQuery } from "@tanstack/react-query";
import type { SprayOperation } from "@/lib/types";

export default function ScanDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const scan = useScan(id);
  const opId = scan.data?.spray_operation_id;
  const op = useQuery({ queryKey: ["operations", "one", opId], queryFn: () => api<SprayOperation>(`/spray/operations/${opId}`), enabled: !!opId });

  if (scan.isError) return <ErrorState error={scan.error} onRetry={() => scan.refetch()} />;
  if (!scan.data) return <Skeleton className="h-96 rounded-xl" />;
  const s = scan.data;
  const rows: [string, React.ReactNode][] = [
    ["Scan ID", <span key="id" className="font-mono text-xs">{s.id}</span>],
    ["Captured", dateTime(s.created_at)],
    ["Source", <span key="src" className="flex items-center gap-1.5 capitalize">{s.source} {s.simulated && <SimBadge />}</span>],
    ["Device", s.device_id ?? "None"],
    ["Submitted by", s.submitted_by ?? "—"],
    ["File", s.original_filename ?? "—"],
    ["Image", `${s.quality.width}×${s.quality.height}px · ${(s.size_bytes / 1024).toFixed(0)} KB`],
    ["Brightness / sharpness", `${num(s.quality.brightness)} / ${num(s.quality.sharpness)}`],
    ["Leaf-coloured area", pct(s.quality.green_ratio)],
  ];

  return (
    <>
      <Button variant="ghost" size="sm" asChild className="mb-2 -ml-2"><Link href="/scans"><ArrowLeft className="size-4" /> Scan history</Link></Button>
      <PageHeader title={`Scan · ${s.prediction.display_label}`} description={s.notes ?? undefined} />
      <div className="grid gap-6 lg:grid-cols-5">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          <Card className="overflow-hidden py-0">
            <ScanImage scanId={s.id} alt={`Leaf scan classified as ${s.prediction.display_label}`} className="aspect-square w-full" />
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-sm">Details</CardTitle></CardHeader>
            <CardContent>
              <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
                {rows.map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-muted-foreground">{k}</dt>
                    <dd className="min-w-0 break-words">{v}</dd>
                  </div>
                ))}
              </dl>
            </CardContent>
          </Card>
        </div>
        <div className="min-w-0 space-y-6 lg:col-span-3">
          <Card>
            <CardHeader><CardTitle className="text-sm">Prediction</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <LabelPill label={s.prediction.label} status={s.prediction.status} />
                <ConfidenceBar value={s.prediction.confidence} threshold={s.prediction.threshold} />
                <span className="text-xs text-muted-foreground">{s.prediction.model_version} · {s.prediction.inference_ms} ms</span>
              </div>
              <table className="w-full text-sm">
                <caption className="sr-only">Class probabilities</caption>
                <tbody>
                  {Object.entries(s.prediction.probabilities).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                    <tr key={k} className="border-t"><td className="py-1.5">{LABELS[k] ?? k}</td><td className="tabular py-1.5 text-right">{pct(v, 2)}</td></tr>
                  ))}
                </tbody>
              </table>
              {s.prediction.warnings.length > 0 && (
                <ul className="space-y-1 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
                  {s.prediction.warnings.map((w) => <li key={w} className="flex gap-2"><Info className="mt-0.5 size-4 shrink-0" />{w}</li>)}
                </ul>
              )}
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle className="text-sm">Safety decision at scan time</CardTitle></CardHeader>
            <CardContent><DecisionPanel decision={s.decision} /></CardContent>
          </Card>
          {op.data && (
            <Card>
              <CardHeader className="flex flex-row items-center justify-between">
                <CardTitle className="text-sm">Spray operation</CardTitle>
                <OpStatusPill status={op.data.status} />
              </CardHeader>
              <CardContent>
                <ol className="space-y-2 border-l pl-4 text-sm">
                  {op.data.history.map((h, i) => (
                    <li key={i}>
                      <p className="font-medium">{h.status.replace("_", " ").toLowerCase()} <span className="font-normal text-muted-foreground">· {h.actor}</span></p>
                      <p className="text-xs text-muted-foreground">{dateTime(h.ts)} · {h.message}</p>
                    </li>
                  ))}
                </ol>
                <Button size="sm" variant="outline" className="mt-3" asChild><Link href="/operations">Manage in Spray Operations</Link></Button>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
