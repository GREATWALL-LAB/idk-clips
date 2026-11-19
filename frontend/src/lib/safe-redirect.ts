/** Only allow same-site relative paths (prevents open redirects like ?next=https://evil.example). */
export function safeNextPath(next: string | null | undefined, fallback = "/dashboard/"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) return fallback;
  if (next.startsWith("/login") || next.startsWith("/register")) return fallback;
  return next;
}
