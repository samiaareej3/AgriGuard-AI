import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

// jsdom lacks these browser APIs used by Radix/Recharts.
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}

(globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver ??= RO;
Element.prototype.scrollIntoView = Element.prototype.scrollIntoView ?? (() => {});
Element.prototype.hasPointerCapture = Element.prototype.hasPointerCapture ?? (() => false);
Element.prototype.releasePointerCapture = Element.prototype.releasePointerCapture ?? (() => {});
window.matchMedia = window.matchMedia ?? ((q: string) => ({
  matches: false, media: q, onchange: null, addListener() {}, removeListener() {}, addEventListener() {},
  removeEventListener() {}, dispatchEvent: () => false,
}));
URL.createObjectURL = URL.createObjectURL ?? (() => "blob:test");
URL.revokeObjectURL = URL.revokeObjectURL ?? (() => {});
