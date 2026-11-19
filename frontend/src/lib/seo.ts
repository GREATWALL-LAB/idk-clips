import type { Metadata } from "next";
import { BRAND, publicLinks, siteUrl } from "@/lib/config";

/**
 * Search and social metadata. Canonical links, Open Graph URLs, the sitemap and
 * structured data use NEXT_PUBLIC_SITE_URL (the production address). Without it (local
 * builds) no absolute URLs are emitted, so nothing ever points at localhost.
 */
export const SITE_URL = siteUrl();

export function absoluteUrl(path: string): string | undefined {
  return SITE_URL ? new URL(path, SITE_URL).toString() : undefined;
}

export function pageMetadata({
  title,
  description,
  path,
  absoluteTitle = false,
}: {
  title: string;
  description: string;
  path: string;
  absoluteTitle?: boolean;
}): Metadata {
  const fullTitle = absoluteTitle ? title : `${title} · ${BRAND.name}`;
  return {
    title: absoluteTitle ? { absolute: title } : title,
    description,
    ...(SITE_URL ? { alternates: { canonical: path } } : {}),
    openGraph: {
      type: "website",
      siteName: BRAND.name,
      title: fullTitle,
      description,
      ...(SITE_URL ? { url: path } : {}),
    },
    twitter: { title: fullTitle, description },
  };
}

/** Pages behind a login, or with no content of their own: kept out of search results. */
export const NOINDEX: Metadata = { robots: { index: false, follow: false } };

export function softwareApplicationLd(): Record<string, unknown> {
  const github = publicLinks().github;
  return {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: BRAND.name,
    description: BRAND.description,
    applicationCategory: "MultimediaApplication",
    applicationSubCategory: "AI video clipping",
    operatingSystem: "Windows, Linux, macOS",
    softwareVersion: "0.1.0",
    license: "https://opensource.org/licenses/MIT",
    isAccessibleForFree: true,
    offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
    featureList: [
      "Speech transcription with faster-whisper",
      "AI detection of the strongest moments with a local or OpenAI-compatible model",
      "Burned-in, word-by-word captions",
      "Exports in 9:16, 4:5, 1:1 and 16:9",
      "Runs on your own computer or on a self-hosted server",
    ],
    ...(SITE_URL ? { url: SITE_URL.toString() } : {}),
    ...(github ? { sameAs: [github], downloadUrl: github } : {}),
  };
}

export function webSiteLd(): Record<string, unknown> | null {
  if (!SITE_URL) return null;
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: BRAND.name,
    url: SITE_URL.toString(),
    description: BRAND.description,
  };
}

export function techArticleLd(title: string, description: string, path: string): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "TechArticle",
    headline: title,
    description,
    about: { "@type": "SoftwareApplication", name: BRAND.name },
    ...(SITE_URL ? { url: absoluteUrl(path), mainEntityOfPage: absoluteUrl(path) } : {}),
  };
}

export function faqLd(items: ReadonlyArray<{ question: string; answer: string }>): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: items.map((item) => ({
      "@type": "Question",
      name: item.question,
      acceptedAnswer: { "@type": "Answer", text: item.answer },
    })),
  };
}
