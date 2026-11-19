import type { MetadataRoute } from "next";
import { DOCS } from "@/lib/docs";
import { routes } from "@/lib/routes";
import { absoluteUrl } from "@/lib/seo";

export const dynamic = "force-static";

/** Every public page, generated at build time: new docs appear here automatically. */
export default function sitemap(): MetadataRoute.Sitemap {
  const built = new Date();
  const pages: Array<{ path: string; priority: number; changeFrequency: "weekly" | "monthly" }> = [
    { path: routes.home, priority: 1, changeFrequency: "weekly" },
    { path: routes.docs, priority: 0.8, changeFrequency: "weekly" },
    ...DOCS.map((doc) => ({ path: routes.doc(doc.slug), priority: 0.6, changeFrequency: "monthly" as const })),
    { path: routes.privacy, priority: 0.3, changeFrequency: "monthly" },
    { path: routes.terms, priority: 0.3, changeFrequency: "monthly" },
  ];
  return pages.flatMap((page) => {
    const url = absoluteUrl(page.path);
    return url ? [{ url, lastModified: built, changeFrequency: page.changeFrequency, priority: page.priority }] : [];
  });
}
