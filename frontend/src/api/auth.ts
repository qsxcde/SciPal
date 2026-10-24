import { jsonRequest, requestJson } from "./client";
import type { AuthResult, UserSummary } from "./types";

export function register(username: string, password: string): Promise<AuthResult> {
  return requestJson<AuthResult>("/auth/register", "注册失败", {
    method: "POST",
    ...jsonRequest({ username, password }),
  });
}

export function login(username: string, password: string): Promise<AuthResult> {
  return requestJson<AuthResult>("/auth/login", "登录失败", {
    method: "POST",
    ...jsonRequest({ username, password }),
  });
}

export function getMe(): Promise<UserSummary> {
  return requestJson<UserSummary>("/auth/me", "获取用户信息失败");
}
