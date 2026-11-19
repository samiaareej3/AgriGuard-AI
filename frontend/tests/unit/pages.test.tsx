import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/lib/auth";

const replace = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
  usePathname: () => "/scans",
}));

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <AuthProvider>
        <TooltipProvider>{ui}</TooltipProvider>
      </AuthProvider>
    </QueryClientProvider>,
  );
}

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

beforeEach(() => replace.mockReset());

describe("Login page", () => {
  it("validates required fields before calling the API", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch");
    const { default: LoginPage } = await import("@/app/login/page");
    wrap(<LoginPage />);
    await userEvent.clear(screen.getByLabelText("Username"));
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByText("Username is required")).toBeInTheDocument();
    expect(screen.getByText("Password is required")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter((c) => String(c[0]).includes("/auth/login"))).toHaveLength(0);
  });

  it("shows the server error on bad credentials", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) =>
      String(url).includes("/auth/login")
        ? json({ error: { code: "INVALID_CREDENTIALS", message: "Invalid username or password" } }, 401)
        : json({}, 401),
    );
    const { default: LoginPage } = await import("@/app/login/page");
    wrap(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Password"), "wrong");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid username or password");
  });

  it("stores the token and redirects on success", async () => {
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) =>
      String(url).includes("/auth/login")
        ? json({ access_token: "tkn", token_type: "bearer", expires_in: 60, user: { id: "u", username: "admin", role: "admin", created_at: "2026-11-18T00:00:00Z", is_default_password: false } })
        : json({}, 401),
    );
    const { default: LoginPage } = await import("@/app/login/page");
    wrap(<LoginPage />);
    await userEvent.type(screen.getByLabelText("Password"), "secret");
    await userEvent.click(screen.getByRole("button", { name: /sign in/i }));
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(window.localStorage.getItem("agriguard.token")).toBe("tkn");
  });
});

describe("Scan history page", () => {
  const scan = {
    id: "scan_abc123", created_at: new Date().toISOString(), source: "simulator", simulated: true, device_id: "dev_1",
    submitted_by: "device:dev_1", original_filename: "x.jpg", content_type: "image/jpeg", size_bytes: 1000,
    quality: { width: 256, height: 256, brightness: 100, sharpness: 200, green_ratio: 0.4 },
    prediction: { status: "CONFIDENT", crop: "tomato", label: "late_blight", display_label: "Late Blight", top_label: "late_blight", confidence: 0.97, probabilities: {}, threshold: 0.75, model_version: "m", inference_ms: 10, warnings: [], timestamp: new Date().toISOString() },
    decision: { outcome: "PENDING_APPROVAL", reasons: [], rules: [], policy_version: 1, evaluated_at: new Date().toISOString(), stage: "scan" },
    spray_operation_id: "op_1", notes: null,
  };

  it("renders rows, shows the simulated label and sends filters to the API", async () => {
    window.localStorage.setItem("agriguard.token", "t");
    const calls: string[] = [];
    vi.spyOn(globalThis, "fetch").mockImplementation(async (url) => {
      const u = String(url);
      calls.push(u);
      if (u.includes("/auth/me")) return json({ id: "u", username: "op", role: "operator", created_at: "2026-11-18T00:00:00Z", is_default_password: false });
      if (u.includes("/devices")) return json([]);
      if (u.includes("/image")) return new Response(new Blob(["x"]), { status: 200 });
      if (u.includes("/scans")) {
        const empty = u.includes("label=healthy");
        return json({ items: empty ? [] : [scan], total: empty ? 0 : 1, page: 1, page_size: 20 });
      }
      return json({});
    });
    const { default: ScansPage } = await import("@/app/(dashboard)/scans/page");
    wrap(<ScansPage />);
    expect(await screen.findByText("scan_abc123")).toBeInTheDocument();
    expect(screen.getAllByText("Late Blight").length).toBeGreaterThan(1);
    expect(screen.getByText("Simulated")).toBeInTheDocument();
    expect(screen.getAllByText("Awaiting approval").length).toBeGreaterThan(1);
    await userEvent.type(screen.getByLabelText("Search"), "late");
    await userEvent.click(screen.getByRole("button", { name: /^search$/i }));
    await waitFor(() => expect(calls.some((c) => c.includes("/scans?") && c.includes("q=late"))).toBe(true));
  });
});
