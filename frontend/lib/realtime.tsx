"use client";

import { createContext, useContext, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { wsUrl } from "./api";
import type { LiveEvent } from "./types";

export type LinkState = "connecting" | "live" | "reconnecting" | "offline";

interface RealtimeState {
  state: LinkState;
  events: LiveEvent[];
  subscribe: (fn: (e: LiveEvent) => void) => () => void;
}

const RealtimeContext = createContext<RealtimeState>({ state: "offline", events: [], subscribe: () => () => {} });

// Which cached queries each event type makes stale.
const INVALIDATE: Record<string, string[][]> = {
  "scan.created": [["scans"], ["summary"], ["analytics"]],
  "spray.updated": [["operations"], ["summary"], ["devices"]],
  "device.updated": [["devices"], ["summary"]],
  "device.deleted": [["devices"], ["summary"]],
  "device.connectivity": [["devices"], ["summary"]],
  "estop.changed": [["estop"], ["summary"]],
  "policy.updated": [["policy"]],
  "log.created": [["logs"]],
  "command.queued": [["commands"]],
};

export function RealtimeProvider({ enabled, children }: { enabled: boolean; children: React.ReactNode }) {
  const qc = useQueryClient();
  const [state, setState] = useState<LinkState>("offline");
  const [events, setEvents] = useState<LiveEvent[]>([]);
  const listeners = useRef(new Set<(e: LiveEvent) => void>());

  useEffect(() => {
    if (!enabled) return;
    let ws: WebSocket | null = null;
    let retry = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let closed = false;
    const pending = new Set<string>();
    let flush: ReturnType<typeof setTimeout> | undefined;

    const invalidate = (type: string) => {
      for (const key of INVALIDATE[type] ?? []) pending.add(JSON.stringify(key));
      if (!flush) {
        // Coalesce bursts (simulator ticks) into one refetch per key.
        flush = setTimeout(() => {
          pending.forEach((k) => qc.invalidateQueries({ queryKey: JSON.parse(k) }));
          pending.clear();
          flush = undefined;
        }, 400);
      }
    };

    const connect = () => {
      setState(retry === 0 ? "connecting" : "reconnecting");
      ws = new WebSocket(wsUrl("/ws/events"));
      ws.onopen = () => {
        retry = 0;
        setState("live");
      };
      ws.onmessage = (msg) => {
        let event: LiveEvent;
        try {
          event = JSON.parse(msg.data);
        } catch {
          return;
        }
        if (event.type === "ping" || event.type === "hello") return;
        invalidate(event.type);
        listeners.current.forEach((fn) => fn(event));
        if (event.type !== "device.heartbeat") setEvents((prev) => [event, ...prev].slice(0, 100));
      };
      ws.onclose = (ev) => {
        if (closed) return;
        if (ev.code === 4401) {
          setState("offline");
          return;
        }
        setState("reconnecting");
        retry += 1;
        timer = setTimeout(connect, Math.min(15000, 1000 * 2 ** Math.min(retry, 4)));
      };
      ws.onerror = () => ws?.close();
    };
    connect();
    return () => {
      closed = true;
      clearTimeout(timer);
      clearTimeout(flush);
      ws?.close();
      setState("offline");
    };
  }, [enabled, qc]);

  const subscribe = (fn: (e: LiveEvent) => void) => {
    listeners.current.add(fn);
    return () => listeners.current.delete(fn);
  };

  return <RealtimeContext.Provider value={{ state, events, subscribe }}>{children}</RealtimeContext.Provider>;
}

export function useRealtime() {
  return useContext(RealtimeContext);
}
