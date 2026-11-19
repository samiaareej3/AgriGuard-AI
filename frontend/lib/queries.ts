"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, errorMessage } from "./api";
import type {
  Analytics, Climate, DataSource, Device, DeviceCommand, EmergencyStop, ExternalData, Forecast, LogEntry, Page,
  Scan, SimulatorStatus, SprayOperation, SprayPolicy, Summary, SystemInfo, TelemetryPoint, User,
} from "./types";

export const useSummary = () =>
  useQuery({ queryKey: ["summary"], queryFn: () => api<Summary>("/dashboard/summary"), refetchInterval: 15000 });

export const useDevices = () =>
  useQuery({ queryKey: ["devices"], queryFn: () => api<Device[]>("/devices"), refetchInterval: 10000 });

export const useTelemetry = (deviceId: string | null, minutes = 30) =>
  useQuery({
    queryKey: ["telemetry", deviceId, minutes],
    queryFn: () => api<TelemetryPoint[]>(`/devices/${deviceId}/telemetry`, { query: { minutes } }),
    enabled: !!deviceId,
  });

export const useCommands = (deviceId: string | null) =>
  useQuery({
    queryKey: ["commands", deviceId],
    queryFn: () => api<DeviceCommand[]>(`/devices/${deviceId}/commands`),
    enabled: !!deviceId,
  });

export const useSimulator = () =>
  useQuery({ queryKey: ["simulator"], queryFn: () => api<SimulatorStatus>("/simulator/status"), refetchInterval: 5000 });

export interface ScanFilters {
  q?: string;
  label?: string;
  outcome?: string;
  device_id?: string;
  source?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  page_size?: number;
}

export const useScans = (filters: ScanFilters) =>
  useQuery({
    queryKey: ["scans", filters],
    queryFn: () => api<Page<Scan>>("/scans", { query: { ...filters } }),
    placeholderData: (prev) => prev,
  });

export const useScan = (id: string) => useQuery({ queryKey: ["scans", "one", id], queryFn: () => api<Scan>(`/scans/${id}`) });

export const useOperations = (status?: string, page = 1) =>
  useQuery({
    queryKey: ["operations", status, page],
    queryFn: () => api<Page<SprayOperation>>("/spray/operations", { query: { status, page, page_size: 25 } }),
    placeholderData: (prev) => prev,
    refetchInterval: 10000,
  });

export const usePolicy = () => useQuery({ queryKey: ["policy"], queryFn: () => api<SprayPolicy>("/spray/policy") });

export const useEstop = () =>
  useQuery({ queryKey: ["estop"], queryFn: () => api<EmergencyStop>("/safety/emergency-stop"), refetchInterval: 10000 });

export const useAnalytics = (days: number) =>
  useQuery({ queryKey: ["analytics", days], queryFn: () => api<Analytics>("/analytics", { query: { days } }) });

export const useWeather = () =>
  useQuery({ queryKey: ["weather"], queryFn: () => api<ExternalData<Forecast>>("/insights/weather"), staleTime: 60000 });

export const useClimate = () =>
  useQuery({ queryKey: ["climate"], queryFn: () => api<ExternalData<Climate>>("/insights/climate"), staleTime: 300000 });

export const useSources = () => useQuery({ queryKey: ["sources"], queryFn: () => api<DataSource[]>("/insights/sources") });

export const useSystemInfo = () => useQuery({ queryKey: ["system"], queryFn: () => api<SystemInfo>("/system/info") });

export const useUsers = (enabled: boolean) =>
  useQuery({ queryKey: ["users"], queryFn: () => api<User[]>("/users"), enabled });

export const useLogs = (params: { category?: string; level?: string; page?: number }) =>
  useQuery({
    queryKey: ["logs", params],
    queryFn: () => api<Page<LogEntry>>("/logs", { query: { ...params, page_size: 50 } }),
    placeholderData: (prev) => prev,
  });

/** Mutation helper: toasts on success/error and invalidates the given keys. */
export function useAction<TVars, TResult = unknown>(
  fn: (vars: TVars) => Promise<TResult>,
  opts: { success?: string | ((r: TResult) => string); invalidate?: string[][]; onSuccess?: (r: TResult) => void } = {},
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: (r) => {
      if (opts.success) toast.success(typeof opts.success === "function" ? opts.success(r) : opts.success);
      opts.invalidate?.forEach((k) => qc.invalidateQueries({ queryKey: k }));
      opts.onSuccess?.(r);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}
