import {
  Activity, BarChart3, Cpu, LayoutDashboard, Leaf, ScanSearch, Settings, SprayCan, Sprout, History,
} from "lucide-react";

export const NAV = [
  {
    group: "Monitor",
    items: [
      { href: "/", label: "Overview", icon: LayoutDashboard },
      { href: "/monitoring", label: "Live Monitoring", icon: Activity },
    ],
  },
  {
    group: "Detect",
    items: [
      { href: "/detect", label: "Disease Detection", icon: ScanSearch },
      { href: "/scans", label: "Scan History", icon: History },
    ],
  },
  {
    group: "Operate",
    items: [
      { href: "/operations", label: "Spray Operations", icon: SprayCan },
      { href: "/devices", label: "Devices", icon: Cpu },
    ],
  },
  {
    group: "Analyze",
    items: [
      { href: "/analytics", label: "Analytics", icon: BarChart3 },
      { href: "/insights", label: "Agri Insights", icon: Sprout },
    ],
  },
  { group: "System", items: [{ href: "/settings", label: "Settings", icon: Settings }] },
] as const;

export const BRAND_ICON = Leaf;

export function titleFor(pathname: string): string {
  for (const g of NAV) for (const i of g.items) if (i.href === pathname || (i.href !== "/" && pathname.startsWith(i.href))) return i.label;
  return "AgriGuard";
}
