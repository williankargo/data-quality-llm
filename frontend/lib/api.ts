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

export async function apiFetch<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const errData = body?.error ?? {
      code: "INTERNAL_ERROR",
      user_message: "An unexpected error occurred. Please try again.",
      technical_detail: `HTTP ${res.status}`,
    };
    throw new ApiError(errData);
  }
  return res.json();
}
