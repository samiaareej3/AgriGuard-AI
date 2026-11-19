/**
 * Typed API client for the AgriGuard backend.
 * Errors are normalised from the backend envelope {error: {code, message, details, request_id}}.
 */

export const API_URL = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1").replace(/\/$/, "");
const TOKEN_KEY = "agriguard.token";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details?: unknown,
    public requestId?: string | null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null) {
  try {
    if (token) window.localStorage.setItem(TOKEN_KEY, token);
    else window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage unavailable (private mode) – session lasts for this tab only */
  }
}

type Query = Record<string, string | number | boolean | null | undefined>;

export function buildUrl(path: string, query?: Query): string {
  const url = new URL(API_URL + path);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

async function parseError(res: Response): Promise<ApiError> {
  let body: { error?: { code?: string; message?: string; details?: unknown; request_id?: string } } | null = null;
  try {
    body = await res.json();
  } catch {
    /* non-JSON error */
  }
  const e = body?.error;
  return new ApiError(
    res.status,
    e?.code ?? `HTTP_${res.status}`,
    e?.message ?? res.statusText ?? "Request failed",
    e?.details,
    e?.request_id ?? res.headers.get("x-request-id"),
  );
}

export async function api<T>(
  path: string,
  options: { method?: string; body?: unknown; query?: Query; form?: FormData; signal?: AbortSignal } = {},
): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (options.form) body = options.form;
  else if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(options.body);
  }
  let res: Response;
  try {
    res = await fetch(buildUrl(path, options.query), {
      method: options.method ?? (body ? "POST" : "GET"),
      headers,
      body,
      signal: options.signal,
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") throw err;
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the AgriGuard API. Is the backend running?");
  }
  if (res.status === 401 && token) {
    setToken(null);
    if (typeof window !== "undefined") window.dispatchEvent(new Event("agriguard:unauthorized"));
  }
  if (!res.ok) throw await parseError(res);
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** Fetch an authenticated binary (e.g. scan image) and return an object URL. */
export async function fetchBlobUrl(path: string): Promise<string> {
  const token = getToken();
  const res = await fetch(buildUrl(path), { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw await parseError(res);
  return URL.createObjectURL(await res.blob());
}

export function wsUrl(path: string): string {
  const token = getToken() ?? "";
  const u = new URL(API_URL + path);
  u.protocol = u.protocol === "https:" ? "wss:" : "ws:";
  u.searchParams.set("token", token);
  return u.toString();
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return "Something went wrong";
}
