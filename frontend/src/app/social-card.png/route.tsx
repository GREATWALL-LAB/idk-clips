import { ImageResponse } from "next/og";

export const dynamic = "force-static";

const size = { width: 1200, height: 630 };

/**
 * The social preview card (/social-card.png), drawn at build time in the brand palette.
 * The page metadata only points to it when NEXT_PUBLIC_SITE_URL is set, because social
 * networks need an absolute address.
 */
export function GET() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 72, background: "#F7F9FC", color: "#172033" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 20 }}>
          <div style={{ width: 72, height: 72, borderRadius: 20, background: "#2457F5", display: "flex", alignItems: "center", justifyContent: "center", position: "relative" }}>
            <div style={{ width: 28, height: 46, border: "5px solid #FFFFFF", borderRadius: 8, display: "flex" }} />
            <div style={{ position: "absolute", left: 14, top: 33, width: 44, height: 5, borderRadius: 3, background: "#B9F56A" }} />
          </div>
          <div style={{ display: "flex", fontSize: 44, fontWeight: 700 }}>
            IDK<span style={{ color: "#2457F5", marginLeft: 12 }}>Clips</span>
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 24 }}>
          <div style={{ display: "flex", fontSize: 76, fontWeight: 700, lineHeight: 1.05, maxWidth: 980 }}>Long videos in. Short clips out.</div>
          <div style={{ display: "flex", fontSize: 32, color: "#545F73", maxWidth: 940 }}>
            AI transcription, moment detection, captions and four export shapes. Free and MIT licensed.
          </div>
        </div>
        <div style={{ display: "flex", gap: 14 }}>
          {["9:16", "4:5", "1:1", "16:9"].map((ratio) => (
            <div key={ratio} style={{ display: "flex", padding: "10px 22px", borderRadius: 999, border: "2px solid #E9EDF3", background: "#FFFFFF", fontSize: 26, fontWeight: 600 }}>
              {ratio}
            </div>
          ))}
          <div style={{ display: "flex", padding: "10px 22px", borderRadius: 999, background: "#B9F56A", fontSize: 26, fontWeight: 600 }}>Open source</div>
        </div>
      </div>
    ),
    size,
  );
}
