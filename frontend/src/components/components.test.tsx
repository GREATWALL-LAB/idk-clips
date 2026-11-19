import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { buildUpdate } from "@/components/editor/clip-editor";
import { RatioPicker } from "@/components/editor/ratio-picker";
import { cropViewBox } from "@/components/home/scene-art";
import { WorkerNeeded } from "@/components/projects/worker-needed";
import { secondsLeft } from "@/components/workers/pairing-dialog";
import type { Clip, Worker } from "@/lib/api/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), replace: vi.fn() }), usePathname: () => "/", useSearchParams: () => new URLSearchParams() }));

const STYLE = {
  font: "Montserrat",
  font_size: 72,
  text_color: "#FFFFFF",
  highlight_color: "#FACC15",
  outline_color: "#000000",
  outline_width: 6,
  background: false,
  background_color: "#000000",
  position: "bottom",
  uppercase: false,
  highlight_words: true,
  words_per_line: 4,
} as const;

function clip(overrides: Partial<Clip> = {}): Clip {
  return {
    title: "Clip",
    description: "",
    start_seconds: 10,
    end_seconds: 40,
    aspect_ratio: "9:16",
    layout: "crop",
    crop_position: 0.5,
    auto_frame: true,
    captions_enabled: true,
    caption_style: { ...STYLE },
    ...overrides,
  } as Clip;
}

function draft(base: Clip, overrides: Record<string, unknown> = {}) {
  return {
    title: base.title,
    description: base.description,
    start: base.start_seconds,
    end: base.end_seconds,
    aspect_ratio: base.aspect_ratio,
    layout: base.layout,
    crop_position: base.crop_position,
    auto_frame: base.auto_frame,
    captions_enabled: base.captions_enabled,
    style: { ...base.caption_style },
    editedLines: null,
    ...overrides,
  };
}

describe("clip editor updates", () => {
  it("sends nothing when nothing changed", () => {
    const base = clip();
    expect(buildUpdate({ clip: base, edited: null }, draft(base) as never)).toEqual({});
  });

  it("sends the new aspect ratio and timing", () => {
    const base = clip();
    const body = buildUpdate({ clip: base, edited: null }, draft(base, { aspect_ratio: "4:5", end: 35 }) as never);
    expect(body).toEqual({ aspect_ratio: "4:5", end_seconds: 35 });
  });

  it("switches automatic framing off with a manual position", () => {
    const base = clip({ auto_frame: true });
    expect(buildUpdate({ clip: base, edited: null }, draft(base, { auto_frame: false, crop_position: 0.2 }) as never)).toEqual({ crop_position: 0.2 });
  });

  it("turns automatic framing back on", () => {
    const base = clip({ auto_frame: false, crop_position: 0.3 });
    expect(buildUpdate({ clip: base, edited: null }, draft(base, { auto_frame: true }) as never)).toEqual({ auto_frame: true });
  });
});

describe("RatioPicker", () => {
  it("offers all four ratios and reports the choice", () => {
    const onChange = vi.fn();
    render(<RatioPicker value="9:16" onChange={onChange} />);
    const radios = screen.getAllByRole("radio");
    expect(radios.map((r) => within(r).getByText(/^\d+:\d+$/).textContent)).toEqual(["9:16", "4:5", "1:1", "16:9"]);
    expect(radios[0].getAttribute("aria-checked")).toBe("true");
    fireEvent.click(radios[3]);
    expect(onChange).toHaveBeenCalledWith("16:9");
  });
});

describe("homepage scene crops", () => {
  it("use the exporter's crop window", () => {
    expect(cropViewBox(9 / 16, 0)).toBe("0.0 0 506.3 900");
    expect(cropViewBox(9 / 16, 1)).toBe("1093.8 0 506.3 900");
    expect(cropViewBox(16 / 9, 0.5)).toBe("0 0.0 1600 900.0");
  });
});

describe("pairing codes", () => {
  it("count down to zero and never below", () => {
    const now = Date.parse("2026-11-17T10:00:00Z");
    expect(secondsLeft("2026-11-17T10:10:00Z", now)).toBe(600);
    expect(secondsLeft("2026-11-17T09:59:00Z", now)).toBe(0);
  });
});

describe("WorkerNeeded", () => {
  const base = { loading: false, local: null, error: null, refresh: vi.fn() };
  const worker = (online: boolean) => ({ id: "w", name: "Studio PC", online }) as Worker;

  it("asks to connect a computer when there is none", () => {
    render(<WorkerNeeded state={{ ...base, workers: [] }} />);
    expect(screen.getByText("Connect your computer first")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Connect a worker" }).getAttribute("href")).toMatch(/^\/workers\/?$/);
  });

  it("explains an offline worker", () => {
    render(<WorkerNeeded state={{ ...base, workers: [worker(false)] }} />);
    expect(screen.getByText("Your worker is offline")).toBeTruthy();
  });

  it("explains a worker on another computer", async () => {
    const refresh = vi.fn();
    render(<WorkerNeeded state={{ ...base, refresh, workers: [worker(true)] }} />);
    expect(screen.getByText("Your worker runs on another computer")).toBeTruthy();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: /check again/i })));
    expect(refresh).toHaveBeenCalled();
  });
});
