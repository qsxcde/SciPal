<script setup lang="ts">
import { onMounted } from "vue";
import LoginView from "./views/LoginView.vue";
import AppLayout from "./AppLayout.vue";
import { useAuth } from "./composables/useAuth";

const { isAuthenticated, loading, checkAuth } = useAuth();

onMounted(() => {
  void checkAuth();
});
</script>

<template>
  <div v-if="loading" class="loading-screen">
    <p>加载中...</p>
  </div>
  <LoginView v-else-if="!isAuthenticated" />
  <AppLayout v-else />
</template>

<style scoped>
.loading-screen {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  color: #909399;
}
</style>
