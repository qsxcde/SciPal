import { createRouter, createWebHashHistory } from "vue-router";
import { useAuth } from "../composables/useAuth";

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: "/",
      name: "chat",
      component: () => import("../layouts/AppLayout.vue"),
      meta: { requiresAuth: true },
    },
    {
      path: "/login",
      name: "login",
      component: () => import("../views/LoginView.vue"),
      meta: { requiresAuth: false },
    },
    { path: "/:pathMatch(.*)*", redirect: { name: "chat" } },
  ],
});

/** 鉴权守卫：首次导航等待 checkAuth 完成，避免刷新后误跳登录页。 */
router.beforeEach(async (to) => {
  const { ensureAuthLoaded, isAuthenticated } = useAuth();
  await ensureAuthLoaded();

  const requiresAuth = to.meta.requiresAuth === true;
  if (requiresAuth && !isAuthenticated.value) {
    return { name: "login" };
  }
  if (!requiresAuth && isAuthenticated.value) {
    return { name: "chat" };
  }
  return true;
});

export default router;
