<script setup lang="ts">
import { EditPen, Expand, Fold } from "@element-plus/icons-vue";

defineProps<{
  collapsed: boolean;
  isBusy: boolean;
}>();

defineEmits<{
  createSession: [];
  toggleCollapse: [];
}>();
</script>

<template>
  <div class="sidebar-header">
    <div
      class="sidebar-header__brand"
      :class="{ 'sidebar-header__brand--collapsed': collapsed }"
    >
      <div class="sidebar-header__mark">
        S
      </div>
      <div
        v-if="!collapsed"
        class="sidebar-header__copy"
      >
        <h1>SciPal</h1>
        <p>论文智能助手</p>
      </div>
    </div>
    <div
      class="sidebar-header__actions"
      :class="{ 'sidebar-header__actions--collapsed': collapsed }"
    >
      <el-button
        :icon="collapsed ? Expand : Fold"
        circle
        text
        aria-label="切换侧边栏"
        @click="$emit('toggleCollapse')"
      />
      <el-button
        :icon="EditPen"
        circle
        text
        :disabled="isBusy"
        aria-label="新建会话"
        @click="$emit('createSession')"
      />
    </div>
  </div>
</template>

<style scoped>
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.sidebar-header__brand {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
}

.sidebar-header__brand--collapsed {
  justify-content: center;
}

.sidebar-header__mark {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  color: var(--color-sidebar);
  font-size: 15px;
  font-weight: 900;
  background: var(--color-accent);
  border-radius: 12px;
}

.sidebar-header__copy {
  min-width: 0;
}

.sidebar-header__copy h1 {
  color: var(--color-text);
  font-size: 15px;
  font-weight: 800;
  line-height: 1.1;
}

.sidebar-header__copy p {
  margin-top: 2px;
  color: var(--color-text-soft);
  font-size: 11px;
}

.sidebar-header__actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.sidebar-header__actions :deep(.el-button) {
  color: var(--color-text-soft);
}

.sidebar-header__actions--collapsed {
  flex-direction: column;
}
</style>
