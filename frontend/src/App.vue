<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import AppSidebar from "./components/AppSidebar.vue";
import ChatWorkspace from "./components/ChatWorkspace.vue";
import { usePaperChat } from "./composables/usePaperChat";
import type { SidebarSessionItem, SuggestedPrompt } from "./types";

const {
  currentPaperHint,
  currentSessionTitle,
  draft,
  errorMessage,
  hasPaper,
  indexedChunks,
  isStreaming,
  isUploading,
  uploadStatus,
  messages,
  sessions,
  createEmptySession,
  deleteSession,
  handleUpload,
  initializeSessions,
  openSession,
  renameSession,
  sendMessage,
  togglePinSession,
  useDemoPaper,
} = usePaperChat();

const isSidebarCollapsed = ref(false);

const recentSessions = computed<SidebarSessionItem[]>(() =>
  sessions.value.map((session) => ({
    id: session.id,
    isPinned: session.is_pinned,
    title: session.title,
    description: `${session.document_count} 篇论文 · ${session.message_count} 条消息`,
    active: session.active,
  })),
);

const suggestedPrompts: SuggestedPrompt[] = [
  { id: "summary", text: "用 5 个要点总结本文核心贡献" },
  { id: "compare", text: "把本文方法和标准 RAG 做对比" },
];

async function uploadPaper(file: File): Promise<void> {
  await handleUpload(file);
}

function handlePromptClick(text: string): void {
  draft.value = text;
}

function toggleSidebarCollapse(): void {
  isSidebarCollapsed.value = !isSidebarCollapsed.value;
}

onMounted(() => {
  void initializeSessions();
});
</script>

<template>
  <main class="page-shell">
    <section
      class="app-frame"
      aria-label="SciPal 论文智能助手"
    >
      <AppSidebar
        :collapsed="isSidebarCollapsed"
        :indexed-chunks="indexedChunks"
        :is-uploading="isUploading"
        :recent-sessions="recentSessions"
        @delete-session="deleteSession"
        @new-paper="createEmptySession"
        @pin-session="togglePinSession"
        @rename-session="renameSession"
        @select-session="openSession"
        @toggle-collapse="toggleSidebarCollapse"
      />
      <ChatWorkspace
        v-model:draft="draft"
        :error-message="errorMessage"
        :has-paper="hasPaper"
        :is-streaming="isStreaming"
        :is-uploading="isUploading"
        :messages="messages"
        :paper-hint="currentPaperHint"
        :session-title="currentSessionTitle"
        :suggested-prompts="suggestedPrompts"
        :upload-status="uploadStatus"
        @demo-paper="useDemoPaper"
        @prompt-click="handlePromptClick"
        @send="sendMessage"
        @upload-paper="uploadPaper"
      />
    </section>
  </main>
</template>
