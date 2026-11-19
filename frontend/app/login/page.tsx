"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle, Leaf, Loader2, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { errorMessage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const schema = z.object({
  username: z.string().trim().min(1, "Username is required"),
  password: z.string().min(1, "Password is required"),
});
type FormValues = z.infer<typeof schema>;

export default function LoginPage() {
  const { login, status } = useAuth();
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState } = useForm<FormValues>({ resolver: zodResolver(schema), defaultValues: { username: "admin", password: "" } });

  useEffect(() => {
    if (status === "authenticated") router.replace("/");
  }, [status, router]);

  const onSubmit = async (values: FormValues) => {
    setError(null);
    try {
      await login(values.username, values.password);
      router.replace("/");
    } catch (e) {
      setError(errorMessage(e));
    }
  };

  return (
    <div className="grid min-h-screen lg:grid-cols-2">
      <div className="relative hidden overflow-hidden bg-sidebar p-12 text-sidebar-foreground lg:flex lg:flex-col lg:justify-between">
        <div className="absolute -right-24 -top-24 size-96 rounded-full bg-primary/20 blur-3xl" aria-hidden />
        <div className="absolute -bottom-32 left-10 size-80 rounded-full bg-primary/10 blur-3xl" aria-hidden />
        <div className="relative flex items-center gap-2.5">
          <span className="grid size-10 place-items-center rounded-xl bg-primary text-primary-foreground"><Leaf className="size-5" /></span>
          <span className="text-lg font-semibold">AgriGuard</span>
        </div>
        <div className="relative max-w-md">
          <h1 className="text-3xl font-semibold leading-tight tracking-tight">Detect crop disease early. Spray only when it is safe.</h1>
          <p className="mt-4 text-sidebar-muted">
            AI-assisted tomato leaf diagnosis with a deterministic safety engine. Every spray decision is explained,
            approved and audited.
          </p>
          <ul className="mt-8 space-y-3 text-sm">
            {["MobileNetV2 classifier with honest uncertainty handling", "13 independent safety rules + emergency stop", "Simulator-first, ESP32-CAM ready"].map((t) => (
              <li key={t} className="flex items-center gap-2"><ShieldCheck className="size-4 text-primary" />{t}</li>
            ))}
          </ul>
        </div>
        <p className="relative text-xs text-sidebar-muted">Decision support only, not a guaranteed field diagnosis.</p>
      </div>
      <div className="flex items-center justify-center px-4 py-12">
        <form onSubmit={handleSubmit(onSubmit)} className="w-full max-w-sm space-y-5" noValidate>
          <div className="lg:hidden flex items-center gap-2">
            <span className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground"><Leaf className="size-5" /></span>
            <span className="text-lg font-semibold">AgriGuard</span>
          </div>
          <div>
            <h2 className="text-2xl font-semibold tracking-tight">Sign in</h2>
            <p className="mt-1 text-sm text-muted-foreground">Use your operator account.</p>
          </div>
          {error && (
            <div role="alert" className="flex items-start gap-2 rounded-lg border border-critical/30 bg-critical/5 p-3 text-sm text-red-800 dark:text-red-300">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" /> {error}
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="username">Username</Label>
            <Input id="username" autoComplete="username" {...register("username")} aria-invalid={!!formState.errors.username} />
            {formState.errors.username && <p className="text-xs text-critical">{formState.errors.username.message}</p>}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input id="password" type="password" autoComplete="current-password" {...register("password")} aria-invalid={!!formState.errors.password} />
            {formState.errors.password && <p className="text-xs text-critical">{formState.errors.password.message}</p>}
          </div>
          <Button type="submit" className="w-full" disabled={formState.isSubmitting}>
            {formState.isSubmitting && <Loader2 className="size-4 animate-spin" />} Sign in
          </Button>
          <p className="text-xs text-muted-foreground">
            Local development default: <code className="rounded bg-muted px-1">admin</code> /{" "}
            <code className="rounded bg-muted px-1">agriguard-dev</code> (disabled in production; change it in Settings).
          </p>
        </form>
      </div>
    </div>
  );
}
