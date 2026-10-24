/**
 * HTTP 基础设施：base url、token、统一错误处理与 JSON 请求封装。
 * 业务端点一律放在 auth.ts / sessions.ts / chat.ts，不在此文件内。
 */

/** 留空即走同源相对路径（开发期由 vite proxy 转发，生产由反向代理转发）。 */
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const TOKEN_KEY = "scipal_token";

export type HttpMethod = "DELETE" | "GET" | "PATCH" | "POST";

export type RequestOptions = {
  body?: BodyInit | null;
  headers?: HeadersInit;
  method?: HttpMethod;
};

type ApiErrorResponse = {
  detail?: string;
};

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function readError(res: Response, fallback: string): Promise<Error> {
  const payload = (await res.json().catch(() => ({}))) as ApiErrorResponse;
  return new Error(payload.detail ?? fallback);
}

function buildHeaders(options: RequestOptions): HeadersInit {
  return { ...authHeaders(), ...options.headers };
}

export async function requestJson<T>(
  path: string,
  fallback: string,
  options: RequestOptions = {},
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers: buildHeaders(options) });
  if (!res.ok) {
    throw await readError(res, fallback);
  }
  return (await res.json()) as T;
}

export async function requestVoid(
  path: string,
  fallback: string,
  options: RequestOptions = {},
): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers: buildHeaders(options) });
  if (!res.ok) {
    throw await readError(res, fallback);
  }
}

export type JsonRequestPayload = {
  headers: Record<string, string>;
  body: string;
};

/** 发送 JSON 请求体：合并 Content-Type 与序列化，避免每个端点重复写法。 */
export function jsonRequest(payload: unknown): JsonRequestPayload {
  return {
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  };
}

/** 以流式方式打开响应，非 2xx 时抛出后端 detail。 */
export async function openStream(
  path: string,
  init: { body?: BodyInit; method?: HttpMethod; signal?: AbortSignal },
  fallback: string,
): Promise<ReadableStream<Uint8Array>> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: init.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...authHeaders(),
    },
    body: init.body,
    signal: init.signal,
  });
  if (!res.ok) {
    throw await readError(res, fallback);
  }
  if (!res.body) {
    throw new Error("后端没有返回可读取的流式响应");
  }
  return res.body;
}
