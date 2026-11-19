"use client";

import { useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import { cn } from "@/lib/cn";
import { formatDuration, formatTimestamp } from "@/lib/format";

type WordMark = { start: number; end: number; text: string };

const MIN_LENGTH = 3;

function niceStep(span: number): number {
  const steps = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600];
  return steps.find((s) => span / s <= 10) ?? 1200;
}

/**
 * Zoomed timeline around the clip: drag the handles to trim, drag the selection to move it,
 * click anywhere to seek. Handles are keyboard accessible (arrows: 0.1 s, Shift: 1 s).
 */
export function Timeline({
  duration,
  start,
  end,
  currentTime,
  words,
  snap,
  onChange,
  onSeek,
}: {
  duration: number;
  start: number;
  end: number;
  currentTime: number;
  words: WordMark[];
  snap: boolean;
  onChange: (start: number, end: number) => void;
  onSeek: (seconds: number) => void;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<null | { kind: "start" | "end" | "move"; origin: number; start: number; end: number }>(null);

  // Visible window: the clip plus some context on both sides (frozen while dragging).
  const length = end - start;
  const pad = Math.max(8, length * 0.6);
  const [frozen, setFrozen] = useState<{ from: number; to: number } | null>(null);
  const viewFrom = frozen?.from ?? Math.max(0, start - pad);
  const viewTo = frozen?.to ?? Math.min(duration, end + pad);
  const span = Math.max(viewTo - viewFrom, 1);
  const toPct = (t: number) => ((t - viewFrom) / span) * 100;

  const timeAt = (clientX: number) => {
    const rect = trackRef.current?.getBoundingClientRect();
    if (!rect) return 0;
    const ratio = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1);
    return viewFrom + ratio * span;
  };

  const snapTo = (t: number, edge: "start" | "end") => {
    if (!snap || words.length === 0) return t;
    let best = t;
    let bestDistance = 0.35;
    for (const w of words) {
      const candidate = edge === "start" ? w.start : w.end;
      const distance = Math.abs(candidate - t);
      if (distance < bestDistance) {
        best = candidate;
        bestDistance = distance;
      }
    }
    return best;
  };

  const clamp = (s: number, e: number): [number, number] => {
    s = Math.max(0, Math.min(s, duration - MIN_LENGTH));
    e = Math.min(duration, Math.max(e, s + MIN_LENGTH));
    return [Math.round(s * 100) / 100, Math.round(e * 100) / 100];
  };

  function beginDrag(kind: "start" | "end" | "move", event: PointerEvent) {
    event.preventDefault();
    event.stopPropagation();
    (event.target as HTMLElement).setPointerCapture(event.pointerId);
    setFrozen({ from: viewFrom, to: viewTo });
    setDrag({ kind, origin: timeAt(event.clientX), start, end });
  }

  function onPointerMove(event: PointerEvent) {
    if (!drag) return;
    const t = timeAt(event.clientX);
    if (drag.kind === "start") onChange(...clamp(snapTo(Math.min(t, drag.end - MIN_LENGTH), "start"), drag.end));
    else if (drag.kind === "end") onChange(...clamp(drag.start, snapTo(Math.max(t, drag.start + MIN_LENGTH), "end")));
    else {
      const delta = t - drag.origin;
      const len = drag.end - drag.start;
      const s = Math.max(0, Math.min(drag.start + delta, duration - len));
      onChange(...clamp(s, s + len));
    }
  }

  function endDrag() {
    setDrag(null);
    setFrozen(null);
  }

  function onHandleKey(edge: "start" | "end", event: KeyboardEvent) {
    const step = event.shiftKey ? 1 : 0.1;
    const delta = event.key === "ArrowLeft" || event.key === "ArrowDown" ? -step : event.key === "ArrowRight" || event.key === "ArrowUp" ? step : 0;
    if (!delta) return;
    event.preventDefault();
    if (edge === "start") onChange(...clamp(start + delta, end));
    else onChange(...clamp(start, end + delta));
  }

  const step = niceStep(span);
  const ticks: number[] = [];
  for (let t = Math.ceil(viewFrom / step) * step; t <= viewTo; t += step) ticks.push(t);
  const visibleWords = words.filter((w) => w.end >= viewFrom && w.start <= viewTo);

  return (
    <div className="space-y-2 select-none">
      {/* Overview of the whole video */}
      <div
        className="relative h-1.5 cursor-pointer rounded-full bg-line-strong"
        onClick={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          onSeek(((e.clientX - rect.left) / rect.width) * duration);
        }}
        aria-hidden="true"
      >
        <div className="absolute inset-y-0 rounded-full bg-brand/70" style={{ left: `${(start / duration) * 100}%`, width: `${((end - start) / duration) * 100}%` }} />
        <div className="absolute inset-y-0 w-px bg-ink/30" style={{ left: `${(viewFrom / duration) * 100}%` }} />
        <div className="absolute inset-y-0 w-px bg-ink/30" style={{ left: `${(viewTo / duration) * 100}%` }} />
      </div>

      <div
        ref={trackRef}
        className="relative h-24 cursor-crosshair overflow-hidden rounded-2xl border border-line bg-canvas"
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        onClick={(e) => {
          if (!drag) onSeek(timeAt(e.clientX));
        }}
      >
        {/* Ticks */}
        {ticks.map((t) => (
          <div key={t} className="absolute top-0 h-full border-l border-line" style={{ left: `${toPct(t)}%` }}>
            {/* Labels near the right edge sit left of their tick so they are never cut off. */}
            <span className={cn("absolute top-1 whitespace-nowrap font-mono text-[10px] text-subtle", toPct(t) > 90 ? "right-1" : "left-1")}>{formatDuration(t)}</span>
          </div>
        ))}
        {/* Word markers from the real transcript */}
        {visibleWords.map((w, i) => (
          <div
            key={`${w.start}-${i}`}
            title={w.text}
            className="absolute bottom-3 h-3 rounded-sm bg-ink/20"
            style={{ left: `${toPct(w.start)}%`, width: `${Math.max(toPct(w.end) - toPct(w.start), 0.3)}%` }}
          />
        ))}
        {/* Selection */}
        <div
          className={cn("absolute inset-y-0 border-y-2 border-brand bg-brand-50", drag?.kind === "move" ? "cursor-grabbing" : "cursor-grab")}
          style={{ left: `${toPct(start)}%`, width: `${toPct(end) - toPct(start)}%` }}
          onPointerDown={(e) => beginDrag("move", e)}
        >
          <span className="pointer-events-none absolute left-1/2 top-1.5 -translate-x-1/2 whitespace-nowrap rounded-md bg-ink px-1.5 py-0.5 font-mono text-[10px] text-white">
            {formatTimestamp(end - start)}
          </span>
        </div>
        {(["start", "end"] as const).map((edge) => {
          const value = edge === "start" ? start : end;
          return (
            <div
              key={edge}
              role="slider"
              tabIndex={0}
              aria-label={edge === "start" ? "Clip start" : "Clip end"}
              aria-valuemin={0}
              aria-valuemax={Math.round(duration * 10) / 10}
              aria-valuenow={Math.round(value * 10) / 10}
              aria-valuetext={formatTimestamp(value)}
              onKeyDown={(e) => onHandleKey(edge, e)}
              onPointerDown={(e) => beginDrag(edge, e)}
              className="absolute inset-y-0 z-10 w-3 -translate-x-1/2 cursor-ew-resize rounded-md bg-brand shadow-[0_0_0_3px_rgb(36_87_245/0.25)] focus-visible:outline-2 focus-visible:outline-brand"
              style={{ left: `${toPct(value)}%` }}
            >
              <span className="absolute left-1/2 top-1/2 h-6 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded bg-white/80" />
            </div>
          );
        })}
        {/* Playhead */}
        {currentTime >= viewFrom && currentTime <= viewTo ? (
          <div className="pointer-events-none absolute inset-y-0 z-20 w-0.5 bg-ink" style={{ left: `${toPct(currentTime)}%` }}>
            <span className="absolute -top-0.5 left-1/2 size-2 -translate-x-1/2 rounded-full bg-ink" />
          </div>
        ) : null}
      </div>
      <div className="flex justify-between font-mono text-[11px] text-subtle">
        <span>{formatTimestamp(viewFrom)}</span>
        <span className="hidden sm:inline">Drag the handles or the selection · arrow keys for fine steps</span>
        <span>{formatTimestamp(viewTo)}</span>
      </div>
    </div>
  );
}
