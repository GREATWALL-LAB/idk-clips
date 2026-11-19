import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom lacks a few browser APIs that components (and the motion library) use.
class FakeIntersectionObserver {
  readonly root = null;
  readonly rootMargin = "";
  readonly thresholds = [];
  constructor(private readonly callback: IntersectionObserverCallback) {}
  observe(target: Element) {
    this.callback([{ isIntersecting: false, target, intersectionRatio: 0 } as unknown as IntersectionObserverEntry], this as unknown as IntersectionObserver);
  }
  unobserve() {}
  disconnect() {}
  takeRecords() {
    return [];
  }
}

class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

let reducedMotion = false;
/** Tests can simulate the "reduce motion" system setting. */
export function setReducedMotion(value: boolean) {
  reducedMotion = value;
}

Object.assign(globalThis, { IntersectionObserver: FakeIntersectionObserver, ResizeObserver: FakeResizeObserver });
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: query.includes("prefers-reduced-motion") ? reducedMotion : false,
    media: query,
    onchange: null,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    addListener: () => undefined,
    removeListener: () => undefined,
    dispatchEvent: () => false,
  }),
});
window.scrollTo = vi.fn() as unknown as typeof window.scrollTo;

afterEach(() => {
  cleanup();
  reducedMotion = false;
});
