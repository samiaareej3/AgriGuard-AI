"use client";

import { useState } from "react";
import { CloudOff, CloudRain, Droplets, ExternalLink, RefreshCw, Sprout, Thermometer, Wind } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { ChartFrame, Lines, SimpleBars, shortDate } from "@/components/charts";
import { EmptyState, ErrorState, Freshness, LoadingGrid, PageHeader, Pill, StatCard } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { num } from "@/lib/format";
import { useClimate, usePolicy, useSources, useWeather } from "@/lib/queries";
import type { Climate, ExternalData, Forecast } from "@/lib/types";
import { AlertTriangle, CheckCircle2 } from "lucide-react";

export default function InsightsPage() {
  const weather = useWeather();
  const climate = useClimate();
  const sources = useSources();
  const policy = usePolicy();
  const qc = useQueryClient();
  const [refreshing, setRefreshing] = useState(false);

  const refresh = async () => {
    setRefreshing(true);
    try {
      const [w, c] = await Promise.all([
        api<ExternalData<Forecast>>("/insights/weather", { query: { refresh: true } }),
        api<ExternalData<Climate>>("/insights/climate", { query: { refresh: true } }),
      ]);
      qc.setQueryData(["weather"], w);
      qc.setQueryData(["climate"], c);
    } finally {
      setRefreshing(false);
    }
  };

  const w = weather.data;
  const f = w?.data;
  const cur = f?.current ?? {};
  const wind = typeof cur.wind_speed_10m === "number" ? cur.wind_speed_10m : null;
  const rainP = f?.next_3h_max_precipitation_probability ?? null;
  const wp = policy.data?.weather;
  const windOk = wind !== null && wp ? wind <= wp.max_wind_kmh : null;
  const rainOk = rainP !== null && wp ? rainP <= wp.max_precip_probability_pct : null;

  const daily = f ? (f.daily.time ?? []).map((t, i) => ({
    date: String(t),
    tmax: f.daily.temperature_2m_max?.[i] as number | null,
    tmin: f.daily.temperature_2m_min?.[i] as number | null,
    rain: (f.daily.precipitation_probability_max?.[i] as number | null) ?? 0,
  })) : [];
  const series = climate.data?.data?.series ?? [];

  return (
    <>
      <PageHeader
        title="Agricultural insights"
        description={`Weather and climate context for ${f?.location.name ?? "the configured location"} from free public APIs. Every value shows its source and retrieval time.`}
        actions={<Button variant="outline" onClick={refresh} disabled={refreshing}><RefreshCw className={`size-4 ${refreshing ? "animate-spin" : ""}`} /> Refresh sources</Button>}
      />

      {weather.isError ? <ErrorState error={weather.error} onRetry={() => weather.refetch()} /> : !w ? <LoadingGrid /> : !w.available ? (
        <EmptyState icon={CloudOff} title="Weather data unavailable" description={`${w.source}: ${w.error ?? "no data"}. No values are shown rather than guessed.`} />
      ) : (
        <>
          <div className="mb-3"><Freshness freshness={w.freshness} fetchedAt={w.fetched_at} source={w.source} /></div>
          {w.error && <p className="mb-3 text-xs text-amber-700 dark:text-amber-300">{w.error}. Showing the last successful retrieval.</p>}
          <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Temperature" value={num(cur.temperature_2m as number, 1, " °C")} hint={`Observed ${String(cur.time ?? "").replace("T", " ")} (${f?.location.timezone})`} icon={Thermometer} />
            <StatCard label="Relative humidity" value={num(cur.relative_humidity_2m as number, 0, " %")} icon={Droplets} />
            <StatCard label="Wind (10 m)" value={num(wind, 1, " km/h")} hint={`Gusts ${num(cur.wind_gusts_10m as number, 0, " km/h")}`} icon={Wind} tone={windOk === false ? "warning" : "default"} />
            <StatCard label="Rain chance (next 3 h)" value={num(rainP, 0, " %")} icon={CloudRain} tone={rainOk === false ? "warning" : "default"} />
          </div>

          <div className="mb-6 grid gap-6 xl:grid-cols-3">
            <Card>
              <CardHeader><CardTitle className="text-sm">Spray conditions vs policy</CardTitle></CardHeader>
              <CardContent className="space-y-3 text-sm">
                {wp ? (
                  <>
                    <Condition ok={windOk} label={`Wind ${num(wind, 0)} km/h (limit ${wp.max_wind_kmh})`} />
                    <Condition ok={rainOk} label={`Rain probability ${num(rainP, 0)}% (limit ${wp.max_precip_probability_pct}%)`} />
                    <p className="text-xs text-muted-foreground">
                      Weather rule is {wp.enabled ? (wp.blocking ? "BLOCKING" : "advisory (warning only)") : "disabled"} in policy v{policy.data?.version}.
                      The safety engine uses the cached forecast and never waits on the network.
                    </p>
                  </>
                ) : <p className="text-muted-foreground">Loading policy…</p>}
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="flex items-center gap-2 text-sm"><Sprout className="size-4" /> Blight-favourable hours</CardTitle></CardHeader>
              <CardContent>
                <p className="tabular text-3xl font-semibold">{f?.blight_favourable_hours_7d ?? "—"} <span className="text-sm font-normal text-muted-foreground">h in 7-day forecast</span></p>
                <p className="mt-2 text-xs text-muted-foreground">{f?.blight_heuristic_note}</p>
              </CardContent>
            </Card>
            <Card>
              <CardHeader><CardTitle className="text-sm">Location</CardTitle></CardHeader>
              <CardContent className="space-y-1 text-sm">
                <p className="font-medium">{f?.location.name}</p>
                <p className="text-muted-foreground">{num(f?.location.lat, 3)}°, {num(f?.location.lon, 3)}° · {num(f?.location.elevation_m, 0)} m</p>
                <p className="text-xs text-muted-foreground">Configured via LOCATION_* environment variables.</p>
              </CardContent>
            </Card>
          </div>

          <div className="mb-6 grid gap-6 xl:grid-cols-2">
            <ChartFrame title="7-day temperature forecast (°C)" description="Open-Meteo daily max / min"
              series={[{ key: "tmax", label: "Max", color: "var(--series-early)" }, { key: "tmin", label: "Min", color: "var(--series-late)" }]}
              table={{ columns: ["Date", "Max °C", "Min °C", "Rain %"], rows: daily.map((d) => [d.date, d.tmax ?? "—", d.tmin ?? "—", d.rain]) }}>
              <Lines data={daily} xKey="date" xFormatter={shortDate}
                series={[{ key: "tmax", label: "Max", color: "var(--series-early)" }, { key: "tmin", label: "Min", color: "var(--series-late)" }]} />
            </ChartFrame>
            <ChartFrame title="Daily max rain probability (%)" description="Open-Meteo forecast"
              table={{ columns: ["Date", "Rain %"], rows: daily.map((d) => [d.date, d.rain]) }}>
              <SimpleBars data={daily.map((d) => ({ date: shortDate(d.date), rain: d.rain }))} xKey="date" yKey="rain" label="Rain probability %" />
            </ChartFrame>
          </div>
        </>
      )}

      <section className="mb-6" aria-label="NASA POWER recent climate">
        <h2 className="mb-2 text-sm font-semibold">Recent 30 days (NASA POWER, Agroclimatology)</h2>
        {climate.data && <div className="mb-3"><Freshness freshness={climate.data.freshness} fetchedAt={climate.data.fetched_at} source={climate.data.source} /></div>}
        {!climate.data ? <LoadingGrid count={2} className="xl:grid-cols-2" /> : !climate.data.available ? (
          <EmptyState icon={CloudOff} title="Climate data unavailable" description={climate.data.error ?? undefined} />
        ) : (
          <>
            <p className="mb-3 text-xs text-muted-foreground">
              Latest processed day: {climate.data.data?.latest_available_date ?? "—"}. NASA POWER daily data typically lags a few days; recent days may be missing rather than estimated.
            </p>
            <div className="grid gap-6 xl:grid-cols-2">
              <div className="min-w-0 xl:col-span-2">
              <ChartFrame title="Daily precipitation (mm/day)" table={{ columns: ["Date", "mm"], rows: series.map((r) => [r.date, r.PRECTOTCORR ?? "—"]) }}>
                <SimpleBars data={series.map((r) => ({ date: shortDate(r.date), mm: (r.PRECTOTCORR as number) ?? 0 }))} xKey="date" yKey="mm" label="Precipitation mm" allTicks={false} />
              </ChartFrame>
              </div>
              <ChartFrame title="Mean temperature (°C)" description="NASA POWER T2M"
                table={{ columns: ["Date", "T2M °C"], rows: series.map((r) => [r.date, r.T2M ?? "—"]) }}>
                <Lines data={series} xKey="date" xFormatter={shortDate} series={[{ key: "T2M", label: "Mean temp °C", color: "var(--series-early)" }]} />
              </ChartFrame>
              <ChartFrame title="Relative humidity (%)" description="NASA POWER RH2M"
                table={{ columns: ["Date", "RH2M %"], rows: series.map((r) => [r.date, r.RH2M ?? "—"]) }}>
                <Lines data={series} xKey="date" xFormatter={shortDate} domain={[0, 100]} series={[{ key: "RH2M", label: "Rel. humidity %", color: "var(--series-late)" }]} />
              </ChartFrame>
            </div>
          </>
        )}
      </section>

      <Card>
        <CardHeader><CardTitle className="text-sm">Data sources &amp; licensing</CardTitle></CardHeader>
        <CardContent className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr><th className="py-2 pr-4 font-medium">Source</th><th className="py-2 pr-4 font-medium">Status</th><th className="py-2 pr-4 font-medium">License</th><th className="py-2 font-medium">Notes</th></tr>
            </thead>
            <tbody>
              {sources.data?.map((s) => (
                <tr key={s.id} className="border-t align-top">
                  <td className="py-2 pr-4"><a href={s.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 font-medium hover:underline">{s.name}<ExternalLink className="size-3" /></a></td>
                  <td className="py-2 pr-4">
                    {s.status === "integrated" ? <Pill tone="good" icon={CheckCircle2}>Integrated</Pill> : s.status === "reference" ? <Pill tone="neutral" icon={Sprout}>Reference</Pill> : <Pill tone="neutral" icon={CloudOff}>Not integrated</Pill>}
                  </td>
                  <td className="py-2 pr-4 text-xs text-muted-foreground">{s.license}</td>
                  <td className="py-2 text-xs text-muted-foreground">{s.used_for}{s.note ? ` ${s.note}` : ""}{s.attribution ? ` Attribution: ${s.attribution}` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </>
  );
}

function Condition({ ok, label }: { ok: boolean | null; label: string }) {
  if (ok === null) return <Pill tone="neutral" icon={CloudOff}>{label}: unknown</Pill>;
  return ok ? <div><Pill tone="good" icon={CheckCircle2}>{label}</Pill></div> : <div><Pill tone="warning" icon={AlertTriangle}>{label}</Pill></div>;
}
