import type { MetadataRoute } from "next";
import { BRAND } from "@/lib/config";

export const dynamic = "force-static";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: BRAND.name,
    short_name: BRAND.name,
    description: BRAND.description,
    start_url: "/dashboard/",
    scope: "/",
    display: "standalone",
    background_color: "#F7F9FC",
    theme_color: "#2457F5",
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: "/apple-icon.png", sizes: "180x180", type: "image/png" },
    ],
  };
}
