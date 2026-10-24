<script setup lang="ts">
import { RouterView } from "vue-router";
import { useAuth } from "./composables/useAuth";

const { loading } = useAuth();
</script>

<template>
  <div v-if="loading" class="loading-screen">
    <p>加载中...</p>
  </div>
  <RouterView v-else />
</template>

<style scoped>
.loading-screen {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  color: var(--color-text-muted);
}
</style>
