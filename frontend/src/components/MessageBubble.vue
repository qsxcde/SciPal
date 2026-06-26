<script setup lang="ts">
import { computed } from "vue";
import MarkdownContent from "./MarkdownContent.vue";
import MessageActions from "./MessageActions.vue";
import type { ChatMessageViewModel } from "../types";

const EMPTY_ASSISTANT_FALLBACK = "回答生成失败，请重试或重新发送问题。";

const props = defineProps<{
  message: ChatMessageViewModel;
  pending?: boolean;
}>();

const displayText = computed(() => {
  if (props.pending) {
    return "正在检索论文并生成回答...";
  }

  if (props.message.role === "assistant" && props.message.text.trim().length === 0) {
    return EMPTY_ASSISTANT_FALLBACK;
  }

  return props.message.text;
});

function buildSourceKey(section: string, chunkIndex: number, index: number): string {
  return `${section}-${chunkIndex}-${index}`;
}
</script>

<template>
  <article
    class="message-row"
    :class="`message-row--${props.message.role}`"
  >
    <div
      v-if="props.message.role === 'assistant'"
      class="avatar-shell"
      aria-hidden="true"
    >
      <span class="avatar-shell__brand">S</span>
    </div>

    <div class="message-column">
      <div
        class="message-bubble"
        :class="`message-bubble--${props.message.role}`"
      >
        <MarkdownContent :text="displayText" />
      </div>

      <div
        v-if="props.message.sources?.length"
        class="source-tags"
      >
        <span
          v-for="(source, index) in props.message.sources"
          :key="buildSourceKey(source.section, source.chunk_index, index)"
        >
          [{{ index + 1 }}] {{ source.section }} · #{{ source.chunk_index }}
        </span>
      </div>

      <MessageActions
        v-if="props.message.role === 'assistant' && props.message.text.trim()"
        :content="props.message.text"
      />
    </div>
  </article>
</template>

<style scoped>
.message-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.message-row--user {
  justify-content: flex-end;
}

.message-row--assistant {
  justify-content: flex-start;
}

.avatar-shell {
  display: inline-flex;
  width: 36px;
  height: 36px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  background: linear-gradient(180deg, #7f99ee 0%, #6883df 100%);
  box-shadow: var(--shadow-card);
}

.avatar-shell__brand {
  color: #ffffff;
  font-size: 16px;
  font-weight: 900;
  line-height: 1;
}

.message-column {
  display: flex;
  max-width: min(720px, calc(100% - 48px));
  flex-direction: column;
  gap: 10px;
}

.message-row--user .message-column {
  align-items: flex-end;
}

.message-row--assistant .message-column {
  align-items: flex-start;
}

.message-bubble {
  width: fit-content;
  max-width: 100%;
  padding: 14px 18px;
  font-size: 14px;
  line-height: 1.55;
}

.message-bubble--user {
  color: var(--color-text);
  background: var(--color-user);
  border: 1px solid var(--color-user-border);
  border-radius: 20px 20px 6px 20px;
}

.message-bubble--assistant {
  color: var(--color-text);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 22px;
  box-shadow: var(--shadow-card);
}

.message-bubble--user :deep(.markdown-content code) {
  color: var(--color-text);
  background: rgba(255, 255, 255, 0.7);
  border-color: var(--color-border);
}

.source-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.source-tags span {
  padding: 6px 9px;
  color: var(--color-text);
  font-size: 11px;
  font-weight: 700;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: 999px;
}

@media (max-width: 760px) {
  .message-column {
    max-width: calc(100% - 44px);
  }

  .avatar-shell {
    width: 32px;
    height: 32px;
    border-radius: 12px;
  }
}
</style>
