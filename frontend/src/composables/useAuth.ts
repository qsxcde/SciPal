import { ref } from "vue";
import { getToken, setToken, clearToken, getMe, login as apiLogin, register as apiRegister } from "../api";

const isAuthenticated = ref(false);
const user = ref<{ id: string; username: string } | null>(null);
const loading = ref(true);

export function useAuth() {
  async function checkAuth() {
    const token = getToken();
    if (!token) {
      loading.value = false;
      isAuthenticated.value = false;
      return;
    }
    try {
      user.value = await getMe();
      isAuthenticated.value = true;
    } catch {
      clearToken();
      isAuthenticated.value = false;
    }
    loading.value = false;
  }

  async function loginUser(username: string, password: string): Promise<void> {
    const res = await apiLogin(username, password);
    setToken(res.token);
    user.value = res.user;
    isAuthenticated.value = true;
  }

  async function registerUser(username: string, password: string): Promise<void> {
    const res = await apiRegister(username, password);
    setToken(res.token);
    user.value = res.user;
    isAuthenticated.value = true;
  }

  function logout() {
    clearToken();
    user.value = null;
    isAuthenticated.value = false;
  }

  return {
    isAuthenticated,
    user,
    loading,
    checkAuth,
    loginUser,
    registerUser,
    logout,
  };
}
