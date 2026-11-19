import { afterEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "@/lib/api/client";

function reply(status: number, body: string) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(status === 204 ? null : body, { status, headers: { "Content-Type": "application/json" } })));
}

afterEach(() => vi.unstubAllGlobals());

describe("apiFetch", () => {
  it("reads the body of 202 Accepted answers (regression: they used to be dropped)", async () => {
    reply(202, JSON.stringify({ resend_after_seconds: 60, code_ttl_minutes: 10 }));
    await expect(apiFetch("/auth/resend-code", { method: "POST", json: {} })).resolves.toEqual({ resend_after_seconds: 60, code_ttl_minutes: 10 });
  });

  it("returns nothing for 204 and for empty bodies", async () => {
    reply(204, "");
    await expect(apiFetch("/auth/logout", { method: "POST" })).resolves.toBeUndefined();
    reply(202, "");
    await expect(apiFetch("/projects/x", { method: "DELETE" })).resolves.toBeUndefined();
  });
});
