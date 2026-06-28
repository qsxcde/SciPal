<script setup lang="ts">
import { ref } from "vue";
import { Expand, Plus } from "@element-plus/icons-vue";
import RenameSessionDialog from "./RenameSessionDialog.vue";
import SessionList from "./SessionList.vue";
import SidebarHeader from "./SidebarHeader.vue";
import type { SessionActionTarget, SidebarSessionItem } from "../types";

const props = defineProps<{
  collapsed: boolean;
  indexedChunks: number;
  isUploading: boolean;
  recentSessions: SidebarSessionItem[];
  username?: string;
}>();

const emit = defineEmits<{
  deleteSession: [sessionId: string];
  newPaper: [];
  pinSession: [sessionId: string];
  renameSession: [sessionId: string, title: string];
  selectSession: [sessionId: string];
  toggleCollapse: [];
  logout: [];
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
    <template v-if="collapsed">
      <div
        class="app-sidebar__collapsed-brand"
        aria-label="SciPal"
      >
        S
      </div>
      <el-button
        class="app-sidebar__collapsed-button"
        :icon="Expand"
        circle
        text
        aria-label="展开侧边栏"
        @click="$emit('toggleCollapse')"
      />
      <el-button
        class="app-sidebar__collapsed-button app-sidebar__collapsed-button--primary"
        :icon="Plus"
        :loading="isUploading"
        :disabled="isUploading"
        circle
        text
        aria-label="新对话 / 上传论文"
        @click="$emit('newPaper')"
      />
    </template>

    <template v-else>
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
        <span v-if="!collapsed">新对话 / 上传论文</span>
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
      <div
        v-if="!collapsed && username"
        class="app-sidebar__user"
      >
        <span class="app-sidebar__user-name">{{ username }}</span>
        <button
          class="app-sidebar__logout"
          @click="$emit('logout')"
        >
          退出
        </button>
      </div>
    </template>
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
  gap: 12px;
  padding: 18px 14px;
  overflow: hidden;
  color: var(--color-text);
  background: rgba(248, 250, 252, 0.95);
}

.app-sidebar--collapsed {
  position: absolute;
  top: 22px;
  left: 22px;
  z-index: 4;
  display: inline-flex;
  width: auto;
  height: auto;
  min-height: 0;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  padding: 7px;
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid rgba(199, 211, 226, 0.92);
  border-radius: 16px;
  box-shadow: 0 14px 36px rgba(47, 69, 103, 0.12);
  backdrop-filter: blur(14px);
}

.app-sidebar__collapsed-brand,
.app-sidebar__collapsed-button.el-button {
  display: grid;
  width: 36px;
  height: 36px;
  place-items: center;
  border-radius: 11px;
}

.app-sidebar__collapsed-brand {
  color: #ffffff;
  font-size: 16px;
  font-weight: 850;
  background: linear-gradient(145deg, #5c7ff0 0%, #244dcc 100%);
  box-shadow: 0 10px 22px rgba(71, 110, 230, 0.2);
}

.app-sidebar__collapsed-button.el-button {
  color: var(--color-text-soft);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}

.app-sidebar__collapsed-button.el-button:hover {
  color: var(--color-accent-strong);
  background: var(--color-accent-soft);
  border-color: var(--color-border-accent);
}

.app-sidebar__collapsed-button--primary.el-button,
.app-sidebar__collapsed-button--primary.el-button:hover {
  color: #ffffff;
  background: linear-gradient(145deg, #5d80ee 0%, #2d55d1 100%);
  border-color: transparent;
}

.app-sidebar__new-session {
  justify-content: flex-start;
  width: 100%;
  height: 40px;
  margin-top: 0;
  padding: 0 13px;
  color: var(--color-text);
  font-size: 13px;
  font-weight: 750;
  background: var(--color-surface);
  border: 1px solid var(--color-border-strong);
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
  font-weight: 850;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.app-sidebar__index-card {
  flex: 0 0 auto;
  padding: 12px;
  background: var(--color-sidebar-soft);
  border: 1px solid var(--color-border);
  border-radius: 13px;
}

.app-sidebar__index-card span {
  display: block;
  color: var(--color-text-soft);
  font-size: 11px;
}

.app-sidebar__index-card strong {
  display: block;
  margin-top: 5px;
  color: var(--color-text);
  font-size: 24px;
  line-height: 1;
}

.app-sidebar__user {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
  color: var(--color-text-soft);
  font-size: 13px;
}

.app-sidebar__user-name {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-sidebar__logout {
  margin-left: auto;
  padding: 5px 9px;
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: 9px;
}

@media (max-width: 1200px) {
  .app-sidebar {
    padding: 16px 12px;
  }
}

@media (max-width: 1100px) {
  .app-sidebar:not(.app-sidebar--collapsed) {
    align-items: center;
    gap: 12px;
    padding: 14px 10px;
  }

  .app-sidebar--collapsed {
    top: 16px;
    left: 16px;
    gap: 6px;
    padding: 6px;
    border-radius: 15px;
  }

  .app-sidebar__collapsed-brand,
  .app-sidebar__collapsed-button.el-button {
    width: 34px;
    height: 34px;
    border-radius: 10px;
  }

  .app-sidebar__new-session,
  .app-sidebar__label,
  .app-sidebar__user,
  .app-sidebar__new-session:not(.app-sidebar__new-session--collapsed) {
    display: none;
  }

  .app-sidebar__index-card {
    width: 52px;
    padding: 9px 6px;
    text-align: center;
  }

  .app-sidebar__index-card span {
    font-size: 11px;
  }

  .app-sidebar__index-card strong {
    font-size: 20px;
  }
}
</style>
