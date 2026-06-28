<script setup lang="ts">
import { Bottom } from "@element-plus/icons-vue";
import type { ScrollbarInstance } from "element-plus";
import { computed, nextTick, onMounted, ref, watch } from "vue";
import MessageBubble from "./MessageBubble.vue";
import type { ChatMessageViewModel, SuggestedPrompt } from "../types";

const props = defineProps<{
  hasPaper: boolean;
  isStreaming: boolean;
  messages: ChatMessageViewModel[];
  suggestedPrompts: SuggestedPrompt[];
}>();

defineEmits<{
  demoPaper: [];
  promptClick: [text: string];
}>();

const SCROLL_FOLLOW_THRESHOLD = 120;
const SCROLL_BUTTON_THRESHOLD = 240;
const scrollbarRef = ref<ScrollbarInstance>();
const isNearBottom = ref(true);
const showScrollButton = ref(false);
const previousMessageIds = ref<string[]>([]);

const messageSignature = computed(() =>
  props.messages
    .map((message) => `${message.id}:${message.text.length}:${message.sources?.length ?? 0}`)
    .join("|"),
);

function isTranscriptReplacement(nextIds: string[]): boolean {
  const currentIds = previousMessageIds.value;
  if (currentIds.length === 0 || nextIds.length === 0) return false;
  if (nextIds.length < currentIds.length) return true;
  return currentIds.some((id, index) => nextIds[index] !== id);
}

function getScrollWrap(): HTMLDivElement | undefined {
  return scrollbarRef.value?.wrapRef;
}

function getDistanceFromBottom(): number {
  const scrollWrap = getScrollWrap();
  if (!scrollWrap) return 0;
  return Math.max(0, scrollWrap.scrollHeight - scrollWrap.clientHeight - scrollWrap.scrollTop);
}

function updateScrollState(): void {
  const distance = getDistanceFromBottom();
  isNearBottom.value = distance <= SCROLL_FOLLOW_THRESHOLD;
  showScrollButton.value = distance > SCROLL_BUTTON_THRESHOLD;
}

function scrollToBottom(behavior: ScrollBehavior = "smooth"): void {
  const scrollWrap = getScrollWrap();
  if (!scrollWrap) return;
  scrollWrap.scrollTo({
    top: scrollWrap.scrollHeight,
    behavior,
  });
}

function handleScroll(): void {
  updateScrollState();
}

watch(
  messageSignature,
  async () => {
    const nextIds = props.messages.map((message) => message.id);
    const shouldResetToBottom = isTranscriptReplacement(nextIds);
    const shouldStickToBottom = shouldResetToBottom || isNearBottom.value;
    await nextTick();
    if (shouldStickToBottom) scrollToBottom("auto");
    updateScrollState();
    previousMessageIds.value = nextIds;
  },
  { flush: "post" },
);

onMounted(async () => {
  await nextTick();
  if (props.messages.length > 0) scrollToBottom("auto");
  updateScrollState();
  previousMessageIds.value = props.messages.map((message) => message.id);
});

function isPendingAssistant(message: ChatMessageViewModel, index: number): boolean {
  if (!props.isStreaming || message.role !== "assistant") return false;
  return index === props.messages.length - 1 && message.text.trim().length === 0;
}
</script>

<template>
  <div
    class="conversation-pane"
    :class="{ 'conversation-pane--messages': props.messages.length > 0 }"
  >
    <section
      v-if="props.messages.length === 0"
      class="welcome-panel"
    >
      <h3>我可以怎样帮你读这篇论文？</h3>
      <p>你可以让我总结、解释方法、分析局限、拆解公式，或给出带引用的答案。</p>
      <div class="prompt-grid">
        <el-button
          v-for="prompt in props.suggestedPrompts"
          :key="prompt.id"
          class="prompt-card"
          text
          @click="$emit('promptClick', prompt.text)"
        >
          {{ prompt.text }}
        </el-button>
      </div>
      <el-button
        v-if="!props.hasPaper"
        class="welcome-panel__demo"
        text
        @click="$emit('demoPaper')"
      >
        或先试用示例论文
      </el-button>
    </section>
    <section
      v-else
      class="message-panel"
      aria-live="polite"
    >
      <el-scrollbar
        ref="scrollbarRef"
        class="message-scroll"
        @scroll="handleScroll"
      >
        <div class="message-list">
          <MessageBubble
            v-for="(message, index) in props.messages"
            :key="message.id"
            :message="message"
            :pending="isPendingAssistant(message, index)"
          />
        </div>
      </el-scrollbar>
      <el-button
        v-if="showScrollButton"
        aria-label="滚动到最新消息"
        :icon="Bottom"
        class="scroll-bottom-button"
        circle
        type="primary"
        @click="scrollToBottom()"
      />
    </section>
  </div>
</template>

<style scoped>
.conversation-pane {
  display: flex;
  min-height: 0;
  flex: 1;
  flex-direction: column;
  justify-content: center;
  padding: clamp(18px, 2.6vh, 28px) 0 clamp(16px, 2vh, 22px);
  overflow: hidden;
}

.conversation-pane--messages {
  justify-content: flex-start;
}
.message-panel {
  position: relative;
  min-height: 0;
  flex: 1;
}
.welcome-panel {
  display: flex;
  max-width: 660px;
  align-self: center;
  flex-direction: column;
  align-items: center;
  text-align: center;
}

.welcome-panel h3 {
  max-width: 580px;
  color: var(--color-text);
  font-size: clamp(24px, 3.2vw, 30px);
  font-weight: 900;
  line-height: 1.1;
  letter-spacing: -0.03em;
}

.welcome-panel p {
  max-width: 520px;
  margin-top: 10px;
  color: var(--color-text-soft);
  font-size: 13px;
}

.welcome-panel__demo { margin-top: 18px; color: var(--color-text-soft); }
.prompt-grid {
  display: grid;
  width: 100%;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 28px;
}

.prompt-card {
  justify-content: flex-start;
  min-height: 54px;
  padding: 12px;
  color: var(--color-text);
  line-height: 1.45;
  white-space: normal;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 15px;
}

.message-scroll { min-height: 0; height: 100%; }
.message-scroll :deep(.el-scrollbar__wrap) {
  padding-right: 8px;
  overscroll-behavior: contain;
}
.message-list {
  display: flex;
  width: min(100%, 1080px);
  min-height: 0;
  flex: 1;
  flex-direction: column;
  gap: 18px;
  margin: 0 auto;
  padding: 3px 0 16px;
}

.scroll-bottom-button.el-button {
  position: absolute;
  right: 18px;
  bottom: 18px;
  box-shadow: var(--shadow-card);
}
@media (max-width: 760px) {
  .prompt-grid { grid-template-columns: 1fr; }
  .scroll-bottom-button.el-button { right: 12px; bottom: 12px; }
}

@media (max-width: 1200px) {
  .message-list {
    width: min(100%, 900px);
  }
}

@media (max-width: 1100px) {
  .message-list {
    gap: 14px;
  }
}

@media (max-height: 820px) {
  .conversation-pane {
    padding-top: 14px;
    padding-bottom: 12px;
  }

  .message-list {
    gap: 12px;
  }
}
</style>
