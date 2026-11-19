import type { Metadata, Viewport } from "next";
import { Anton, Bricolage_Grotesque, Geist, Geist_Mono, Montserrat, Poppins } from "next/font/google";
import { AuthProvider } from "@/components/auth/auth-provider";
import { ToastProvider } from "@/components/ui/toast";
import { BRAND, siteUrl } from "@/lib/config";
import "./globals.css";

const geistSans = Geist({ subsets: ["latin"], variable: "--font-geist-sans" });
const geistMono = Geist_Mono({ subsets: ["latin"], variable: "--font-geist-mono" });
const bricolage = Bricolage_Grotesque({ subsets: ["latin"], variable: "--font-bricolage", weight: ["500", "600", "700", "800"] });
// Caption fonts: the same families the backend burns into exported clips.
const montserrat = Montserrat({ subsets: ["latin"], weight: "700", variable: "--font-caption-montserrat" });
const poppins = Poppins({ subsets: ["latin"], weight: "700", variable: "--font-caption-poppins" });
const anton = Anton({ subsets: ["latin"], weight: "400", variable: "--font-caption-anton" });

const SITE_URL = siteUrl();
// Search Console / Bing Webmaster Tools ownership tokens (public by design; optional).
const GOOGLE_VERIFICATION = process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION;
const BING_VERIFICATION = process.env.NEXT_PUBLIC_BING_SITE_VERIFICATION;
const VERIFICATION =
  GOOGLE_VERIFICATION || BING_VERIFICATION
    ? {
        ...(GOOGLE_VERIFICATION ? { google: GOOGLE_VERIFICATION } : {}),
        ...(BING_VERIFICATION ? { other: { "msvalidate.01": BING_VERIFICATION } } : {}),
      }
    : undefined;
const SOCIAL_CARD = { url: "/social-card.png", width: 1200, height: 630, alt: `${BRAND.name}: ${BRAND.tagline}` };

export const metadata: Metadata = {
  metadataBase: SITE_URL,
  title: {
    default: BRAND.title,
    template: `%s · ${BRAND.name}`,
  },
  description: BRAND.description,
  applicationName: BRAND.name,
  appleWebApp: { title: BRAND.name, capable: true, statusBarStyle: "default" },
  icons: {
    icon: [{ url: "/icon.svg", type: "image/svg+xml", sizes: "any" }],
    apple: [{ url: "/apple-icon.png", sizes: "180x180", type: "image/png" }],
  },
  openGraph: {
    type: "website",
    siteName: BRAND.name,
    title: BRAND.title,
    description: BRAND.description,
    locale: "en_US",
    ...(SITE_URL ? { url: SITE_URL, images: [SOCIAL_CARD] } : {}),
  },
  twitter: {
    card: SITE_URL ? "summary_large_image" : "summary",
    title: BRAND.title,
    description: BRAND.description,
    ...(SITE_URL ? { images: [SOCIAL_CARD] } : {}),
  },
  // Each public page sets its own canonical URL (lib/seo.ts); none is inherited here.
  robots: { index: true, follow: true },
  ...(VERIFICATION ? { verification: VERIFICATION } : {}),
};

export const viewport: Viewport = {
  themeColor: "#F7F9FC",
  colorScheme: "light",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  const fonts = [geistSans, geistMono, bricolage, montserrat, poppins, anton].map((f) => f.variable).join(" ");
  return (
    <html lang="en" className={fonts}>
      <body className="min-h-dvh">
        <AuthProvider>
          <ToastProvider>{children}</ToastProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
