import type { ApiEnvelope, ApiErrorBody } from "@/types/api";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const ATM_DAEMON_URL =
  process.env.NEXT_PUBLIC_ATM_DAEMON_URL ?? "http://localhost:8100";

/**
 * 로그인 역할. 이 앱은 한 브라우저에서 사용자(어르신)와 상담원 화면을 동시에 띄워
 * 시연하므로, 토큰을 역할마다 따로 저장한다. 하나만 저장하면 나중에 로그인한 쪽이
 * 앞의 로그인을 덮어써서 문자 목록이 비어 버린다.
 */
export type Role = "user" | "agent";

const TOKEN_KEY_PREFIX = "smart-atm-token";
const NAME_KEY_PREFIX = "smart-atm-name";

const tokenKey = (role: Role) => `${TOKEN_KEY_PREFIX}:${role}`;
const nameKey = (role: Role) => `${NAME_KEY_PREFIX}:${role}`;

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

export function saveToken(role: Role, token: string, displayName?: string): void {
  window.localStorage.setItem(tokenKey(role), token);
  if (displayName) window.localStorage.setItem(nameKey(role), displayName);
}

export function readToken(role: Role): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(tokenKey(role));
}

/** 지금 이 역할로 로그인한 사람의 이름 (화면에 표시해 계정을 헷갈리지 않게 한다) */
export function readDisplayName(role: Role): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(nameKey(role));
}

/** 해당 역할만 로그아웃한다. 다른 역할의 로그인은 그대로 유지된다. */
export function clearToken(role: Role): void {
  window.localStorage.removeItem(tokenKey(role));
  window.localStorage.removeItem(nameKey(role));
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return (
    typeof value === "object" &&
    value !== null &&
    "error" in value &&
    typeof (value as ApiErrorBody).error?.message === "string"
  );
}

export interface RequestOptions {
  /** 이 요청에 쓸 토큰의 역할. null이면 토큰을 붙이지 않는다 (로그인, ATM 데몬). */
  role?: Role | null;
  /** 아직 저장하지 않은 토큰을 직접 쓸 때 — 로그인 직후 역할을 확인하는 용도. */
  token?: string;
  baseUrl?: string;
}

async function request<T>(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {},
): Promise<T> {
  const { role = "user", token, baseUrl = API_BASE_URL } = options;
  const headers = new Headers(init.headers);
  if (init.body) headers.set("Content-Type", "application/json");

  const bearer = token ?? (role ? readToken(role) : null);
  if (bearer && baseUrl === API_BASE_URL) {
    headers.set("Authorization", `Bearer ${bearer}`);
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

/** 백엔드(FastAPI) 호출. 역할을 안 주면 사용자(user) 토큰을 쓴다. */
export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, {}, options),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }, options),
};

/** ATM 로컬 데몬 호출 (JWT를 붙이지 않는다) */
export const atmDaemon = {
  get: <T>(path: string) => request<T>(path, {}, { baseUrl: ATM_DAEMON_URL, role: null }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(
      path,
      { method: "POST", body: body ? JSON.stringify(body) : undefined },
      { baseUrl: ATM_DAEMON_URL, role: null },
    ),
};
