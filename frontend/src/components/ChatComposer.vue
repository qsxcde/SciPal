<script setup lang="ts">
import { Promotion } from "@element-plus/icons-vue";
import { computed, ref } from "vue";
import ComposerTools from "./ComposerTools.vue";
import UploadStatusCard from "./UploadStatusCard.vue";
import type { ComposerToolState, UploadStatus } from "../types";

const props = defineProps<{
  draft: string;
  isStreaming: boolean;
  isUploading: boolean;
  uploadStatus: UploadStatus | null;
}>();

const emit = defineEmits<{
  send: [text: string];
  "update:draft": [value: string];
  uploadPaper: [file: File];
}>();

const fileInputRef = ref<HTMLInputElement | null>(null);
const toolState = ref<ComposerToolState>({
  isMoreMenuVisible: false,
  isSearchSelected: false,
});

const isDisabled = computed(() => props.isStreaming || props.isUploading);

function sendDraft(): void {
  emit("send", props.draft);
}

function handleDraftChange(value: string): void {
  emit("update:draft", value);
}

function handleEnter(event: KeyboardEvent): void {
  if (event.shiftKey || event.isComposing) {
    return;
  }
  event.preventDefault();
  sendDraft();
}

function openFilePicker(): void {
  fileInputRef.value?.click();
}

function handleFileChange(event: Event): void {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) {
    return;
  }
  emit("uploadPaper", file);
  target.value = "";
}

function toggleSearch(): void {
  toolState.value.isSearchSelected = !toolState.value.isSearchSelected;
}

function toggleMore(): void {
  toolState.value.isMoreMenuVisible = !toolState.value.isMoreMenuVisible;
}
</script>

<template>
  <footer class="chat-composer">
    <input
      ref="fileInputRef"
      class="chat-composer__file-input"
      type="file"
      accept=".pdf,application/pdf"
      @change="handleFileChange"
    >
    <UploadStatusCard
      v-if="uploadStatus"
      :status="uploadStatus"
    />
    <el-input
      :model-value="draft"
      class="chat-composer__input"
      type="textarea"
      :autosize="{ minRows: 2, maxRows: 4 }"
      :disabled="isDisabled"
      placeholder="给 SciPal 发送消息"
      resize="none"
      @update:model-value="handleDraftChange"
      @keydown.enter="handleEnter"
    />
    <div class="chat-composer__actions">
      <ComposerTools
        :disabled="isDisabled"
        :state="toolState"
        @open-upload="openFilePicker"
        @toggle-more="toggleMore"
        @toggle-search="toggleSearch"
      />
      <el-button
        class="chat-composer__send"
        :disabled="!draft.trim() || isDisabled"
        :icon="Promotion"
        circle
        :loading="isStreaming"
        aria-label="发送消息"
        @click="sendDraft"
      />
    </div>
  </footer>
</template>

<style scoped>
.chat-composer {
  display: flex;
  width: min(100%, 860px);
  min-height: 0;
  margin: 0 auto;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  background: var(--color-surface);
  border: 1px solid var(--color-border-strong);
  border-radius: 22px;
  box-shadow: var(--shadow-input);
}

.chat-composer__file-input {
  display: none;
}

.chat-composer__input {
  position: relative;
  z-index: 1;
}

.chat-composer__input :deep(.el-textarea__inner) {
  min-height: 56px;
  padding: 0;
  color: var(--color-text);
  line-height: 1.5;
  background: transparent;
  border: 0;
  box-shadow: none;
}

.chat-composer__input :deep(.el-textarea__inner::placeholder) {
  color: var(--color-text-muted);
}

.chat-composer__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.chat-composer__send {
  flex: 0 0 auto;
  width: 36px;
  height: 36px;
  color: #ffffff;
  background: linear-gradient(180deg, #7f99ee 0%, #6883df 100%);
  border-color: transparent;
  box-shadow: 0 10px 22px rgba(104, 131, 223, 0.24);
}

@media (max-width: 760px) {
  .chat-composer {
    width: 100%;
    padding: 12px;
    border-radius: 18px;
  }

  .chat-composer__actions {
    flex-direction: column;
    align-items: stretch;
  }

  .chat-composer__send {
    align-self: flex-end;
  }
}
</style>
