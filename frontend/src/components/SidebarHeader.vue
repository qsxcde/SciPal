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
  gap: 10px;
}

.sidebar-header__brand {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 9px;
}

.sidebar-header__brand--collapsed {
  justify-content: center;
}

.sidebar-header__mark {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  color: #ffffff;
  font-size: 16px;
  font-weight: 900;
  background: linear-gradient(145deg, #5c7ff0 0%, #244dcc 100%);
  border-radius: 11px;
  box-shadow: 0 12px 24px rgba(71, 110, 230, 0.22);
}

.sidebar-header__copy {
  min-width: 0;
}

.sidebar-header__copy h1 {
  color: var(--color-text);
  font-size: 17px;
  font-weight: 850;
  line-height: 1.1;
}

.sidebar-header__copy p {
  margin-top: 3px;
  color: var(--color-text-soft);
  font-size: 11px;
  font-weight: 650;
}

.sidebar-header__actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sidebar-header__actions :deep(.el-button) {
  color: var(--color-text-soft);
}

.sidebar-header__actions--collapsed {
  flex-direction: column;
}

@media (max-width: 1200px) {
  .sidebar-header__copy h1 {
    font-size: 16px;
  }

  .sidebar-header__actions {
    gap: 4px;
  }
}

@media (max-width: 1100px) {
  .sidebar-header {
    justify-content: center;
  }

  .sidebar-header__brand {
    flex-direction: column;
    gap: 8px;
  }

  .sidebar-header__copy,
  .sidebar-header__actions {
    display: none;
  }
}
</style>
