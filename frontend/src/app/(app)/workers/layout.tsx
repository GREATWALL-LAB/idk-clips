import type { Metadata } from "next";

export const metadata: Metadata = { title: "Workers" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
