import { ref } from "vue";
import {
  clearToken,
  getMe,
  getToken,
  login as apiLogin,
  register as apiRegister,
  setToken,
} from "../api";
import type { AuthResult, UserSummary } from "../api";

const isAuthenticated = ref(false);
const user = ref<UserSummary | null>(null);
const loading = ref(true);

let authReadyPromise: Promise<void> | null = null;

async function loadAuth(): Promise<void> {
  const token = getToken();
  if (!token) {
    isAuthenticated.value = false;
    loading.value = false;
    return;
  }
  try {
    user.value = await getMe();
    isAuthenticated.value = true;
  } catch {
    clearToken();
    isAuthenticated.value = false;
  } finally {
    loading.value = false;
  }
}

/** 幂等初始化：多个入口（路由守卫、挂载）调用只发一次 /auth/me。 */
function ensureAuthLoaded(): Promise<void> {
  authReadyPromise ??= loadAuth();
  return authReadyPromise;
}

function applyAuthResult(result: AuthResult): void {
  setToken(result.token);
  user.value = result.user;
  isAuthenticated.value = true;
  loading.value = false;
}

export function useAuth() {
  async function loginUser(username: string, password: string): Promise<void> {
    applyAuthResult(await apiLogin(username, password));
  }

  async function registerUser(username: string, password: string): Promise<void> {
    applyAuthResult(await apiRegister(username, password));
  }

  function logout(): void {
    clearToken();
    user.value = null;
    isAuthenticated.value = false;
    authReadyPromise = Promise.resolve();
  }

  return {
    isAuthenticated,
    user,
    loading,
    ensureAuthLoaded,
    loginUser,
    registerUser,
    logout,
  };
}
