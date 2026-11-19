import { API_V1, CSRF_HEADER } from "@/lib/config";

/** An error returned by the backend (or a network failure), ready to show to users. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;
  readonly details?: Array<{ field?: string; message: string }>;

  constructor(
    status: number,
    code: string,
    message: string,
    requestId?: string,
    details?: Array<{ field?: string; message: string }>,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

type ErrorEnvelope = {
  error?: {
    code?: string;
    message?: string;
    request_id?: string;
    details?: Array<{ field?: string; message: string }>;
  };
};

export type ApiRequestInit = Omit<RequestInit, "body"> & { timeoutMs?: number; json?: unknown };

/** Absolute backend URL for a path under /api/v1 (used for <video>, <img> and downloads). */
export function apiUrl(path: string): string {
  return `${API_V1}${path}`;
}

export async function toApiError(response: Response): Promise<ApiError> {
  let body: ErrorEnvelope | undefined;
  try {
    body = (await response.json()) as ErrorEnvelope;
  } catch {
    body = undefined;
  }
  const error = body?.error;
  let message = error?.message ?? `The server responded with status ${response.status}.`;
  if (error?.code === "validation_error" && error.details?.length) {
    message = error.details.map((d) => d.message).join(" ");
  }
  return new ApiError(
    response.status,
    error?.code ?? "http_error",
    message,
    error?.request_id ?? response.headers.get("x-request-id") ?? undefined,
    error?.details,
  );
}

export const NETWORK_ERROR_MESSAGE =
  "Cannot reach the IDK Clips backend. Make sure it is running and NEXT_PUBLIC_API_URL is correct.";

/**
 * Fetch JSON from the backend with a timeout, the session cookie and the CSRF header.
 * Network failures become ApiError("network_error") with a helpful message.
 */
export async function apiFetch<T>(path: string, init: ApiRequestInit = {}): Promise<T> {
  const { timeoutMs = 20_000, signal: externalSignal, headers, json, ...rest } = init;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(new DOMException("timeout", "TimeoutError")), timeoutMs);
  const onExternalAbort = () => controller.abort(externalSignal?.reason);
  externalSignal?.addEventListener("abort", onExternalAbort, { once: true });

  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      ...rest,
      body: json === undefined ? undefined : JSON.stringify(json),
      credentials: "include",
      signal: controller.signal,
      headers: {
        Accept: "application/json",
        ...CSRF_HEADER,
        ...(json === undefined ? {} : { "Content-Type": "application/json" }),
        ...headers,
      },
    });
  } catch (cause) {
    if (externalSignal?.aborted) throw cause;
    if (controller.signal.aborted) {
      throw new ApiError(0, "timeout", "The backend did not respond in time. Please try again.");
    }
    throw new ApiError(0, "network_error", NETWORK_ERROR_MESSAGE);
  } finally {
    clearTimeout(timer);
    externalSignal?.removeEventListener("abort", onExternalAbort);
  }

  if (!response.ok) {
    const error = await toApiError(response);
    if (error.status === 401 && typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("openclip:unauthorized"));
    }
    throw error;
  }
  if (response.status === 204) return undefined as T;
  // 202 Accepted can carry a body (code timers, queued jobs); only an empty body is "nothing".
  const text = await response.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

/** Human-friendly message for any thrown value. */
export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}
