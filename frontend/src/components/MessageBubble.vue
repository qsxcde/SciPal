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
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  border-radius: 11px;
  background: linear-gradient(145deg, #5d80ee 0%, #2d55d1 100%);
  box-shadow: 0 14px 28px rgba(71, 110, 230, 0.2);
}

.avatar-shell__brand {
  color: #ffffff;
  font-size: 14px;
  font-weight: 900;
  line-height: 1;
}

.message-column {
  display: flex;
  max-width: min(820px, calc(100% - 46px));
  flex-direction: column;
  gap: 8px;
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
  padding: 12px 16px;
  font-size: 13px;
  line-height: 1.5;
}

.message-bubble--user {
  color: var(--color-text);
  background: var(--color-user);
  border: 1px solid var(--color-user-border);
  border-radius: 16px 16px 6px 16px;
  font-size: 14px;
  font-weight: 650;
}

.message-bubble--assistant {
  color: var(--color-text);
  padding: 18px 22px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid var(--color-border-strong);
  border-radius: 17px;
  box-shadow: var(--shadow-shell);
}

.message-bubble--assistant :deep(.markdown-content) {
  color: #26334a;
  font-size: 14px;
  line-height: 1.62;
}

.message-bubble--assistant :deep(p + p),
.message-bubble--assistant :deep(p + ul),
.message-bubble--assistant :deep(p + ol) {
  margin-top: 12px;
}

.message-bubble--assistant :deep(ul),
.message-bubble--assistant :deep(ol) {
  display: grid;
  gap: 8px;
  margin: 12px 0 0;
  padding-left: 20px;
}

.message-bubble--assistant :deep(li) {
  color: #29374f;
  font-size: 14px;
  line-height: 1.52;
}

.message-bubble--assistant :deep(li::marker) {
  color: var(--color-aqua);
}

.message-bubble--assistant :deep(code) {
  color: var(--color-text);
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: 6px;
}

.message-bubble--user :deep(.markdown-content code) {
  color: var(--color-text);
  background: rgba(255, 255, 255, 0.7);
  border-color: var(--color-border);
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

@media (max-width: 1200px) {
  .message-column {
    max-width: min(780px, calc(100% - 46px));
  }

  .message-bubble--assistant {
    padding: 17px 20px;
  }
}

@media (max-width: 1100px) {
  .message-column {
    max-width: 100%;
  }

  .message-bubble--assistant {
    padding: 16px 18px;
  }
}

@media (max-height: 820px) {
  .message-bubble--assistant {
    padding: 14px 18px;
  }

  .message-bubble--assistant :deep(.markdown-content) {
    line-height: 1.5;
  }

  .message-bubble--assistant :deep(ul),
  .message-bubble--assistant :deep(ol) {
    gap: 6px;
    margin-top: 10px;
  }
}
</style>
