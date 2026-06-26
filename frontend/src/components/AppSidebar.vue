<script setup lang="ts">
import { ref } from "vue";
import { Plus } from "@element-plus/icons-vue";
import RenameSessionDialog from "./RenameSessionDialog.vue";
import SessionList from "./SessionList.vue";
import SidebarHeader from "./SidebarHeader.vue";
import type { SessionActionTarget, SidebarSessionItem } from "../types";

const props = defineProps<{
  collapsed: boolean;
  indexedChunks: number;
  isUploading: boolean;
  recentSessions: SidebarSessionItem[];
}>();

const emit = defineEmits<{
  deleteSession: [sessionId: string];
  newPaper: [];
  pinSession: [sessionId: string];
  renameSession: [sessionId: string, title: string];
  selectSession: [sessionId: string];
  toggleCollapse: [];
}>();

const renameTarget = ref<SessionActionTarget | null>(null);
const isRenameDialogVisible = ref(false);

function openRenameDialog(sessionId: string): void {
  const target = props.recentSessions.find((item) => item.id === sessionId);
  if (!target) {
    return;
  }
  renameTarget.value = { id: target.id, title: target.title };
  isRenameDialogVisible.value = true;
}

function submitRename(title: string): void {
  if (!renameTarget.value) {
    return;
  }
  emit("renameSession", renameTarget.value.id, title);
  renameTarget.value = null;
}

function handleDelete(sessionId: string): void {
  emit("deleteSession", sessionId);
}

function handlePin(sessionId: string): void {
  emit("pinSession", sessionId);
}
</script>

<template>
  <aside
    class="app-sidebar"
    :class="{ 'app-sidebar--collapsed': collapsed }"
    aria-label="最近论文会话"
  >
    <SidebarHeader
      :collapsed="collapsed"
      :is-busy="isUploading"
      @create-session="$emit('newPaper')"
      @toggle-collapse="$emit('toggleCollapse')"
    />

    <el-button
      class="app-sidebar__new-session"
      :class="{ 'app-sidebar__new-session--collapsed': collapsed }"
      :icon="Plus"
      :loading="isUploading"
      :disabled="isUploading"
      :aria-label="collapsed ? '新对话' : undefined"
      @click="$emit('newPaper')"
    >
      <span v-if="!collapsed">新对话</span>
    </el-button>

    <div
      v-if="!collapsed"
      class="app-sidebar__label"
    >
      最近会话
    </div>
    <SessionList
      :collapsed="collapsed"
      :items="recentSessions"
      @delete-session="handleDelete"
      @pin-session="handlePin"
      @rename-session="openRenameDialog"
      @select-session="$emit('selectSession', $event)"
    />

    <div class="app-sidebar__index-card">
      <span>{{ collapsed ? "索引" : "已索引片段" }}</span>
      <strong>{{ indexedChunks }}</strong>
    </div>
  </aside>
  <RenameSessionDialog
    v-model:visible="isRenameDialogVisible"
    :initial-title="renameTarget?.title ?? ''"
    @submit="submitRename"
  />
</template>

<style scoped>
.app-sidebar {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  gap: 13px;
  padding: 18px 15px;
  overflow: hidden;
  color: var(--color-text);
  background: var(--color-sidebar);
}

.app-sidebar--collapsed {
  padding-right: 12px;
  padding-left: 12px;
}

.app-sidebar__new-session {
  justify-content: flex-start;
  width: 100%;
  height: 38px;
  margin-top: 2px;
  color: var(--color-text);
  font-size: 12px;
  font-weight: 800;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  box-shadow: var(--shadow-card);
}

.app-sidebar__new-session--collapsed {
  justify-content: center;
  padding: 0;
}

.app-sidebar__label {
  color: var(--color-text-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.app-sidebar__index-card {
  flex: 0 0 auto;
  padding: 12px;
  background: var(--color-sidebar-soft);
  border: 1px solid var(--color-border);
  border-radius: 15px;
}

.app-sidebar__index-card span {
  display: block;
  color: var(--color-text-soft);
  font-size: 12px;
}

.app-sidebar__index-card strong {
  display: block;
  margin-top: 3px;
  color: var(--color-text);
  font-size: 21px;
  line-height: 1;
}
</style>
