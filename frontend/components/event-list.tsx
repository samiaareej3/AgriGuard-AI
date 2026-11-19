"use client";

import { TimeAgo } from "@/components/common";
import type { LiveEvent } from "@/lib/types";

export function EventList({ events }: { events: LiveEvent[] }) {
  const logs = events.filter((e) => e.type === "log.created").slice(0, 8);
  if (!logs.length) return <p className="text-sm text-muted-foreground">No recent activity.</p>;
  return (
    <ol className="space-y-2.5">
      {logs.map((e) => {
        const d = e.data as { message?: string; level?: string; simulated?: boolean };
        return (
          <li key={e.id ?? e.ts} className="flex gap-2 text-sm">
            <span className={`mt-1.5 size-1.5 shrink-0 rounded-full ${d.level === "error" || d.level === "critical" ? "bg-critical" : d.level === "warning" ? "bg-warning" : "bg-primary"}`} aria-hidden />
            <div className="min-w-0">
              <p className="leading-snug">{d.message}</p>
              <p className="text-xs text-muted-foreground"><TimeAgo iso={e.ts} />{e.simulated ? " · simulated" : ""}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
