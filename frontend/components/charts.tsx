"use client";

import { useState } from "react";
import { Table2, BarChart3 } from "lucide-react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";

const AXIS = { stroke: "var(--chart-axis)", fontSize: 11, tickLine: false, axisLine: false } as const;
const GRID = { stroke: "var(--chart-grid)", strokeDasharray: "0", vertical: false } as const;

export interface Series {
  key: string;
  label: string;
  color: string;
}

function ChartTooltip({ active, payload, label, formatter }: {
  active?: boolean; payload?: { dataKey: string; value: number; color: string; name: string }[]; label?: string;
  formatter?: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium text-popover-foreground">{label}</p>
      {payload.map((p) => (
        <p key={p.dataKey} className="flex items-center gap-2 text-muted-foreground">
          <span className="size-2 rounded-sm" style={{ background: p.color }} aria-hidden />
          <span className="flex-1">{p.name}</span>
          <span className="tabular font-medium text-popover-foreground">{formatter ? formatter(p.value) : p.value}</span>
        </p>
      ))}
    </div>
  );
}

export function Legend({ series }: { series: Series[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground" aria-label="Legend">
      {series.map((s) => (
        <li key={s.key} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: s.color }} aria-hidden />
          {s.label}
        </li>
      ))}
    </ul>
  );
}

/** Chart with a table toggle: identity is never colour-only and the data is always readable as text. */
export function ChartFrame({ title, description, series, table, children, height = 260 }: {
  title: string; description?: string; series?: Series[]; table: { columns: string[]; rows: (string | number)[][] };
  children: React.ReactNode; height?: number;
}) {
  const [asTable, setAsTable] = useState(false);
  return (
    <section className="rounded-xl border bg-card p-5" aria-label={title}>
      <div className="mb-3 flex items-start justify-between gap-2">
        <div>
          <h3 className="text-sm font-semibold">{title}</h3>
          {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
        </div>
        <Button variant="ghost" size="sm" onClick={() => setAsTable((v) => !v)} aria-pressed={asTable} className="h-7 text-xs">
          {asTable ? <BarChart3 className="size-3.5" /> : <Table2 className="size-3.5" />} {asTable ? "Chart" : "Table"}
        </Button>
      </div>
      {series && series.length > 1 && !asTable && <div className="mb-2"><Legend series={series} /></div>}
      {asTable ? (
        <div className="max-h-[320px] overflow-auto rounded-md border">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-muted text-left text-muted-foreground">
              <tr>{table.columns.map((c) => <th key={c} className="px-2 py-1.5 font-medium">{c}</th>)}</tr>
            </thead>
            <tbody className="tabular">
              {table.rows.map((r, i) => (
                <tr key={i} className="border-t">{r.map((v, j) => <td key={j} className="px-2 py-1">{v}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div style={{ height }}>{children}</div>
      )}
    </section>
  );
}

export function StackedBars({ data, xKey, series, xFormatter }: {
  data: Record<string, string | number | null>[]; xKey: string; series: Series[]; xFormatter?: (v: string) => string;
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 4, right: 4, left: -16, bottom: 0 }} barCategoryGap="25%">
        <CartesianGrid {...GRID} />
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={xFormatter} minTickGap={12} />
        <YAxis {...AXIS} allowDecimals={false} />
        <Tooltip cursor={{ fill: "var(--muted)", opacity: 0.5 }} content={<ChartTooltip />} labelFormatter={(l) => (xFormatter ? xFormatter(String(l)) : String(l))} />
        {series.map((s, i) => (
          <Bar key={s.key} dataKey={s.key} name={s.label} stackId="a" fill={s.color} stroke="var(--chart-surface)" strokeWidth={2}
            radius={i === series.length - 1 ? [4, 4, 0, 0] : 0} maxBarSize={36} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

export function SimpleBars({ data, xKey, yKey, label, color = "var(--series-late)", allTicks = true }: {
  data: Record<string, string | number>[]; xKey: string; yKey: string; label: string; color?: string;
  /** false = thin out category labels so long date axes never collide */
  allTicks?: boolean;
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 4, right: 4, left: -16, bottom: 0 }} barCategoryGap="20%">
        <CartesianGrid {...GRID} />
        <XAxis dataKey={xKey} {...AXIS} interval={allTicks ? 0 : "preserveStartEnd"} minTickGap={allTicks ? 0 : 16} fontSize={10} />
        <YAxis {...AXIS} allowDecimals={false} />
        <Tooltip cursor={{ fill: "var(--muted)", opacity: 0.5 }} content={<ChartTooltip />} />
        <Bar dataKey={yKey} name={label} fill={color} radius={[4, 4, 0, 0]} maxBarSize={40} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function Lines({ data, xKey, series, xFormatter, yFormatter, domain, connectNulls = true }: {
  data: Record<string, string | number | null | undefined>[]; xKey: string; series: Series[];
  xFormatter?: (v: string) => string; yFormatter?: (v: number) => string; domain?: [number | "auto", number | "auto"];
  connectNulls?: boolean;
}) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 6, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid {...GRID} />
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={xFormatter} minTickGap={24} />
        <YAxis {...AXIS} tickFormatter={yFormatter} domain={domain ?? ["auto", "auto"]} width={48} />
        <Tooltip content={<ChartTooltip formatter={yFormatter} />} labelFormatter={(l) => (xFormatter ? xFormatter(String(l)) : String(l))}
          cursor={{ stroke: "var(--chart-axis)", strokeWidth: 1, strokeDasharray: "3 3" }} />
        {series.map((s) => (
          <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2} dot={false}
            activeDot={{ r: 4, stroke: "var(--chart-surface)", strokeWidth: 2 }} connectNulls={connectNulls} isAnimationActive={false} />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

export function AreaSeries({ data, xKey, yKey, label, color, xFormatter, yFormatter }: {
  data: Record<string, string | number | null>[]; xKey: string; yKey: string; label: string; color: string;
  xFormatter?: (v: string) => string; yFormatter?: (v: number) => string;
}) {
  const id = `grad-${yKey}`;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 6, right: 8, left: -12, bottom: 0 }}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.25} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid {...GRID} />
        <XAxis dataKey={xKey} {...AXIS} tickFormatter={xFormatter} minTickGap={24} />
        <YAxis {...AXIS} tickFormatter={yFormatter} width={48} />
        <Tooltip content={<ChartTooltip formatter={yFormatter} />} labelFormatter={(l) => (xFormatter ? xFormatter(String(l)) : String(l))}
          cursor={{ stroke: "var(--chart-axis)", strokeWidth: 1, strokeDasharray: "3 3" }} />
        <Area type="monotone" dataKey={yKey} name={label} stroke={color} strokeWidth={2} fill={`url(#${id})`} connectNulls isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

export const DISEASE_SERIES: Series[] = [
  { key: "healthy", label: "Healthy", color: "var(--series-healthy)" },
  { key: "early_blight", label: "Early Blight", color: "var(--series-early)" },
  { key: "late_blight", label: "Late Blight", color: "var(--series-late)" },
  { key: "uncertain", label: "Review required", color: "var(--series-unclassified)" },
];

export const shortDate = (d: string) => new Date(d + (d.length === 10 ? "T00:00:00" : "")).toLocaleDateString(undefined, { month: "short", day: "numeric" });
export const clock = (d: string) => new Date(d).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit" });
