import type { AspectRatio } from "@/lib/api/types";

/** The four export shapes. Sizes match processing/openclip_processing/render.py exactly. */
export const RATIOS: ReadonlyArray<{ id: AspectRatio; width: number; height: number; label: string; use: string }> = [
  { id: "9:16", width: 1080, height: 1920, label: "Vertical", use: "Shorts, TikTok, Reels" },
  { id: "4:5", width: 1080, height: 1350, label: "Portrait", use: "Instagram and Facebook feeds" },
  { id: "1:1", width: 1080, height: 1080, label: "Square", use: "Feeds and carousels" },
  { id: "16:9", width: 1920, height: 1080, label: "Landscape", use: "YouTube, LinkedIn, X" },
];

export function ratioInfo(id: AspectRatio) {
  return RATIOS.find((r) => r.id === id) ?? RATIOS[0];
}

/** Width divided by height. */
export function ratioValue(id: AspectRatio): number {
  const { width, height } = ratioInfo(id);
  return width / height;
}

/** Which side a "crop" export trims (same rule as the backend's framing.crop_axis). */
export function cropAxis(sourceWidth: number | null | undefined, sourceHeight: number | null | undefined, ratio: AspectRatio): "x" | "y" | null {
  if (!sourceWidth || !sourceHeight) return "x";
  const source = sourceWidth / sourceHeight;
  const target = ratioValue(ratio);
  if (Math.abs(source - target) / target < 0.01) return null;
  return source > target ? "x" : "y";
}

/** CSS object-position that previews the backend's crop window for a 0..1 position. */
export function cropObjectPosition(axis: "x" | "y" | null, position: number): string {
  const pct = `${Math.round(Math.min(Math.max(position, 0), 1) * 1000) / 10}%`;
  if (axis === "y") return `50% ${pct}`;
  if (axis === "x") return `${pct} 50%`;
  return "50% 50%";
}

/** Preview frame size that fits inside a box without distortion. */
export function fitFrame(ratio: AspectRatio, maxWidth: number, maxHeight: number): { width: number; height: number } {
  const value = ratioValue(ratio);
  let width = maxWidth;
  let height = width / value;
  if (height > maxHeight) {
    height = maxHeight;
    width = height * value;
  }
  return { width: Math.round(width), height: Math.round(height) };
}

/** Caption scale used by the backend: font sizes are defined for a 1080-pixel short side. */
export function captionScale(frameWidth: number, frameHeight: number): number {
  return Math.min(frameWidth, frameHeight) / 1080;
}
