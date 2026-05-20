const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  code: string;
  user_message: string;
  technical_detail: string;

  constructor(data: { code: string; user_message: string; technical_detail: string }) {
    super(data.user_message);
    this.code = data.code;
    this.user_message = data.user_message;
    this.technical_detail = data.technical_detail;
  }
}

interface FetchOptions {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
}

export async function apiFetch<T = unknown>(path: string, options?: FetchOptions): Promise<T> {
  const { method = "GET", body } = options ?? {};
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const bodyData = await res.json().catch(() => null);
    const errData = bodyData?.error ?? {
      code: "INTERNAL_ERROR",
      user_message: "An unexpected error occurred. Please try again.",
      technical_detail: `HTTP ${res.status}`,
    };
    throw new ApiError(errData);
  }
  if (res.status === 204) return {} as T;
  return res.json();
}
