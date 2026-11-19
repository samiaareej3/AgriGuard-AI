"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Leaf } from "lucide-react";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";
import { EmergencyStopBanner } from "@/components/shell/estop";
import { SidebarNav } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { useAuth } from "@/lib/auth";
import { RealtimeProvider } from "@/lib/realtime";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);

  if (status !== "authenticated") {
    return (
      <div className="grid min-h-screen place-items-center" aria-busy="true">
        <Leaf className="size-8 animate-pulse text-primary" aria-label="Loading AgriGuard" />
      </div>
    );
  }

  return (
    <RealtimeProvider enabled>
      <div className="min-h-screen lg:pl-64">
        <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 bg-sidebar lg:block">
          <SidebarNav />
        </aside>
        <Sheet open={menuOpen} onOpenChange={setMenuOpen}>
          <SheetContent side="left" className="w-72 border-0 bg-sidebar p-0">
            <SheetTitle className="sr-only">Navigation</SheetTitle>
            <SidebarNav onNavigate={() => setMenuOpen(false)} />
          </SheetContent>
        </Sheet>
        <EmergencyStopBanner />
        <Topbar onMenu={() => setMenuOpen(true)} />
        <main className="mx-auto w-full max-w-[1400px] px-4 py-6 lg:px-8 lg:py-8">{children}</main>
      </div>
    </RealtimeProvider>
  );
}
