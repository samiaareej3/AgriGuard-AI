"use client";

import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";
import { Database, FlaskConical, LogOut, Menu, Monitor, Moon, Sun, UserRound } from "lucide-react";
import { Pill } from "@/components/common";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup,
  DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useAuth } from "@/lib/auth";
import { useSummary } from "@/lib/queries";
import { useRealtime } from "@/lib/realtime";
import { cn } from "@/lib/utils";
import { EmergencyStopButton } from "./estop";
import { titleFor } from "./nav";

function LinkIndicator() {
  const { state } = useRealtime();
  const label = { live: "Live", connecting: "Connecting", reconnecting: "Reconnecting", offline: "Offline" }[state];
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <span className="flex items-center gap-1.5 text-xs text-muted-foreground" role="status">
          <span className={cn("size-2 rounded-full", state === "live" ? "bg-good" : state === "offline" ? "bg-critical" : "animate-pulse bg-warning")} aria-hidden />
          <span className="hidden md:inline">{label}</span>
        </span>
      </TooltipTrigger>
      <TooltipContent>Real-time event stream: {label}</TooltipContent>
    </Tooltip>
  );
}

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const pathname = usePathname();
  const { user, logout } = useAuth();
  const { data } = useSummary();
  const { theme, setTheme } = useTheme();
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b bg-background/85 px-4 backdrop-blur lg:px-8">
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={onMenu} aria-label="Open navigation">
        <Menu className="size-5" />
      </Button>
      <p className="truncate text-sm font-medium">{titleFor(pathname)}</p>
      <div className="ml-auto flex items-center gap-2 sm:gap-3">
        {data && data.devices.simulated > 0 && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span><Pill tone="info" icon={FlaskConical} className="hidden border-sim/40 bg-sim/10 text-sim sm:inline-flex">Simulator active</Pill></span>
            </TooltipTrigger>
            <TooltipContent>{data.devices.simulated} simulated device(s). Their telemetry and operations are demo data.</TooltipContent>
          </Tooltip>
        )}
        {data?.database_mode === "memory" && (
          <Tooltip>
            <TooltipTrigger asChild>
              <span><Pill tone="warning" icon={Database} className="hidden md:inline-flex">In-memory DB</Pill></span>
            </TooltipTrigger>
            <TooltipContent>MONGODB_URI not configured: data is lost when the API restarts.</TooltipContent>
          </Tooltip>
        )}
        <LinkIndicator />
        <EmergencyStopButton />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Account menu">
              <UserRound className="size-5" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <DropdownMenuLabel>
              <span className="block">{user?.username}</span>
              <span className="block text-xs font-normal capitalize text-muted-foreground">{user?.role}</span>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">Theme</DropdownMenuLabel>
            <DropdownMenuRadioGroup value={theme ?? "system"} onValueChange={setTheme}>
              <DropdownMenuRadioItem value="light"><Sun className="size-4" /> Light</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="dark"><Moon className="size-4" /> Dark</DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="system"><Monitor className="size-4" /> System</DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={logout}><LogOut className="size-4" /> Sign out</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
