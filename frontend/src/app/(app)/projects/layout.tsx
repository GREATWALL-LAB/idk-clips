import type { Metadata } from "next";
import { BRAND } from "@/lib/config";

// A layout with a plain title would stop the root "· IDK Clips" template from reaching
// the pages below it, so it passes the template on.
export const metadata: Metadata = { title: { default: "Projects", template: `%s · ${BRAND.name}` } };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
