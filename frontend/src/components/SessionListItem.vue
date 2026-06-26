<script setup lang="ts">
import {
  ChatDotRound,
  ChatLineRound,
  CollectionTag,
  MoreFilled,
} from "@element-plus/icons-vue";
import SessionActionsMenu from "./SessionActionsMenu.vue";

const props = defineProps<{
  active?: boolean;
  collapsed?: boolean;
  description: string;
  id: string;
  isPinned?: boolean;
  title: string;
}>();

const emit = defineEmits<{
  delete: [sessionId: string];
  pin: [sessionId: string];
  rename: [sessionId: string];
  select: [sessionId: string];
}>();

function handleSelect(): void {
  emit("select", props.id);
}

function handleDelete(): void {
  emit("delete", props.id);
}

function handlePin(): void {
  emit("pin", props.id);
}

function handleRename(): void {
  emit("rename", props.id);
}
</script>

<template>
  <div
    class="session-item"
    :class="{
      'session-item--active': active,
      'session-item--collapsed': collapsed,
      'session-item--pinned': isPinned,
    }"
  >
    <button
      class="session-item__main"
      :aria-label="title"
      type="button"
      @click="handleSelect"
    >
      <span class="session-item__icon">
        <el-icon>
          <component :is="active ? ChatDotRound : ChatLineRound" />
        </el-icon>
      </span>
      <div
        v-if="!collapsed"
        class="session-item__content"
      >
        <span class="session-item__title">{{ title }}</span>
        <small>{{ description }}</small>
      </div>
    </button>
    <span
      v-if="!collapsed && isPinned"
      class="session-item__pin"
      aria-hidden="true"
    >
      <el-icon><CollectionTag /></el-icon>
    </span>
    <SessionActionsMenu
      v-if="!collapsed"
      :is-pinned="Boolean(isPinned)"
      @delete="handleDelete"
      @pin="handlePin"
      @rename="handleRename"
    >
      <el-button
        :icon="MoreFilled"
        circle
        text
        class="session-item__menu"
        aria-label="会话操作"
      />
    </SessionActionsMenu>
  </div>
</template>

<style scoped>
.session-item {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  color: var(--color-text);
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(217, 226, 238, 0.84);
  border-radius: 12px;
  transition: background-color 0.2s ease, border-color 0.2s ease;
}

.session-item--active {
  background: var(--color-accent-soft);
  border-color: var(--color-border-accent);
}

.session-item--pinned {
  border-color: rgba(123, 147, 232, 0.34);
}

.session-item--collapsed {
  justify-content: center;
  padding: 4px 0;
}

.session-item__main {
  display: flex;
  min-width: 0;
  flex: 1;
  align-items: center;
  gap: 10px;
  padding: 10px;
  color: inherit;
  text-align: left;
  background: transparent;
  border: 0;
}

.session-item--collapsed .session-item__main {
  justify-content: center;
}

.session-item__icon {
  display: grid;
  width: 20px;
  height: 20px;
  flex: 0 0 auto;
  place-items: center;
  color: var(--color-accent-strong);
  font-size: 16px;
}

.session-item__content {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 3px;
}

.session-item__title {
  overflow: hidden;
  font-size: 12px;
  line-height: 1.25;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-item__content small {
  color: var(--color-text-muted);
  font-size: 11px;
}

.session-item__pin {
  display: grid;
  width: 20px;
  height: 20px;
  margin-right: -2px;
  place-items: center;
  color: var(--color-accent-strong);
  font-size: 12px;
}

.session-item__menu {
  flex: 0 0 auto;
  margin-right: 4px;
  color: var(--color-text-soft);
}
</style>
