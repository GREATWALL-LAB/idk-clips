import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { setReducedMotion } from "@/test/setup";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => "/" }));

async function renderHome() {
  vi.resetModules();
  const { default: HomePage } = await import("@/app/page");
  return render(<HomePage />);
}

describe("homepage", () => {
  it("has every required section and navigation entry", async () => {
    // CI sets the real repository URL; this test checks the menu without it.
    vi.stubEnv("NEXT_PUBLIC_GITHUB_URL", "");
    const { container } = await renderHome();
    for (const id of ["how-it-works", "features", "run-locally", "use-online", "open-source"]) {
      expect(container.querySelector(`#${id}`), id).not.toBeNull();
    }
    const nav = screen.getAllByRole("navigation", { name: "Primary" })[0];
    const labels = Array.from(nav.querySelectorAll("a")).map((a) => a.textContent?.trim());
    expect(labels).toEqual(["Features", "How it works", "Run locally", "Use online", "Open source", "Docs"]);
    expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Long videos in.");
    expect(screen.getAllByRole("link", { name: /start creating/i }).length).toBeGreaterThan(0);
    expect(screen.getByRole("link", { name: /explore open source/i }).getAttribute("href")).toBe("/#open-source");
  });

  it("tells the whole story in six steps", async () => {
    await renderHome();
    for (const title of [
      "Start with the long version.",
      "Every word, on the clock.",
      "AI finds what stands on its own.",
      "Five to ten clips, ready to refine.",
      "9:16, 4:5, 1:1 or 16:9.",
      "Preview it, then press export.",
    ]) {
      expect(screen.getByRole("heading", { name: title })).toBeTruthy();
    }
  });

  it("never shows a GitHub link until a real one is configured", async () => {
    vi.stubEnv("NEXT_PUBLIC_GITHUB_URL", "");
    await renderHome();
    expect(screen.queryByRole("link", { name: /github/i })).toBeNull();
    expect(screen.getByText(/repository link will appear here/i)).toBeTruthy();
  });

  it("shows the configured GitHub repository", async () => {
    vi.stubEnv("NEXT_PUBLIC_GITHUB_URL", "https://github.com/example/openclip");
    await renderHome();
    const links = screen.getAllByRole("link", { name: /github/i });
    expect(links.every((link) => link.getAttribute("href") === "https://github.com/example/openclip")).toBe(true);
  });

  it("makes no claims with invented numbers", async () => {
    const { container } = await renderHome();
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/\b\d+(\.\d+)?\s*(k|m)?\+?\s*(users|creators|downloads|clips created)\b/i);
    expect(text).not.toMatch(/testimonial|★/i);
  });

  it("still renders all content for people who prefer reduced motion", async () => {
    setReducedMotion(true);
    await renderHome();
    expect(screen.getAllByRole("heading", { level: 3 }).length).toBeGreaterThanOrEqual(6);
    expect(screen.getByText(/the shape you pick is the file you get/i)).toBeTruthy();
  });
});
