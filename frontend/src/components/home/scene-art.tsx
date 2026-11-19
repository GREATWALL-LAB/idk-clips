import type { CSSProperties } from "react";

/**
 * An illustrated 16:9 "podcast studio" frame used across the homepage, so crops and
 * aspect ratios are demonstrated on the same picture. Flat brand colours, no photos.
 * The guest on the right is the active speaker (used for subject-aware crops).
 */
export const SCENE_WIDTH = 1600;
export const SCENE_HEIGHT = 900;
/** Where the speaking guest sits, as a fraction of the free space when cropping (0 = left). */
export const SPEAKER_FOCUS = 0.8;

/**
 * The crop window for an output shape, computed like the exporter does: the largest
 * window with the target ratio, moved along the cropped axis by `focus` (0..1).
 */
export function cropViewBox(aspect: number, focus = 0.5): string {
  const sourceAspect = SCENE_WIDTH / SCENE_HEIGHT;
  const position = Math.min(Math.max(focus, 0), 1);
  if (aspect < sourceAspect) {
    const width = SCENE_HEIGHT * aspect;
    return `${((SCENE_WIDTH - width) * position).toFixed(1)} 0 ${width.toFixed(1)} ${SCENE_HEIGHT}`;
  }
  const height = SCENE_WIDTH / aspect;
  return `0 ${((SCENE_HEIGHT - height) * position).toFixed(1)} ${SCENE_WIDTH} ${height.toFixed(1)}`;
}

export function SceneArt({
  className,
  style,
  crop,
  title = "Illustration of a two-person video podcast",
}: {
  className?: string;
  style?: CSSProperties;
  /** Show only the window an export in this shape would contain. */
  crop?: { aspect: number; focus?: number };
  title?: string;
}) {
  const viewBox = crop ? cropViewBox(crop.aspect, crop.focus) : `0 0 ${SCENE_WIDTH} ${SCENE_HEIGHT}`;
  return (
    <svg viewBox={viewBox} preserveAspectRatio="xMidYMid slice" className={className} style={style} role="img" aria-label={title}>
      {/* wall */}
      <rect width="1600" height="900" fill="#E9EDF3" />
      <rect x="0" y="0" width="1600" height="560" fill="#F7F9FC" />
      <rect x="90" y="90" width="430" height="300" rx="28" fill="#2457F5" />
      <rect x="130" y="130" width="350" height="12" rx="6" fill="#B9F56A" />
      <rect x="130" y="166" width="230" height="12" rx="6" fill="#FFFFFF" opacity="0.55" />
      <rect x="1140" y="70" width="360" height="210" rx="24" fill="#172033" />
      <circle cx="1210" cy="140" r="26" fill="#B9F56A" />
      <rect x="1256" y="128" width="190" height="10" rx="5" fill="#FFFFFF" opacity="0.6" />
      <rect x="1256" y="152" width="130" height="10" rx="5" fill="#FFFFFF" opacity="0.35" />
      {[0, 1, 2, 3, 4, 5].map((i) => (
        <rect key={i} x={640 + i * 64} y={120} width="40" height={170 - (i % 3) * 30} rx="12" fill="#B9F56A" opacity={0.35 + (i % 2) * 0.25} />
      ))}
      {/* plant */}
      <rect x="560" y="430" width="70" height="90" rx="14" fill="#172033" />
      <path d="M595 430 C560 360 520 340 500 300 C560 320 590 360 595 430 Z" fill="#2457F5" />
      <path d="M598 430 C620 350 660 320 700 300 C680 360 640 390 598 430 Z" fill="#B9F56A" />

      {/* host (left) */}
      <g>
        <path d="M200 900 C200 690 280 600 420 600 C560 600 640 690 640 900 Z" fill="#172033" />
        <rect x="392" y="540" width="56" height="80" rx="20" fill="#C98E62" />
        <circle cx="420" cy="470" r="104" fill="#C98E62" />
        <path d="M316 462 C316 380 370 340 430 344 C500 348 534 400 526 450 C500 410 440 404 380 420 C346 430 330 448 316 462 Z" fill="#2B1C14" />
        <circle cx="384" cy="478" r="8" fill="#172033" />
        <circle cx="456" cy="478" r="8" fill="#172033" />
        <path d="M392 524 Q420 540 448 524" stroke="#172033" strokeWidth="7" fill="none" strokeLinecap="round" />
      </g>
      {/* guest (right, speaking) */}
      <g>
        <path d="M900 900 C900 680 990 590 1130 590 C1270 590 1360 680 1360 900 Z" fill="#2457F5" />
        <path d="M1060 640 L1130 720 L1200 640 Z" fill="#B9F56A" />
        <rect x="1100" y="520" width="60" height="86" rx="22" fill="#F2C9A5" />
        <circle cx="1130" cy="450" r="108" fill="#F2C9A5" />
        <path d="M1018 452 C1006 350 1076 316 1140 320 C1220 324 1262 384 1244 470 C1236 420 1196 392 1140 392 C1090 392 1040 410 1018 452 Z" fill="#7A4B2A" />
        <circle cx="1094" cy="460" r="8" fill="#172033" />
        <circle cx="1168" cy="460" r="8" fill="#172033" />
        <ellipse cx="1131" cy="512" rx="24" ry="16" fill="#172033" />
        <ellipse cx="1131" cy="507" rx="16" ry="6" fill="#E9EDF3" />
      </g>
      {/* desk + mics */}
      <rect x="0" y="760" width="1600" height="140" fill="#172033" />
      <rect x="0" y="752" width="1600" height="14" fill="#2457F5" />
      <rect x="470" y="600" width="18" height="160" rx="9" fill="#364156" />
      <rect x="446" y="560" width="66" height="96" rx="33" fill="#364156" />
      <rect x="1004" y="600" width="18" height="160" rx="9" fill="#364156" />
      <rect x="980" y="560" width="66" height="96" rx="33" fill="#364156" />
      <circle cx="1013" cy="586" r="10" fill="#B9F56A" />
    </svg>
  );
}
