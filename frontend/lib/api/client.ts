import * as Sentry from "@sentry/nextjs";
import { getAccessToken, useAuth } from "@/lib/store/authStore";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : "Request failed");
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

// Normalise a FastAPI `detail` field (string or array of validation errors).
function extractMessage(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d: any) => (d && d.msg ? d.msg : String(d)))
      .join("; ");
  }
  if (detail && typeof detail === "object") {
    return JSON.stringify(detail);
  }
  return "An unexpected error occurred.";
}

export async function apiFetch<T>(
  path: string,
  options: RequestInit = {},
  auth: boolean = true
): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };
  if (auth) {
    const token = getAccessToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });

  if (!res.ok) {
    let detail: unknown = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? body;
    } catch {
      /* ignore parse errors */
    }
    if (res.status === 401) {
      useAuth.getState().logout();
    }
    if (process.env.NEXT_PUBLIC_SENTRY_DSN) {
      // Forward API failures to Sentry (5xx / validation / detail).
      Sentry.captureException(new ApiError(res.status, detail));
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}
