import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConnectivityPill, EmptyState, ErrorState, LabelPill, OpStatusPill, OutcomePill, SimBadge } from "@/components/common";
import { DecisionPanel } from "@/components/decision-panel";
import { ChartFrame } from "@/components/charts";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api";
import type { Decision } from "@/lib/types";

const decision: Decision = {
  outcome: "BLOCKED",
  reasons: ["Device is offline", "Warning: Weather data unavailable"],
  rules: [
    { rule: "CONFIDENCE_THRESHOLD", passed: true, critical: true, message: "Confidence 92% ≥ 75%" },
    { rule: "DEVICE_ONLINE", passed: false, critical: true, message: "Device is offline" },
    { rule: "DEVICE_HEALTHY", passed: null, critical: true, message: "Unknown: tank level" },
    { rule: "WEATHER_SUITABLE", passed: null, critical: false, message: "Weather data unavailable" },
  ],
  policy_version: 3,
  evaluated_at: "2026-11-18T12:00:00Z",
  stage: "scan",
};

describe("status components always pair colour with a text label", () => {
  it("renders outcome, op status, connectivity and label pills", () => {
    render(<>
      <OutcomePill outcome="PENDING_APPROVAL" />
      <OpStatusPill status="ABORTED" />
      <ConnectivityPill state="offline" />
      <LabelPill label="late_blight" status="CONFIDENT" />
      <LabelPill label={null} status="UNCERTAIN" />
      <LabelPill label={null} status="MODEL_UNAVAILABLE" />
      <SimBadge />
    </>);
    for (const t of ["Awaiting approval", "Aborted", "Offline", "Late Blight", "Review required", "Model unavailable", "Simulated"]) {
      expect(screen.getByText(t)).toBeInTheDocument();
    }
  });
});

describe("DecisionPanel", () => {
  it("shows outcome, reasons, warnings and every rule with pass/fail/unknown", () => {
    render(<DecisionPanel decision={decision} />);
    expect(screen.getByText("Blocked")).toBeInTheDocument();
    expect(screen.getByText(/Policy v3/)).toBeInTheDocument();
    expect(screen.getAllByText("Device is offline").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Weather data unavailable").length).toBeGreaterThan(0);
    expect(screen.getByText("Pass")).toBeInTheDocument();
    expect(screen.getByText("Fail")).toBeInTheDocument();
    expect(screen.getAllByText("Unknown")).toHaveLength(2);
    expect(screen.getByText("(advisory)")).toBeInTheDocument();
  });
  it("compact mode hides the rule table", () => {
    render(<DecisionPanel decision={decision} compact />);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("empty / error states", () => {
  it("renders empty state with action", () => {
    render(<EmptyState title="No scans yet" description="Upload one" action={<button>Go</button>} />);
    expect(screen.getByText("No scans yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go" })).toBeInTheDocument();
  });
  it("renders error state with retry", async () => {
    const retry = vi.fn();
    render(<ErrorState error={new ApiError(503, "DATABASE_UNAVAILABLE", "Database temporarily unavailable")} onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Database temporarily unavailable");
    await userEvent.click(screen.getByRole("button", { name: /retry/i }));
    expect(retry).toHaveBeenCalled();
  });
});

describe("ChartFrame", () => {
  it("toggles to an accessible data table", async () => {
    render(
      <TooltipProvider>
        <ChartFrame title="Scans" table={{ columns: ["Date", "Count"], rows: [["2026-11-18", 4]] }}>
          <div>chart</div>
        </ChartFrame>
      </TooltipProvider>,
    );
    expect(screen.getByText("chart")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /table/i }));
    expect(screen.getByRole("table")).toHaveTextContent("2026-11-18");
    expect(screen.queryByText("chart")).not.toBeInTheDocument();
  });
});
