import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/lib/seo";

export const dynamic = "force-static";

/** Public pages are crawlable; the signed-in app and the API are not useful in search results. */
export default function robots(): MetadataRoute.Robots {
  const sitemap = absoluteUrl("/sitemap.xml");
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/", "/dashboard/", "/projects/", "/clips/", "/settings/", "/workers/"],
      },
    ],
    ...(sitemap ? { sitemap } : {}),
  };
}
