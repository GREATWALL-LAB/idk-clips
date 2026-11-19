import type { CaptionLine, CaptionStyle, Segment } from "@/lib/api/types";

export type CueWord = { start: number; end: number; text: string };
export type Cue = { start: number; end: number; text: string; words?: CueWord[] };

/** Transcript words whose midpoint lies inside [start, end) (same rule as the backend). */
export function wordsInRange(segments: Segment[], start: number, end: number): CueWord[] {
  const words: CueWord[] = [];
  for (const segment of segments) {
    if (segment.end < start || segment.start > end) continue;
    for (const word of segment.words) {
      const middle = (word.start + word.end) / 2;
      if (middle >= start && middle < end) words.push({ start: word.start, end: word.end, text: word.text.trim() });
    }
  }
  return words;
}

/** Caption cues generated from the real transcript words, relative to the clip start. */
export function generatedCues(segments: Segment[], start: number, end: number, perLine: number): Cue[] {
  const words = wordsInRange(segments, start, end);
  const cues: Cue[] = [];
  const size = Math.max(1, perLine);
  for (let i = 0; i < words.length; i += size) {
    const group = words.slice(i, i + size);
    const relative = group.map((w) => ({ start: Math.max(w.start - start, 0), end: Math.min(w.end, end) - start, text: w.text }));
    const text = group.map((w) => w.text).join(" ").trim();
    if (text) cues.push({ start: relative[0].start, end: relative[relative.length - 1].end, text, words: relative });
  }
  // Keep each caption until the next one starts when the pause is short (matches the export).
  for (let i = 0; i < cues.length - 1; i += 1) {
    const gap = cues[i + 1].start - cues[i].end;
    if (gap > 0 && gap < 0.6) cues[i].end = cues[i + 1].start;
  }
  return cues;
}

export function linesFromCues(cues: Cue[]): CaptionLine[] {
  return cues.map((c) => ({ start: Math.round(c.start * 1000) / 1000, end: Math.round(c.end * 1000) / 1000, text: c.text }));
}

export const CAPTION_FONTS: Record<CaptionStyle["font"], string> = {
  Montserrat: "var(--font-caption-montserrat), sans-serif",
  Poppins: "var(--font-caption-poppins), sans-serif",
  Anton: "var(--font-caption-anton), sans-serif",
};

export const DEFAULT_STYLE: CaptionStyle = {
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
};
