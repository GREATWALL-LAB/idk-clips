import { describe, expect, it } from "vitest";
import { captionScale, cropAxis, cropObjectPosition, fitFrame, RATIOS, ratioValue } from "@/lib/aspect";
import { cleanPublicUrl } from "@/lib/config";
import { formatBytes, formatDuration, formatTimestamp, parseTimestamp } from "@/lib/format";
import { isUuid, routes } from "@/lib/routes";
import { safeNextPath } from "@/lib/safe-redirect";

describe("aspect ratios", () => {
  it("match the exporter's pixel sizes exactly", () => {
    expect(RATIOS.map((r) => [r.id, r.width, r.height])).toEqual([
      ["9:16", 1080, 1920],
      ["4:5", 1080, 1350],
      ["1:1", 1080, 1080],
      ["16:9", 1920, 1080],
    ]);
    expect(ratioValue("16:9")).toBeCloseTo(16 / 9);
  });

  it("crop the same axis as the backend", () => {
    expect(cropAxis(1920, 1080, "9:16")).toBe("x"); // landscape source, vertical clip: trim the sides
    expect(cropAxis(1080, 1920, "16:9")).toBe("y"); // portrait source, landscape clip: trim top/bottom
    expect(cropAxis(1920, 1080, "16:9")).toBeNull(); // same shape: nothing to crop
    expect(cropAxis(1080, 1080, "4:5")).toBe("x"); // square source is wider than 4:5
    expect(cropAxis(1080, 1350, "1:1")).toBe("y");
  });

  it("preview the crop position on the right axis", () => {
    expect(cropObjectPosition("x", 0.25)).toBe("25% 50%");
    expect(cropObjectPosition("y", 1.4)).toBe("50% 100%");
    expect(cropObjectPosition(null, 0.9)).toBe("50% 50%");
  });

  it("fit preview frames without distortion", () => {
    expect(fitFrame("9:16", 520, 560)).toEqual({ width: 315, height: 560 });
    expect(fitFrame("16:9", 520, 560)).toEqual({ width: 520, height: 293 });
    const square = fitFrame("1:1", 520, 560);
    expect(square.width).toBe(square.height);
  });

  it("scales captions by the short side like the exporter", () => {
    expect(captionScale(1080, 1920)).toBe(1);
    expect(captionScale(1920, 1080)).toBe(1);
    expect(captionScale(270, 480)).toBe(0.25);
  });
});

describe("routes", () => {
  it("use query strings so the site can be a static export", () => {
    const id = "2fb110f9-ef33-4c53-bbd2-b46029f223ce";
    expect(routes.project(id)).toBe(`/projects/view/?id=${id}`);
    expect(routes.clip(id, id)).toBe(`/clips/edit/?project=${id}&clip=${id}`);
    expect(routes.doc("installation")).toBe("/docs/installation/");
  });

  it("only accept UUIDs from the address bar", () => {
    expect(isUuid("2fb110f9-ef33-4c53-bbd2-b46029f223ce")).toBe(true);
    for (const value of ["", null, "../../etc", "2fb110f9", "2fb110f9-ef33-4c53-bbd2-b46029f223ce/../x"]) {
      expect(isUuid(value)).toBe(false);
    }
  });
});

describe("safe redirects", () => {
  it("allow same-site paths only", () => {
    expect(safeNextPath("/projects/view/?id=1")).toBe("/projects/view/?id=1");
    for (const value of ["https://evil.example", "//evil.example", "/\\evil.example", "/login/", null]) {
      expect(safeNextPath(value)).toBe("/dashboard/");
    }
  });
});

describe("public links", () => {
  it("only accept absolute https URLs", () => {
    expect(cleanPublicUrl("https://github.com/owner/repo/")).toBe("https://github.com/owner/repo");
    expect(cleanPublicUrl("http://github.com/owner/repo")).toBeNull();
    expect(cleanPublicUrl("javascript:alert(1)")).toBeNull();
    expect(cleanPublicUrl("")).toBeNull();
    expect(cleanPublicUrl(undefined)).toBeNull();
  });
});

describe("formatting", () => {
  it("formats and parses times", () => {
    expect(formatDuration(3725)).toBe("1:02:05");
    expect(formatTimestamp(83.45)).toBe("1:23.5");
    expect(parseTimestamp("1:23.5")).toBeCloseTo(83.5);
    expect(parseTimestamp("1:02:03")).toBe(3723);
    expect(parseTimestamp("abc")).toBeNull();
    expect(formatBytes(1536)).toBe("1.5 KB");
  });
});
