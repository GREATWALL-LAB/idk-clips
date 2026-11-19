import { ImageResponse } from "next/og";

export const dynamic = "force-static";

const size = { width: 180, height: 180 };

/** Home-screen icon (/apple-icon.png; iOS needs a PNG): the IDK Clips mark on a full-bleed tile. */
export function GET() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center", background: "#2457F5" }}>
        <div style={{ position: "relative", width: 68, height: 112, border: "12px solid #FFFFFF", borderRadius: 18, display: "flex" }} />
        <div style={{ position: "absolute", left: 34, top: 84, width: 112, height: 12, borderRadius: 6, background: "#B9F56A" }} />
      </div>
    ),
    size,
  );
}
