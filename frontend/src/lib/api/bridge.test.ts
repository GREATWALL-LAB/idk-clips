import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const transferToken = vi.fn();
vi.mock("@/lib/api/endpoints", () => ({ api: { transferToken: (...args: unknown[]) => transferToken(...args) } }));

const { bridgeOrigin, bridgeUrls, clearReadAccess, probeBridge, readAccess, uploadToWorker } = await import("@/lib/api/bridge");
const { mediaUrls } = await import("@/lib/hooks/use-media");

const WORKER = "11111111-1111-4111-8111-111111111111";
const PROJECT = "22222222-2222-4222-8222-222222222222";
const CLIP = "33333333-3333-4333-8333-333333333333";

function token(minutes: number, value = "oct_secret+/=") {
  return { token: value, scope: "read", expires_at: new Date(Date.now() + minutes * 60_000).toISOString(), worker_id: WORKER, bridge_port: 8787 };
}

beforeEach(() => {
  clearReadAccess();
  transferToken.mockReset();
});

afterEach(() => vi.unstubAllGlobals());

describe("worker bridge", () => {
  it("always targets the loopback address", () => {
    expect(bridgeOrigin(8787)).toBe("http://127.0.0.1:8787");
  });

  it("reuses a read token until shortly before it expires", async () => {
    transferToken.mockResolvedValue(token(30));
    const first = await readAccess(WORKER);
    const second = await readAccess(WORKER);
    expect(first).toEqual(second);
    expect(transferToken).toHaveBeenCalledTimes(1);
    expect(transferToken).toHaveBeenCalledWith(WORKER, { scope: "read" });

    clearReadAccess();
    transferToken.mockResolvedValueOnce(token(0.5, "oct_old")).mockResolvedValueOnce(token(30, "oct_new"));
    await readAccess(WORKER);
    const renewed = await readAccess(WORKER); // the first token expires within the safety margin
    expect(renewed.token).toBe("oct_new");
  });

  it("does not cache failures", async () => {
    transferToken.mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce(token(30));
    await expect(readAccess(WORKER)).rejects.toThrow("offline");
    await expect(readAccess(WORKER)).resolves.toMatchObject({ origin: "http://127.0.0.1:8787" });
  });

  it("encodes tokens in media URLs", async () => {
    transferToken.mockResolvedValue(token(30));
    const access = await readAccess(WORKER);
    const url = new URL(bridgeUrls.clipFile(access, { id: CLIP, project_id: PROJECT, title: "My clip" }, true));
    expect(url.origin).toBe("http://127.0.0.1:8787");
    expect(url.pathname).toBe(`/bridge/v1/projects/${PROJECT}/clips/${CLIP}/file`);
    expect(url.searchParams.get("token")).toBe("oct_secret+/=");
    expect(url.searchParams.get("download")).toBe("true");
    expect(url.searchParams.get("name")).toBe("My clip");
  });

  it("recognises only its own worker on this computer", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ worker_id: WORKER })));
    expect(await probeBridge(8787, WORKER)).toBe(true);
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({ worker_id: "someone-else" })));
    expect(await probeBridge(8787, WORKER)).toBe(false);
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    expect(await probeBridge(8787, WORKER)).toBe(false);
    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8787/bridge/v1/hello");
  });

  it("uploads straight to the worker with an upload token", async () => {
    transferToken.mockResolvedValue({ ...token(30, "oct_upload"), scope: "upload" });
    const sent: Array<{ method: string; url: string; headers: Record<string, string>; body: unknown }> = [];
    class FakeXHR {
      upload: { onprogress: ((e: { lengthComputable: boolean; loaded: number; total: number }) => void) | null } = { onprogress: null };
      status = 0;
      response: unknown = null;
      responseType = "";
      onload: (() => void) | null = null;
      onerror: (() => void) | null = null;
      onabort: (() => void) | null = null;
      private request = { method: "", url: "", headers: {} as Record<string, string>, body: null as unknown };
      open(method: string, url: string) {
        this.request.method = method;
        this.request.url = url;
      }
      setRequestHeader(name: string, value: string) {
        this.request.headers[name] = value;
      }
      send(body: unknown) {
        this.request.body = body;
        sent.push(this.request);
        this.upload.onprogress?.({ lengthComputable: true, loaded: 5, total: 10 });
        this.status = 200;
        this.response = { ok: true };
        this.onload?.();
      }
      abort() {
        this.onabort?.();
      }
    }
    vi.stubGlobal("XMLHttpRequest", FakeXHR);
    const progress: number[] = [];
    const file = new File(["video"], "talk.mp4", { type: "video/mp4" });
    await uploadToWorker(WORKER, PROJECT, file, (p) => progress.push(p.loaded)).promise;
    expect(transferToken).toHaveBeenCalledWith(WORKER, { scope: "upload", project_id: PROJECT });
    expect(sent[0].method).toBe("PUT");
    expect(sent[0].url).toBe(`http://127.0.0.1:8787/bridge/v1/projects/${PROJECT}/media?filename=talk.mp4`);
    expect(sent[0].headers.Authorization).toBe("Bearer oct_upload");
    expect(sent[0].body).toBe(file);
    expect(progress).toEqual([5]);
  });
});

describe("media URLs", () => {
  const project = {
    id: PROJECT,
    has_media: true,
    media_url: `/projects/${PROJECT}/media`,
    thumbnail_url: `/projects/${PROJECT}/thumbnail`,
  } as never;
  const clip = {
    id: CLIP,
    project_id: PROJECT,
    title: "Clip",
    preview_url: `/clips/${CLIP}/file`,
    download_url: `/clips/${CLIP}/file?download=true`,
    thumbnail_url: `/clips/${CLIP}/thumbnail`,
    rendered_at: "2026-11-17T10:00:00Z",
  } as never;

  it("come from the API in local and server mode", () => {
    expect(mediaUrls.projectVideo(project, { kind: "server" })).toMatch(new RegExp(`/api/v1/projects/${PROJECT}/media$`));
    expect(mediaUrls.clipDownload(clip, { kind: "server" })).toMatch(/\/api\/v1\/clips\/.+\/file\?download=true$/);
  });

  it("come from the worker's bridge in hybrid mode", () => {
    const access = { origin: "http://127.0.0.1:8787", token: "oct_t", expiresAt: Date.now() + 60_000 };
    const video = mediaUrls.projectVideo(project, { kind: "worker", access }) ?? "";
    expect(video.startsWith(`http://127.0.0.1:8787/bridge/v1/projects/${PROJECT}/media?token=oct_t`)).toBe(true);
    expect(mediaUrls.clipVideo(clip, { kind: "worker", access })).toContain(`/clips/${CLIP}/file?token=oct_t`);
  });

  it("are not offered when the worker is on another computer", () => {
    const elsewhere = { kind: "elsewhere", message: "On your worker" } as const;
    expect(mediaUrls.projectVideo(project, elsewhere)).toBeNull();
    expect(mediaUrls.clipDownload(clip, elsewhere)).toBeNull();
    expect(mediaUrls.clipThumbnail(clip, elsewhere)).toBeNull();
  });
});
