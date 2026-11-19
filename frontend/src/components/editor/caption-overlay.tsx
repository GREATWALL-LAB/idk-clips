import type { CSSProperties } from "react";
import { CAPTION_FONTS, type Cue } from "@/components/editor/captions";
import type { CaptionStyle } from "@/lib/api/types";
import { captionScale } from "@/lib/aspect";

/**
 * Renders the caption that is active at `time` (seconds from the clip start).
 * Sizes follow the export: font sizes are defined for a 1080-pixel short side, so the
 * preview matches the burned-in captions in every aspect ratio.
 */
export function CaptionOverlay({
  cues,
  time,
  style,
  frameWidth,
  frameHeight,
}: {
  cues: Cue[];
  time: number;
  style: CaptionStyle;
  frameWidth: number;
  frameHeight: number;
}) {
  const cue = cues.find((c) => time >= c.start && time < c.end);
  if (!cue) return null;
  const scale = captionScale(frameWidth, frameHeight);
  const transform = (text: string) => (style.uppercase ? text.toUpperCase() : text);

  const position: CSSProperties =
    style.position === "top"
      ? { top: `${12}%` }
      : style.position === "middle"
        ? { top: "50%", transform: "translateY(-50%)" }
        : { bottom: `${17}%` };

  const textStyle: CSSProperties = {
    fontFamily: CAPTION_FONTS[style.font],
    fontSize: `${style.font_size * scale}px`,
    lineHeight: 1.15,
    color: style.text_color,
    fontWeight: style.font === "Anton" ? 400 : 700,
    ...(style.background
      ? { backgroundColor: `${style.background_color}BF`, padding: `${0.12 * style.font_size * scale}px ${0.3 * style.font_size * scale}px`, borderRadius: 4 }
      : {
          WebkitTextStroke: `${style.outline_width * scale * 2}px ${style.outline_color}`,
          paintOrder: "stroke fill",
          textShadow: `0 ${2 * scale}px ${3 * scale}px rgb(0 0 0 / 0.5)`,
        }),
    boxDecorationBreak: "clone",
    WebkitBoxDecorationBreak: "clone",
  };

  let activeIndex = -1;
  if (style.highlight_words && cue.words) {
    cue.words.forEach((word, index) => {
      if (time >= word.start) activeIndex = index;
    });
  }

  return (
    <div className="pointer-events-none absolute inset-x-[7%] text-center" style={position} aria-hidden="true">
      <span style={textStyle}>
        {style.highlight_words && cue.words
          ? cue.words.map((word, index) => (
              <span key={`${word.start}-${index}`} style={index === activeIndex ? { color: style.highlight_color } : undefined}>
                {transform(word.text)}
                {index < (cue.words?.length ?? 0) - 1 ? " " : ""}
              </span>
            ))
          : transform(cue.text)}
      </span>
    </div>
  );
}
