<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, watch } from "vue";
import { Close } from "@element-plus/icons-vue";
import MarkdownContent from "./MarkdownContent.vue";
import { usePaperReader } from "../composables/usePaperReader";
import type { PaperBlock } from "../api";

const props = defineProps<{
  sessionId: string;
  documentId: string;
}>();

const emit = defineEmits<{
  close: [];
}>();

const { content, isLoading, errorMessage, activeBlockId, load, mount, unmount } = usePaperReader();

type ReaderNode =
  | { kind: "section"; key: string; title: string; level: number }
  | { kind: "block"; key: string; block: PaperBlock };

/** 章节标题由 section_path 变化推导，避免正文里重复输出标题。 */
const nodes = computed<ReaderNode[]>(() => {
  const blocks = content.value?.blocks ?? [];
  const result: ReaderNode[] = [];
  let lastPath = "";

  blocks.forEach((block, index) => {
    const path = block.section_path.join(" > ");
    if (path && path !== lastPath) {
      lastPath = path;
      result.push({
        kind: "section",
        key: `section-${path}`,
        title: block.section_path[block.section_path.length - 1] ?? path,
        level: Math.min(block.section_path.length + 1, 4),
      });
    }
    result.push({ kind: "block", key: block.id || `block-${index}`, block });
  });

  return result;
});

function scrollToActiveBlock(): void {
  const id = activeBlockId.value;
  if (!id) {
    return;
  }
  const element = window.document.getElementById(`paper-block-${id}`);
  element?.scrollIntoView({ behavior: "smooth", block: "center" });
}

watch([activeBlockId, content], async () => {
  if (!activeBlockId.value) {
    return;
  }
  await nextTick();
  scrollToActiveBlock();
});

watch(
  () => props.documentId,
  (id) => {
    void load(props.sessionId, id);
  },
);

onMounted(async () => {
  mount();
  await load(props.sessionId, props.documentId);
  await nextTick();
  scrollToActiveBlock();
});

onBeforeUnmount(() => {
  unmount();
});
</script>

<template>
  <section class="paper-reader" aria-label="论文原文">
    <header class="paper-reader__bar">
      <div class="paper-reader__meta">
        <p class="paper-reader__eyebrow">
          原文<span v-if="content?.parser_name"> · {{ content.parser_name }}</span>
          <span v-if="content?.chunk_count"> · {{ content.chunk_count }} 个片段</span>
        </p>
        <h1 class="paper-reader__filename">
          {{ content?.filename || "正在载入正文" }}
        </h1>
      </div>
      <el-button
        class="paper-reader__close"
        :icon="Close"
        circle
        text
        aria-label="收起原文"
        @click="emit('close')"
      />
    </header>

    <div class="paper-reader__scroll">
      <p v-if="isLoading" class="paper-reader__state">正在读取解析结果…</p>
      <p v-else-if="errorMessage" class="paper-reader__state paper-reader__state--error">
        {{ errorMessage }}
      </p>
      <p v-else-if="!nodes.length" class="paper-reader__state">
        该论文还没有可展示的结构化正文，请等待解析完成或重新上传。
      </p>

      <article v-else class="paper-reader__body">
        <template v-for="node in nodes" :key="node.key">
          <h2
            v-if="node.kind === 'section'"
            class="paper-reader__section"
            :class="`paper-reader__section--h${node.level}`"
          >
            {{ node.title }}
          </h2>
          <div
            v-else
            :id="node.block.id ? `paper-block-${node.block.id}` : undefined"
            class="paper-reader__block"
            :class="{
              'is-active': activeBlockId === node.block.id,
              'paper-reader__block--table': node.block.type === 'table',
              'paper-reader__block--formula': node.block.type === 'formula',
            }"
          >
            <p v-if="node.block.page_number" class="paper-reader__anchor" aria-hidden="true">
              p.{{ node.block.page_number }}
            </p>
            <p v-if="node.block.type === 'title'" class="paper-reader__title">
              {{ node.block.text }}
            </p>
            <pre v-else-if="node.block.type === 'table'" class="paper-reader__pre">{{
              node.block.text
            }}</pre>
            <p v-else-if="node.block.type === 'formula'" class="paper-reader__formula">
              {{ node.block.text }}
            </p>
            <MarkdownContent v-else :text="node.block.text" />
          </div>
        </template>
      </article>
    </div>
  </section>
</template>

<style scoped>
.paper-reader {
  display: flex;
  min-width: 0;
  flex-direction: column;
  background: var(--color-panel);
  border-right: 1px solid var(--color-border);
}

.paper-reader__bar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 26px 14px;
  border-bottom: 1px solid var(--color-border);
}

.paper-reader__meta {
  min-width: 0;
}

.paper-reader__eyebrow {
  margin: 0 0 4px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.02em;
}

.paper-reader__filename {
  margin: 0;
  overflow: hidden;
  color: var(--color-text);
  font-family: var(--font-serif);
  font-size: 18px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.paper-reader__scroll {
  flex: 1;
  min-height: 0;
  padding: 26px 30px 96px;
  overflow-y: auto;
}

.paper-reader__body {
  max-width: 720px;
  margin: 0 auto;
}

.paper-reader__state {
  max-width: 520px;
  margin: 40px auto;
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.7;
  text-align: center;
}

.paper-reader__state--error {
  color: var(--color-danger);
}

.paper-reader__section {
  margin: 34px 0 12px;
  color: var(--color-text);
  font-family: var(--font-serif);
  line-height: 1.3;
  letter-spacing: -0.01em;
}

.paper-reader__section--h2 {
  font-size: 21px;
}

.paper-reader__section--h3 {
  font-size: 17px;
}

.paper-reader__section--h4 {
  font-size: 15px;
  color: var(--color-text-soft);
}

.paper-reader__block {
  position: relative;
  margin: 0 -12px;
  padding: 6px 12px;
  border-radius: 8px;
  transition:
    background 0.24s ease,
    box-shadow 0.24s ease;
}

.paper-reader__block + .paper-reader__block {
  margin-top: 4px;
}

.paper-reader__block.is-active {
  background: var(--color-accent-soft);
  box-shadow: -3px 0 0 var(--color-accent);
}

.paper-reader__anchor {
  position: absolute;
  top: 6px;
  left: -46px;
  width: 34px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  text-align: right;
}

.paper-reader__title {
  margin: 0;
  color: var(--color-text);
  font-family: var(--font-serif);
  font-size: 24px;
  font-weight: 700;
  line-height: 1.35;
}

.paper-reader__formula {
  margin: 0;
  color: var(--color-text-body);
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.7;
  word-break: break-word;
}

.paper-reader__pre {
  margin: 0;
  padding: 10px 12px;
  overflow-x: auto;
  color: var(--color-text-body);
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
  background: var(--color-surface-alt);
  border-radius: 8px;
}

.paper-reader__block :deep(.markdown-content) {
  color: var(--color-text-body);
  font-family: var(--font-serif);
  font-size: 15px;
  line-height: 1.85;
}

.paper-reader__block :deep(.markdown-content p + p) {
  margin-top: 10px;
}

.paper-reader__block :deep(.markdown-content ul),
.paper-reader__block :deep(.markdown-content ol) {
  display: grid;
  gap: 6px;
  margin: 10px 0 0;
  padding-left: 22px;
}

@media (max-width: 1200px) {
  .paper-reader__scroll {
    padding: 22px 22px 80px;
  }

  .paper-reader__anchor {
    display: none;
  }
}
</style>
