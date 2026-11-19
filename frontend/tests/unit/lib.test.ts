import { describe, expect, it, vi } from "vitest";
import { api, ApiError, buildUrl, errorMessage, getToken, setToken, wsUrl } from "@/lib/api";
import { duration, num, pct, shortId, timeAgo } from "@/lib/format";

describe("format helpers", () => {
  it("formats percentages and handles missing values", () => {
    expect(pct(0.923)).toBe("92%");
    expect(pct(0.9234, 1)).toBe("92.3%");
    expect(pct(null)).toBe("—");
    expect(num(undefined)).toBe("—");
    expect(num(3.14159, 2, " °C")).toBe("3.14 °C");
  });
  it("formats relative time and durations", () => {
    const now = Date.parse("2026-11-18T12:00:00Z");
    expect(timeAgo("2026-11-18T11:59:58Z", now)).toBe("just now");
    expect(timeAgo("2026-11-18T11:59:30Z", now)).toBe("30s ago");
    expect(timeAgo("2026-11-18T11:30:00Z", now)).toBe("30 min ago");
    expect(timeAgo(null, now)).toBe("never");
    expect(duration(45)).toBe("45s");
    expect(duration(900)).toBe("15 min");
    expect(shortId("scan_abcdef123456")).toBe("scan_abcdef");
  });
});

describe("api client", () => {
  it("builds URLs and skips empty query values", () => {
    const url = buildUrl("/scans", { label: "healthy", q: "", page: 2, x: undefined });
    expect(url).toContain("/scans?label=healthy&page=2");
    expect(url).not.toContain("q=");
  });

  it("attaches the bearer token and parses JSON", async () => {
    setToken("tok123");
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ ok: 1 }), { status: 200 }));
    await expect(api<{ ok: number }>("/health")).resolves.toEqual({ ok: 1 });
    const headers = fetchMock.mock.calls[0][1]?.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer tok123");
  });

  it("normalises the backend error envelope", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({
      error: { code: "CONFLICT", message: "spray already active", details: { a: 1 }, request_id: "rid" },
    }), { status: 409 }));
    const err = (await api("/x").catch((e) => e)) as ApiError;
    expect(err).toBeInstanceOf(ApiError);
    expect(err.code).toBe("CONFLICT");
    expect(err.status).toBe(409);
    expect(err.requestId).toBe("rid");
    expect(errorMessage(err)).toBe("spray already active");
  });

  it("clears the session on 401 and emits an event", async () => {
    setToken("expired");
    const onUnauth = vi.fn();
    window.addEventListener("agriguard:unauthorized", onUnauth);
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ error: { code: "UNAUTHORIZED", message: "x" } }), { status: 401 }));
    await expect(api("/devices")).rejects.toBeInstanceOf(ApiError);
    expect(getToken()).toBeNull();
    expect(onUnauth).toHaveBeenCalled();
  });

  it("reports network failures clearly", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("Failed to fetch"));
    const err = (await api("/x").catch((e) => e)) as ApiError;
    expect(err.code).toBe("NETWORK_ERROR");
  });

  it("returns undefined for 204 and sends JSON bodies", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(null, { status: 204 }));
    await expect(api("/auth/change-password", { body: { a: 1 } })).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0][1]?.method).toBe("POST");
    expect(fetchMock.mock.calls[0][1]?.body).toBe('{"a":1}');
  });

  it("builds websocket URLs with the token", () => {
    setToken("t0k");
    expect(wsUrl("/ws/events")).toMatch(/^ws:\/\/.*\/ws\/events\?token=t0k$/);
  });
});
