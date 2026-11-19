"use client";

import { useEffect, useState } from "react";
import {
  AlertTriangle, Ban, CheckCircle2, CircleDashed, CircleHelp, Clock, CloudOff, FlaskConical, Hourglass, Inbox,
  Loader2, OctagonX, PauseCircle, RefreshCw, ShieldCheck, Signal, SignalZero, Sparkles, XCircle,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { errorMessage } from "@/lib/api";
import { OP_STATUS_LABEL, OUTCOME_LABEL, dateTime, timeAgo } from "@/lib/format";
import type { Connectivity, DecisionOutcome, OperationStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function StatCard({
  label, value, hint, icon: Icon, tone = "default",
}: {
  label: string; value: React.ReactNode; hint?: React.ReactNode; icon: React.ElementType;
  tone?: "default" | "good" | "warning" | "critical";
}) {
  const toneCls = {
    default: "bg-secondary text-secondary-foreground",
    good: "bg-good/12 text-good",
    warning: "bg-warning/15 text-amber-700 dark:text-warning",
    critical: "bg-critical/12 text-critical",
  }[tone];
  return (
    <Card className="gap-0 py-0">
      <CardContent className="flex items-start justify-between gap-3 p-5">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</p>
          <p className="tabular mt-2 text-3xl font-semibold tracking-tight">{value}</p>
          {hint && <p className="mt-1 text-xs text-muted-foreground">{hint}</p>}
        </div>
        <span className={cn("grid size-10 shrink-0 place-items-center rounded-xl", toneCls)}>
          <Icon className="size-5" aria-hidden />
        </span>
      </CardContent>
    </Card>
  );
}

export function SimBadge({ simulated = true, className }: { simulated?: boolean; className?: string }) {
  if (!simulated) {
    return (
      <Badge variant="outline" className={cn("gap-1 border-primary/40 text-primary", className)}>
        <Signal className="size-3" aria-hidden /> Hardware
      </Badge>
    );
  }
  return (
    <Badge variant="outline" className={cn("gap-1 border-sim/40 bg-sim/10 text-sim", className)}>
      <FlaskConical className="size-3" aria-hidden /> Simulated
    </Badge>
  );
}

type Tone = "good" | "warning" | "serious" | "critical" | "neutral" | "info";

const TONE_CLS: Record<Tone, string> = {
  good: "border-good/30 bg-good/10 text-green-800 dark:text-green-300",
  warning: "border-warning/40 bg-warning/15 text-amber-800 dark:text-amber-200",
  serious: "border-serious/40 bg-serious/12 text-orange-800 dark:text-orange-200",
  critical: "border-critical/40 bg-critical/10 text-red-800 dark:text-red-300",
  neutral: "border-border bg-muted text-muted-foreground",
  info: "border-primary/30 bg-primary/10 text-primary",
};

export function Pill({ tone, icon: Icon, children, className }: { tone: Tone; icon: React.ElementType; children: React.ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium whitespace-nowrap", TONE_CLS[tone], className)}>
      <Icon className="size-3.5 shrink-0" aria-hidden />
      {children}
    </span>
  );
}

export function ConnectivityPill({ state }: { state: Connectivity }) {
  if (state === "online") return <Pill tone="good" icon={Signal}>Online</Pill>;
  if (state === "offline") return <Pill tone="critical" icon={SignalZero}>Offline</Pill>;
  return <Pill tone="neutral" icon={CircleDashed}>Never seen</Pill>;
}

const OUTCOME_STYLE: Record<DecisionOutcome, [Tone, React.ElementType]> = {
  AUTHORIZED: ["good", ShieldCheck],
  PENDING_APPROVAL: ["warning", Hourglass],
  BLOCKED: ["critical", Ban],
  REVIEW_REQUIRED: ["serious", CircleHelp],
  SKIP: ["neutral", CheckCircle2],
};

export function OutcomePill({ outcome }: { outcome: DecisionOutcome }) {
  const [tone, Icon] = OUTCOME_STYLE[outcome];
  return <Pill tone={tone} icon={Icon}>{OUTCOME_LABEL[outcome]}</Pill>;
}

const OP_STYLE: Record<OperationStatus, [Tone, React.ElementType]> = {
  PENDING_APPROVAL: ["warning", Hourglass],
  BLOCKED: ["critical", Ban],
  DISPATCHED: ["info", Clock],
  RUNNING: ["info", Loader2],
  COMPLETED: ["good", CheckCircle2],
  FAILED: ["critical", XCircle],
  ABORTED: ["critical", OctagonX],
  REJECTED: ["neutral", PauseCircle],
  EXPIRED: ["neutral", Clock],
};

export function OpStatusPill({ status }: { status: OperationStatus }) {
  const [tone, Icon] = OP_STYLE[status];
  return (
    <Pill tone={tone} icon={Icon} className={status === "RUNNING" ? "[&>svg]:animate-spin" : undefined}>
      {OP_STATUS_LABEL[status]}
    </Pill>
  );
}

export function LabelPill({ label, status }: { label: string | null; status: string }) {
  if (status === "MODEL_UNAVAILABLE") return <Pill tone="neutral" icon={CloudOff}>Model unavailable</Pill>;
  if (!label || status !== "CONFIDENT") return <Pill tone="serious" icon={CircleHelp}>Review required</Pill>;
  if (label === "healthy") return <Pill tone="good" icon={Sparkles}>Healthy</Pill>;
  return (
    <Pill tone="critical" icon={AlertTriangle}>
      {label === "early_blight" ? "Early Blight" : label === "late_blight" ? "Late Blight" : label}
    </Pill>
  );
}

export function ConfidenceBar({ value, threshold }: { value: number | null; threshold?: number }) {
  const v = value ?? 0;
  return (
    <div className="flex items-center gap-2" aria-label={`Confidence ${(v * 100).toFixed(0)} percent`}>
      <div className="relative h-1.5 w-24 overflow-hidden rounded-full bg-muted">
        <div className="absolute inset-y-0 left-0 rounded-full bg-primary" style={{ width: `${v * 100}%` }} />
        {threshold !== undefined && (
          <div className="absolute inset-y-0 w-0.5 bg-foreground/60" style={{ left: `${threshold * 100}%` }} title="Threshold" />
        )}
      </div>
      <span className="tabular text-xs text-muted-foreground">{value === null ? "—" : `${(v * 100).toFixed(0)}%`}</span>
    </div>
  );
}

/** Relative time that re-renders every 10 s, with the absolute time on hover. */
export function TimeAgo({ iso, className }: { iso: string | null | undefined; className?: string }) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 10000);
    return () => clearInterval(t);
  }, []);
  if (!iso) return <span className={className}>never</span>;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <time dateTime={iso} className={cn("cursor-default", className)}>{timeAgo(iso)}</time>
      </TooltipTrigger>
      <TooltipContent>{new Date(iso).toLocaleString()} (local time)</TooltipContent>
    </Tooltip>
  );
}

export function EmptyState({ icon: Icon = Inbox, title, description, action }: {
  icon?: React.ElementType; title: string; description?: string; action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-12 text-center">
      <span className="grid size-11 place-items-center rounded-full bg-muted text-muted-foreground">
        <Icon className="size-5" aria-hidden />
      </span>
      <p className="mt-3 font-medium">{title}</p>
      {description && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center justify-center rounded-xl border border-critical/30 bg-critical/5 px-6 py-10 text-center">
      <AlertTriangle className="size-6 text-critical" aria-hidden />
      <p className="mt-2 font-medium">Could not load data</p>
      <p className="mt-1 max-w-md text-sm text-muted-foreground">{errorMessage(error)}</p>
      {onRetry && (
        <Button variant="outline" size="sm" className="mt-4" onClick={onRetry}>
          <RefreshCw className="size-4" /> Retry
        </Button>
      )}
    </div>
  );
}

export function LoadingGrid({ count = 4, className }: { count?: number; className?: string }) {
  return (
    <div className={cn("grid gap-4 sm:grid-cols-2 xl:grid-cols-4", className)} aria-busy="true" aria-label="Loading">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-28 rounded-xl" />
      ))}
    </div>
  );
}

export function Freshness({ freshness, fetchedAt, source }: { freshness: string; fetchedAt: string | null; source: string }) {
  const tone: Tone = freshness === "live" ? "good" : freshness === "unavailable" ? "critical" : "warning";
  const Icon = freshness === "live" ? Signal : freshness === "unavailable" ? CloudOff : Clock;
  const label = freshness === "live" ? "Live" : freshness === "stale" ? "Stale (cached)" : freshness === "unavailable" ? "Unavailable" : "Cached";
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      <Pill tone={tone} icon={Icon}>{label}</Pill>
      <span>
        {source}
        {fetchedAt && <> · retrieved {dateTime(fetchedAt)} ({timeAgo(fetchedAt)})</>}
      </span>
    </div>
  );
}
