<script setup lang="ts">
import ChatComposer from "./ChatComposer.vue";
import ChatHeaderBar from "./ChatHeaderBar.vue";
import MessageList from "./MessageList.vue";
import type { ChatMessageViewModel, SuggestedPrompt, UploadStatus } from "../types";

const props = defineProps<{
  draft: string;
  errorMessage: string;
  hasPaper: boolean;
  isUploading: boolean;
  isStreaming: boolean;
  messages: ChatMessageViewModel[];
  paperHint: string;
  sessionTitle: string;
  suggestedPrompts: SuggestedPrompt[];
  uploadStatus: UploadStatus | null;
}>();

const emit = defineEmits<{
  demoPaper: [];
  promptClick: [text: string];
  send: [text: string];
  "update:draft": [value: string];
  uploadPaper: [file: File];
}>();

function handleDraftUpdate(value: string): void {
  emit("update:draft", value);
}
</script>

<template>
  <section
    class="chat-workspace"
    aria-label="论文问答区"
  >
    <ChatHeaderBar
      :paper-hint="paperHint"
      :session-title="sessionTitle"
    />
    <MessageList
      :has-paper="hasPaper"
      :is-streaming="isStreaming"
      :messages="messages"
      :suggested-prompts="suggestedPrompts"
      @demo-paper="$emit('demoPaper')"
      @prompt-click="$emit('promptClick', $event)"
    />

    <p
      v-if="errorMessage"
      class="error-text"
    >
      {{ errorMessage }}
    </p>
    <ChatComposer
      :draft="draft"
      :is-streaming="isStreaming"
      :is-uploading="isUploading"
      :upload-status="uploadStatus"
      @send="$emit('send', $event)"
      @update:draft="handleDraftUpdate"
      @upload-paper="$emit('uploadPaper', $event)"
    />
  </section>
</template>

<style scoped>
.chat-workspace {
  display: flex;
  height: 100%;
  min-width: 0;
  flex-direction: column;
  padding: 24px 34px;
  overflow: hidden;
  background: var(--color-shell);
}

.error-text {
  width: min(100%, 66%);
  margin: 0 auto 10px;
  color: var(--el-color-danger);
  font-size: 13px;
}

@media (max-width: 760px) {
  .chat-workspace {
    padding: 18px;
  }

  .error-text {
    width: 100%;
  }
}
</style>
