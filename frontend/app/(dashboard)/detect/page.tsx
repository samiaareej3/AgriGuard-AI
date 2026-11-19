"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Camera, FlaskConical, ImageUp, Info, Loader2, ScanSearch, Upload, X } from "lucide-react";
import { toast } from "sonner";
import { ConfidenceBar, LabelPill, PageHeader, SimBadge } from "@/components/common";
import { DecisionPanel } from "@/components/decision-panel";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api, errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { LABELS, dateTime, pct } from "@/lib/format";
import { useDevices, useSystemInfo } from "@/lib/queries";
import type { Scan } from "@/lib/types";

const ACCEPT = ["image/jpeg", "image/png", "image/webp"];
const NO_DEVICE = "__none__";

export default function DetectPage() {
  const { can } = useAuth();
  const devices = useDevices();
  const info = useSystemInfo();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [deviceId, setDeviceId] = useState<string>(NO_DEVICE);
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Scan | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const maxMb = info.data?.uploads.max_mb ?? 5;
  const allowed = can("operator");

  useEffect(() => {
    if (deviceId === NO_DEVICE && devices.data?.length) {
      const online = devices.data.find((d) => d.connectivity === "online");
      if (online) setDeviceId(online.id);
    }
  }, [devices.data, deviceId]);

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);

  const pick = useCallback((f: File | undefined) => {
    if (!f) return;
    if (!ACCEPT.includes(f.type)) return toast.error("Unsupported file type. Use JPEG, PNG or WebP.");
    if (f.size > maxMb * 1024 * 1024) return toast.error(`File is larger than ${maxMb} MB.`);
    setFile(f);
    setResult(null);
    setPreview(URL.createObjectURL(f));
  }, [maxMb]);

  const submit = async () => {
    if (!file) return;
    setBusy(true);
    const form = new FormData();
    form.append("image", file);
    if (deviceId !== NO_DEVICE) form.append("device_id", deviceId);
    if (notes.trim()) form.append("notes", notes.trim());
    try {
      const scan = await api<Scan>("/scans", { form });
      setResult(scan);
      toast.success("Scan analysed");
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  const reset = () => {
    setFile(null);
    setPreview(null);
    setResult(null);
    setNotes("");
  };

  const simDevice = devices.data?.find((d) => d.simulated && d.connectivity === "online");
  const simCapture = async () => {
    if (!simDevice) return;
    setBusy(true);
    try {
      const scan = await api<Scan>(`/simulator/devices/${simDevice.id}/scan`, { body: {} });
      setResult(scan);
      setFile(null);
      setPreview(null);
      toast.success(`Simulated capture from ${simDevice.name}`);
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title="Disease detection" description="Upload or capture a tomato-leaf photo. The model classifies it; the safety engine then decides separately whether spraying may proceed." />
      <div className="grid gap-6 xl:grid-cols-5">
        <Card className="xl:col-span-2">
          <CardHeader><CardTitle className="text-sm">1 · Image</CardTitle></CardHeader>
          <CardContent className="space-y-4">
            <div
              role="button"
              tabIndex={0}
              aria-label="Choose or drop an image"
              onClick={() => inputRef.current?.click()}
              onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); pick(e.dataTransfer.files[0]); }}
              className={`relative grid aspect-[4/3] cursor-pointer place-items-center overflow-hidden rounded-xl border-2 border-dashed transition-colors focus-visible:outline-2 focus-visible:outline-primary ${dragOver ? "border-primary bg-primary/5" : "hover:bg-muted/50"}`}
            >
              {preview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={preview} alt="Selected leaf" className="absolute inset-0 size-full object-contain" />
              ) : (
                <div className="px-6 text-center">
                  <ImageUp className="mx-auto size-8 text-muted-foreground" aria-hidden />
                  <p className="mt-2 text-sm font-medium">Drop a leaf photo or click to browse</p>
                  <p className="mt-1 text-xs text-muted-foreground">JPEG, PNG or WebP · up to {maxMb} MB · single leaf, good light</p>
                </div>
              )}
            </div>
            <input ref={inputRef} type="file" accept={ACCEPT.join(",")} className="sr-only" onChange={(e) => pick(e.target.files?.[0])} aria-label="Image file" />
            <input ref={cameraRef} type="file" accept="image/*" capture="environment" className="sr-only" onChange={(e) => pick(e.target.files?.[0])} aria-label="Camera capture" />
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => cameraRef.current?.click()}><Camera className="size-4" /> Use camera</Button>
              {file && <Button variant="ghost" size="sm" onClick={reset}><X className="size-4" /> Clear</Button>}
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="device">Target spray device</Label>
              <Select value={deviceId} onValueChange={setDeviceId}>
                <SelectTrigger id="device" className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value={NO_DEVICE}>No device (classification only)</SelectItem>
                  {devices.data?.map((d) => (
                    <SelectItem key={d.id} value={d.id}>{d.name} · {d.connectivity}{d.simulated ? " · simulated" : ""}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">Without a device the safety engine will block spraying. That is expected.</p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="notes">Notes (optional)</Label>
              <Textarea id="notes" maxLength={500} rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Row, plant, observations…" />
            </div>
            <div className="flex flex-wrap gap-2">
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Button onClick={submit} disabled={!file || busy || !allowed}>
                      {busy ? <Loader2 className="size-4 animate-spin" /> : <Upload className="size-4" />} Analyse image
                    </Button>
                  </span>
                </TooltipTrigger>
                {!allowed && <TooltipContent>Requires operator role</TooltipContent>}
                {allowed && !file && <TooltipContent>Choose an image first</TooltipContent>}
              </Tooltip>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Button variant="outline" onClick={simCapture} disabled={!simDevice || busy || !allowed}>
                      <FlaskConical className="size-4" /> Simulated capture
                    </Button>
                  </span>
                </TooltipTrigger>
                <TooltipContent>{simDevice ? `Sample image from ${simDevice.name} (SIMULATED)` : "No online simulated device"}</TooltipContent>
              </Tooltip>
            </div>
          </CardContent>
        </Card>

        <div className="min-w-0 space-y-6 xl:col-span-3">
          <Card>
            <CardHeader><CardTitle className="text-sm">2 · AI prediction</CardTitle></CardHeader>
            <CardContent>
              {busy && !result ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="size-4 animate-spin" /> Analysing…</div>
              ) : result ? (
                <div className="space-y-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <LabelPill label={result.prediction.label} status={result.prediction.status} />
                    {result.simulated && <SimBadge />}
                    <span className="text-xs text-muted-foreground">
                      {result.prediction.model_version ?? "no model"} · {result.prediction.inference_ms ?? "—"} ms · {dateTime(result.prediction.timestamp)}
                    </span>
                  </div>
                  <div className="space-y-2">
                    {Object.entries(result.prediction.probabilities).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
                      <div key={k} className="grid grid-cols-[110px_1fr_48px] items-center gap-3 text-sm">
                        <span>{LABELS[k] ?? k}</span>
                        <div className="h-2 overflow-hidden rounded-full bg-muted">
                          <div className="h-full rounded-full" style={{ width: `${v * 100}%`, background: k === "healthy" ? "var(--series-healthy)" : k === "early_blight" ? "var(--series-early)" : "var(--series-late)" }} />
                        </div>
                        <span className="tabular text-right text-xs">{pct(v, 1)}</span>
                      </div>
                    ))}
                  </div>
                  <div className="flex items-center gap-3 text-xs text-muted-foreground">
                    Confidence <ConfidenceBar value={result.prediction.confidence} threshold={result.prediction.threshold} /> threshold {pct(result.prediction.threshold)}
                  </div>
                  {result.prediction.warnings.length > 0 && (
                    <ul className="space-y-1 rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm">
                      {result.prediction.warnings.map((w) => <li key={w} className="flex gap-2"><Info className="mt-0.5 size-4 shrink-0" />{w}</li>)}
                    </ul>
                  )}
                  <Button variant="outline" size="sm" asChild><Link href={`/scans/${result.id}`}>Open scan record</Link></Button>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">Results appear here after analysis.</p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader><CardTitle className="text-sm">3 · Spray decision (safety engine)</CardTitle></CardHeader>
            <CardContent>
              {result ? (
                <div className="space-y-3">
                  <DecisionPanel decision={result.decision} />
                  {result.spray_operation_id && (
                    <Button size="sm" asChild><Link href="/operations"><ScanSearch className="size-4" /> Go to spray operations</Link></Button>
                  )}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">The decision is computed independently of the classifier using 13 explicit rules.</p>
              )}
            </CardContent>
          </Card>

          <p className="flex items-start gap-2 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            {info.data?.model.disclaimer ?? "AI-assisted decision support only."}
          </p>
        </div>
      </div>
    </>
  );
}
