import type { ApiEnvelope, ApiErrorBody } from "@/types/api";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const ATM_DAEMON_URL =
  process.env.NEXT_PUBLIC_ATM_DAEMON_URL ?? "http://localhost:8100";

const TOKEN_STORAGE_KEY = "smart-atm-token";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export function saveToken(token: string): void {
  window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
}

export function readToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function clearToken(): void {
  window.localStorage.removeItem(TOKEN_STORAGE_KEY);
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as ApiErrorBody).error?.message === "string"
  );
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  baseUrl: string = API_BASE_URL,
): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");

  const token = readToken();
  if (token && baseUrl === API_BASE_URL) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "서버에 연결할 수 없습니다. 연결 상태를 확인해 주세요.");
  }

  const payload: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    if (isErrorBody(payload)) {
      throw new ApiError(response.status, payload.error.code, payload.error.message);
    }
    throw new ApiError(response.status, "UNKNOWN_ERROR", "요청을 처리하지 못했습니다.");
  }

  return (payload as ApiEnvelope<T>).data;
}

/** 백엔드(FastAPI) 호출 */
export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
};

/** 라즈베리파이 ATM 로컬 데몬 호출 (JWT를 붙이지 않는다) */
export const atmDaemon = {
  get: <T>(path: string) => request<T>(path, {}, ATM_DAEMON_URL),
  post: <T>(path: string, body?: unknown) =>
    request<T>(
      path,
      { method: "POST", body: body ? JSON.stringify(body) : undefined },
      ATM_DAEMON_URL,
    ),
};
