import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Clip, Meta } from "@/lib/api/types";
import { headerActions } from "@/lib/header-actions";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  push: vi.fn(),
  params: { current: new URLSearchParams() },
  auth: { current: null as Record<string, unknown> | null },
  api: {
    authStatus: vi.fn(),
    register: vi.fn(),
    login: vi.fn(),
    me: vi.fn(),
    verifyEmail: vi.fn(),
    resendCode: vi.fn(),
    requestPasswordReset: vi.fn(),
    confirmPasswordReset: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push, replace: mocks.replace }),
  usePathname: () => "/",
  useSearchParams: () => mocks.params.current,
}));

vi.mock("@/components/auth/auth-provider", () => ({
  useOptionalAuth: () => mocks.auth.current,
  useAuth: () => mocks.auth.current,
}));

vi.mock("@/lib/api/endpoints", () => ({ api: mocks.api }));

const SERVER_META: Meta = { mode: "hybrid", accounts: true, registration_open: true } as Meta;

function anonymous(meta: Meta | null = SERVER_META) {
  return { status: "anonymous", user: null, error: null, meta, setUser: vi.fn(), refresh: vi.fn(), signOut: vi.fn() };
}

beforeEach(() => {
  mocks.replace.mockReset();
  mocks.push.mockReset();
  mocks.params.current = new URLSearchParams();
  window.sessionStorage.clear();
  for (const fn of Object.values(mocks.api)) fn.mockReset();
  mocks.auth.current = anonymous();
});

// ------------------------------------------------------------ header logic
describe("header account buttons", () => {
  it("offers Log in and Create account to visitors", () => {
    expect(headerActions("anonymous", SERVER_META).map((a) => [a.label, a.href])).toEqual([
      ["Log in", "/login/"],
      ["Create account", "/register/"],
    ]);
  });

  it("shows both while the API has not answered yet", () => {
    expect(headerActions("loading", null).map((a) => a.label)).toEqual(["Log in", "Create account"]);
    expect(headerActions("offline", null).map((a) => a.label)).toEqual(["Log in", "Create account"]);
  });

  it("hides Create account when the server closed sign-ups", () => {
    expect(headerActions("anonymous", { ...SERVER_META, registration_open: false }).map((a) => a.label)).toEqual(["Log in"]);
  });

  it("sends signed-in users to their dashboard", () => {
    expect(headerActions("authenticated", SERVER_META)).toEqual([
      { key: "dashboard", href: "/dashboard/", label: "Dashboard", variant: "primary" },
    ]);
  });

  it("has no account buttons in local mode", () => {
    const local = { mode: "local", accounts: false, registration_open: false } as Meta;
    expect(headerActions("authenticated", local).map((a) => a.label)).toEqual(["Open app"]);
  });
});

describe("site header", () => {
  it("renders Log in and Create account in the bar and in the mobile menu", async () => {
    const { SiteHeader } = await import("@/components/home/site-header");
    render(<SiteHeader />);
    const bar = screen.getByTestId("header-actions");
    const login = within(bar).getAllByRole("link", { name: "Log in" });
    // (next/link drops the trailing slash in the test environment)
    expect(login.map((link) => link.getAttribute("href"))).toEqual(["/login", "/login"]);
    expect(within(bar).getByRole("link", { name: "Create account" }).getAttribute("href")).toMatch(/^\/register\/?$/);

    fireEvent.click(screen.getByRole("button", { name: "Open menu" }));
    const menu = document.getElementById("site-menu")!;
    expect(within(menu).getByRole("link", { name: "Log in" }).getAttribute("href")).toMatch(/^\/login\/?$/);
    expect(within(menu).getByRole("link", { name: "Create account" }).getAttribute("href")).toMatch(/^\/register\/?$/);
  });

  it("works on static pages without an auth provider", async () => {
    mocks.auth.current = null;
    const { SiteHeader } = await import("@/components/home/site-header");
    render(<SiteHeader />);
    expect(within(screen.getByTestId("header-actions")).getByRole("link", { name: "Create account" })).toBeTruthy();
  });

  it("carries the IDK Clips name", async () => {
    const { SiteHeader } = await import("@/components/home/site-header");
    const { container } = render(<SiteHeader />);
    expect(screen.getByRole("link", { name: "IDK Clips home" })).toBeTruthy();
    expect(container.textContent).toContain("IDK Clips");
    expect(container.textContent).not.toMatch(/openclip/i);
  });
});

// ---------------------------------------------------------- registration
const OPEN = { has_users: true, registration_open: true, email_verification: true, mode: "hybrid", accounts: true };

async function renderRegister() {
  const { default: RegisterPage } = await import("@/app/(auth)/register/page");
  return render(<RegisterPage />);
}

describe("registration page", () => {
  it("asks the 18+ question first, with nothing pre-selected", async () => {
    mocks.api.authStatus.mockResolvedValue(OPEN);
    const { container } = await renderRegister();
    expect(await screen.findByText("Are you 18 years of age or older?")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Yes, I am 18 or older" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "No" })).toBeTruthy();
    expect(screen.queryByLabelText("Email")).toBeNull(); // no form before the answer
    expect(container.querySelector("input[type=checkbox]:checked")).toBeNull();
    expect(container.textContent).not.toMatch(/administrator|admin/i);
  });

  it("answering No blocks sign-up for this browser session", async () => {
    mocks.api.authStatus.mockResolvedValue(OPEN);
    await renderRegister();
    fireEvent.click(await screen.findByRole("button", { name: "No" }));
    expect(screen.getByRole("heading", { name: "You must be 18 or older" })).toBeTruthy();
    expect(screen.queryByLabelText("Email")).toBeNull();
    expect(mocks.api.register).not.toHaveBeenCalled();
    // Opening the page again does not bring the form back.
    const again = await renderRegister();
    expect(await within(again.container).findByRole("heading", { name: "You must be 18 or older" })).toBeTruthy();
  });

  it("after Yes, sends the answer with the form and goes to code entry", async () => {
    mocks.api.authStatus.mockResolvedValue(OPEN);
    mocks.api.register.mockResolvedValue({
      user: { id: "u1", email: "new@example.com", display_name: "New", created_at: "", email_verified: false, age_confirmed: true },
      verification_required: true,
      code_sent: true,
      resend_after_seconds: 60,
      code_ttl_minutes: 10,
    });
    await renderRegister();
    fireEvent.click(await screen.findByRole("button", { name: "Yes, I am 18 or older" }));
    await screen.findByRole("heading", { name: "Create your account" });
    expect(document.body.querySelector("select, [name='role'], [name='is_admin']")).toBeNull();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "New" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a-long-password" } });
    fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "a-long-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Create account" }));
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/verify/?email=new%40example.com&sent=1"));
    expect(mocks.api.register).toHaveBeenCalledWith("new@example.com", "a-long-password", "New", true);
    expect(mocks.api.me).not.toHaveBeenCalled(); // no session before verification
  });

  it("explains when sign-ups are closed because verification is not set up", async () => {
    mocks.api.authStatus.mockResolvedValue({ ...OPEN, registration_open: false });
    await renderRegister();
    expect(await screen.findByRole("heading", { name: "Sign-ups are closed" })).toBeTruthy();
    expect(screen.getByText(/email verification is not set up/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Create account" })).toBeNull();
  });
});

describe("log-in page", () => {
  async function renderLogin() {
    mocks.api.authStatus.mockResolvedValue(OPEN);
    const { default: LoginPage } = await import("@/app/(auth)/login/page");
    render(<LoginPage />);
    fireEvent.change(await screen.findByLabelText("Email"), { target: { value: "old@example.com" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "a-long-password" } });
  }

  it("does not push visitors of an empty server into a setup flow", async () => {
    mocks.api.authStatus.mockResolvedValue({ ...OPEN, has_users: false });
    const { default: LoginPage } = await import("@/app/(auth)/login/page");
    render(<LoginPage />);
    expect(await screen.findByRole("link", { name: "Create account" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Log in" })).toBeTruthy();
    expect(mocks.replace).not.toHaveBeenCalled();
  });

  it("asks older accounts the 18+ question, then logs in with the answer", async () => {
    const { ApiError } = await import("@/lib/api/client");
    mocks.api.login.mockRejectedValueOnce(new ApiError(403, "age_confirmation_required", "Please confirm"));
    mocks.api.login.mockResolvedValueOnce({});
    mocks.api.me.mockResolvedValue({ id: "u1", email: "old@example.com" });
    await renderLogin();
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    fireEvent.click(await screen.findByRole("button", { name: "Yes, I am 18 or older" }));
    await waitFor(() => expect(mocks.api.login).toHaveBeenLastCalledWith("old@example.com", "a-long-password", true));
  });

  it("sends unverified accounts to code entry", async () => {
    const { ApiError } = await import("@/lib/api/client");
    mocks.api.login.mockRejectedValueOnce(new ApiError(403, "email_not_verified", "Verify your email"));
    await renderLogin();
    fireEvent.click(screen.getByRole("button", { name: "Log in" }));
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/verify/?email=old%40example.com&sent=1"));
    expect(mocks.api.me).not.toHaveBeenCalled();
  });
});

describe("code entry page", () => {
  async function renderVerify(query: string) {
    mocks.params.current = new URLSearchParams(query);
    const { default: VerifyPage } = await import("@/app/(auth)/verify/page");
    render(<VerifyPage />);
  }

  it("verifies the code with the server and opens the dashboard", async () => {
    mocks.api.verifyEmail.mockResolvedValue({ id: "u1", email: "new@example.com", email_verified: true });
    await renderVerify("email=new%40example.com&sent=1");
    const button = screen.getByRole("button", { name: "Verify and continue" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Verification code"), { target: { value: "12 34-56" } });
    expect((screen.getByLabelText("Verification code") as HTMLInputElement).value).toBe("123456");
    fireEvent.click(button);
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/dashboard/"));
    expect(mocks.api.verifyEmail).toHaveBeenCalledWith("new@example.com", "123456");
  });

  it("waits 60 seconds before a new code can be requested", async () => {
    await renderVerify("email=new%40example.com&sent=1");
    const resend = screen.getByRole("button", { name: /Send a new code in 60s/ }) as HTMLButtonElement;
    expect(resend.disabled).toBe(true);
    expect(mocks.api.resendCode).not.toHaveBeenCalled();
  });

  it("shows the server's message for a wrong code", async () => {
    const { ApiError } = await import("@/lib/api/client");
    mocks.api.verifyEmail.mockRejectedValue(new ApiError(422, "invalid_code", "That code is not correct. 4 attempt(s) left."));
    await renderVerify("email=new%40example.com");
    fireEvent.change(screen.getByLabelText("Verification code"), { target: { value: "000000" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify and continue" }));
    expect(await screen.findByText(/4 attempt\(s\) left/)).toBeTruthy();
    expect(mocks.replace).not.toHaveBeenCalled();
  });
});

describe("password reset page", () => {
  it("asks for a code, then sets the new password and returns to log in", async () => {
    mocks.api.requestPasswordReset.mockResolvedValue({ resend_after_seconds: 60, code_ttl_minutes: 10 });
    mocks.api.confirmPasswordReset.mockResolvedValue(undefined);
    const { default: ForgotPasswordPage } = await import("@/app/(auth)/forgot-password/page");
    render(<ForgotPasswordPage />);
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "old@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Email me a code" }));
    await screen.findByLabelText("Reset code");
    expect(mocks.api.requestPasswordReset).toHaveBeenCalledWith("old@example.com");
    expect((screen.getByRole("button", { name: /Send a new code in 60s/ }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Reset code"), { target: { value: "123456" } });
    fireEvent.change(screen.getByLabelText("New password"), { target: { value: "a-brand-new-password" } });
    fireEvent.change(screen.getByLabelText("Confirm new password"), { target: { value: "a-brand-new-password" } });
    fireEvent.click(screen.getByRole("button", { name: "Set new password" }));
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/login/?reset=1"));
    expect(mocks.api.confirmPasswordReset).toHaveBeenCalledWith("old@example.com", "123456", "a-brand-new-password");
  });
});

// ---------------------------------------------------------- preview dialog
function exportedClip(aspect_ratio: Clip["aspect_ratio"]): Clip {
  return {
    id: "c1",
    project_id: "p1",
    title: "A clip",
    aspect_ratio,
    status: "ready",
    rendered_at: "2026-11-18T00:00:00Z",
    preview_url: "/clips/c1/file",
    download_url: "/clips/c1/file?download=true",
  } as Clip;
}

describe("clip preview dialog", () => {
  it.each(["16:9", "1:1"] as const)("gives %s clips the wide dialog and a full-width player", async (ratio) => {
    const { ClipPreviewDialog } = await import("@/components/clips/clip-card");
    render(<ClipPreviewDialog clip={exportedClip(ratio)} media={{ kind: "server" }} open onClose={() => undefined} />);
    const video = screen.getByTestId("clip-preview-video");
    expect(video.classList.contains("w-full")).toBe(true);
    expect(video.classList.contains("max-w-full")).toBe(true);
    expect(video.closest("dialog")!.className).toContain("max-w-3xl");
    // jsdom has no showModal, so the dialog's content counts as hidden for role queries.
    expect(screen.getByRole("link", { name: `Download MP4 · ${ratio}`, hidden: true }).getAttribute("href")).toBe("/api/v1/clips/c1/file?download=true");
  });

  it.each(["9:16", "4:5"] as const)("keeps %s clips in the narrow dialog, limited by height", async (ratio) => {
    const { ClipPreviewDialog } = await import("@/components/clips/clip-card");
    render(<ClipPreviewDialog clip={exportedClip(ratio)} media={{ kind: "server" }} open onClose={() => undefined} />);
    const video = screen.getByTestId("clip-preview-video");
    expect(video.classList.contains("w-full")).toBe(false);
    expect(video.classList.contains("max-w-full")).toBe(true);
    expect(video.closest("dialog")!.className).toContain("max-w-md");
    expect(screen.getByRole("link", { name: `Download MP4 · ${ratio}`, hidden: true })).toBeTruthy();
  });
});
