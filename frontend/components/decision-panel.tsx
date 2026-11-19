"use client";

import { CheckCircle2, CircleHelp, Info, XCircle } from "lucide-react";
import { OutcomePill } from "@/components/common";
import { RULE_LABEL, dateTime } from "@/lib/format";
import type { Decision } from "@/lib/types";
import { cn } from "@/lib/utils";

export function DecisionPanel({ decision, compact = false }: { decision: Decision; compact?: boolean }) {
  const warnings = decision.reasons.filter((r) => r.startsWith("Warning: "));
  const reasons = decision.reasons.filter((r) => !r.startsWith("Warning: "));
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <OutcomePill outcome={decision.outcome} />
        <span className="text-xs text-muted-foreground">
          Policy v{decision.policy_version} · {decision.stage === "approval" ? "re-evaluated at approval" : "evaluated at scan"} ·{" "}
          {dateTime(decision.evaluated_at)}
        </span>
      </div>
      <ul className="space-y-1 text-sm">
        {reasons.map((r) => (
          <li key={r} className="font-medium">{r}</li>
        ))}
        {warnings.map((w) => (
          <li key={w} className="flex items-start gap-1.5 text-amber-700 dark:text-amber-300">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden /> {w.replace("Warning: ", "")}
          </li>
        ))}
      </ul>
      {!compact && (
        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-sm">
            <caption className="sr-only">Safety rule evaluation</caption>
            <thead className="bg-muted/60 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">Rule</th>
                <th className="px-3 py-2 font-medium">Result</th>
                <th className="hidden px-3 py-2 font-medium sm:table-cell">Detail</th>
              </tr>
            </thead>
            <tbody>
              {decision.rules.map((r) => {
                const state = r.passed === true ? "pass" : r.passed === false ? "fail" : "unknown";
                const Icon = state === "pass" ? CheckCircle2 : state === "fail" ? XCircle : CircleHelp;
                return (
                  <tr key={r.rule} className="border-t align-top">
                    <td className="px-3 py-2">
                      <span className="font-medium">{RULE_LABEL[r.rule] ?? r.rule}</span>
                      {!r.critical && <span className="ml-1 text-xs text-muted-foreground">(advisory)</span>}
                    </td>
                    <td className="px-3 py-2">
                      <span className={cn("inline-flex items-center gap-1 text-xs font-medium",
                        state === "pass" && "text-green-700 dark:text-green-400",
                        state === "fail" && (r.critical ? "text-red-700 dark:text-red-400" : "text-amber-700 dark:text-amber-300"),
                        state === "unknown" && "text-orange-700 dark:text-orange-300")}>
                        <Icon className="size-3.5" aria-hidden />
                        {state === "pass" ? "Pass" : state === "fail" ? "Fail" : "Unknown"}
                      </span>
                      <p className="mt-0.5 text-xs text-muted-foreground sm:hidden">{r.message}</p>
                    </td>
                    <td className="hidden px-3 py-2 text-muted-foreground sm:table-cell">{r.message}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
