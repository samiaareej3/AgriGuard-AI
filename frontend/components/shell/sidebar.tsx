"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSummary } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { BRAND_ICON as Brand, NAV } from "./nav";

export function SidebarNav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { data } = useSummary();
  const pending = data?.operations.pending_approval ?? 0;
  return (
    <nav aria-label="Main" className="flex h-full flex-col">
      <Link href="/" onClick={onNavigate} className="flex items-center gap-2.5 px-5 py-5">
        <span className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm">
          <Brand className="size-5" aria-hidden />
        </span>
        <span>
          <span className="block text-[15px] font-semibold leading-tight text-sidebar-foreground">AgriGuard</span>
          <span className="block text-[11px] text-sidebar-muted">Precision crop protection</span>
        </span>
      </Link>
      <div className="flex-1 space-y-5 overflow-y-auto px-3 pb-4">
        {NAV.map((g) => (
          <div key={g.group}>
            <p className="px-3 pb-1.5 text-[11px] font-medium uppercase tracking-wider text-sidebar-muted">{g.group}</p>
            <ul className="space-y-0.5">
              {g.items.map((item) => {
                const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      onClick={onNavigate}
                      aria-current={active ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors focus-visible:outline-2 focus-visible:outline-primary",
                        active
                          ? "bg-sidebar-accent font-medium text-sidebar-foreground"
                          : "text-sidebar-muted hover:bg-sidebar-accent/60 hover:text-sidebar-foreground",
                      )}
                    >
                      <Icon className={cn("size-4", active && "text-primary")} aria-hidden />
                      <span className="flex-1">{item.label}</span>
                      {item.href === "/operations" && pending > 0 && (
                        <span className="tabular rounded-full bg-warning px-1.5 text-[11px] font-semibold text-black" aria-label={`${pending} awaiting approval`}>
                          {pending}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </div>
      <p className="border-t border-sidebar-border px-5 py-3 text-[11px] leading-snug text-sidebar-muted">
        Decision support only. Predictions never actuate hardware without the safety engine.
      </p>
    </nav>
  );
}
