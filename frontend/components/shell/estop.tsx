"use client";

import { useState } from "react";
import { OctagonAlert, RotateCcw } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dateTime } from "@/lib/format";
import { useAction, useEstop } from "@/lib/queries";
import type { EmergencyStop } from "@/lib/types";

export function EmergencyStopButton() {
  const { can } = useAuth();
  const { data } = useEstop();
  const [reason, setReason] = useState("");
  const [open, setOpen] = useState(false);
  const activate = useAction(
    (r: string) => api<EmergencyStop>("/safety/emergency-stop", { body: { reason: r } }),
    { success: "Emergency stop activated: all operations aborted, STOP sent to every device", invalidate: [["estop"], ["summary"], ["operations"]], onSuccess: () => { setOpen(false); setReason(""); } },
  );
  const allowed = can("operator");
  const button = (
    <Button
      variant="destructive"
      size="sm"
      disabled={!allowed}
      className="gap-1.5 bg-critical font-semibold shadow-sm hover:bg-critical/90"
      aria-label="Emergency stop"
    >
      <OctagonAlert className="size-4" aria-hidden />
      <span className="hidden sm:inline">{data?.active ? "E-STOP ACTIVE" : "Emergency stop"}</span>
      <span className="sm:hidden">STOP</span>
    </Button>
  );
  if (!allowed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild><span tabIndex={0}>{button}</span></TooltipTrigger>
        <TooltipContent>Requires operator role</TooltipContent>
      </Tooltip>
    );
  }
  return (
    <AlertDialog open={open} onOpenChange={setOpen}>
      <AlertDialogTrigger asChild>{button}</AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-critical">
            <OctagonAlert className="size-5" /> Activate emergency stop?
          </AlertDialogTitle>
          <AlertDialogDescription>
            All pending and running spray operations are aborted immediately, queued commands are cancelled and a STOP
            command is sent to every device. New operations stay blocked until an admin resets the stop.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="space-y-1.5">
          <Label htmlFor="estop-reason">Reason (recorded in the audit log)</Label>
          <Input id="estop-reason" autoFocus value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Person entered spray zone" />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className="bg-critical text-white hover:bg-critical/90"
            disabled={reason.trim().length < 3 || activate.isPending}
            onClick={(e) => {
              e.preventDefault();
              activate.mutate(reason.trim());
            }}
          >
            {activate.isPending ? "Stopping…" : "Activate emergency stop"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

export function EmergencyStopBanner() {
  const { data } = useEstop();
  const { can } = useAuth();
  const [reason, setReason] = useState("");
  const reset = useAction(
    (r: string) => api<EmergencyStop>("/safety/emergency-stop/reset", { body: { reason: r } }),
    { success: "Emergency stop reset", invalidate: [["estop"], ["summary"]], onSuccess: () => setReason("") },
  );
  if (!data?.active) return null;
  return (
    <div role="alert" className="flex flex-col gap-3 border-b border-critical/40 bg-critical px-4 py-3 text-white sm:flex-row sm:items-center sm:justify-between lg:px-8">
      <div className="flex items-start gap-2">
        <OctagonAlert className="mt-0.5 size-5 shrink-0" aria-hidden />
        <div className="text-sm">
          <p className="font-semibold">EMERGENCY STOP ACTIVE: all spraying is blocked</p>
          <p className="text-white/85">
            “{data.reason}” · by {data.activated_by?.replace("user:", "")} at {dateTime(data.activated_at)}
          </p>
        </div>
      </div>
      {can("admin") ? (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            reset.mutate(reason.trim());
          }}
        >
          <Input
            aria-label="Reset reason"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Reset reason"
            className="h-8 w-44 border-white/40 bg-white/10 text-white placeholder:text-white/60"
          />
          <Button type="submit" size="sm" variant="secondary" disabled={reason.trim().length < 3 || reset.isPending}>
            <RotateCcw className="size-4" /> Reset
          </Button>
        </form>
      ) : (
        <p className="text-xs text-white/85">Only an admin can reset the emergency stop.</p>
      )}
    </div>
  );
}
