<script setup lang="ts">
import {
  computed,
  defineAsyncComponent,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from "vue";
import { Close, Tickets } from "@element-plus/icons-vue";
import MarkdownContent from "./MarkdownContent.vue";
import PaperOutline from "./PaperOutline.vue";

// pdf.js 体积较大，只在切到「原页」时才加载
const PdfViewer = defineAsyncComponent(() => import("./PdfViewer.vue"));
import { usePaperReader } from "../composables/usePaperReader";
import type { PaperBlock } from "../api";
import type { SelectionAskMode } from "../types";

const props = defineProps<{
  sessionId: string;
  documentId: string;
}>();

const emit = defineEmits<{
  ask: [text: string, mode: SelectionAskMode];
  close: [];
}>();

const {
  content,
  outline,
  isLoading,
  errorMessage,
  activeBlockId,
  activeSectionKey,
  citationBoxes,
  citationPage,
  load,
  revealBlock,
  setActiveSection,
  mount,
  unmount,
} = usePaperReader();

const scrollRef = ref<HTMLElement | null>(null);
const bodyRef = ref<HTMLElement | null>(null);
const outlineVisible = ref(true);
const viewMode = ref<"text" | "pdf">("text");
const pdfPage = ref(1);
const selectionMenu = ref<{ text: string; x: number; y: number } | null>(null);

// 引用命中时自动切到原页并定位
watch([citationPage, citationBoxes], () => {
  const page = citationPage.value ?? citationBoxes.value[0]?.page_number ?? null;
  if (!page) {
    return;
  }
  pdfPage.value = page;
  viewMode.value = "pdf";
});

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

let scrollFrame = 0;

/** 滚动时用「最后一个越过顶部阈值的小节标题」标记当前章节。 */
function syncActiveSection(): void {
  const container = scrollRef.value;
  if (!container) {
    return;
  }
  const threshold = container.getBoundingClientRect().top + 64;
  const headings = container.querySelectorAll<HTMLElement>("[data-section-key]");
  let current: string | null = null;
  headings.forEach((heading) => {
    if (heading.getBoundingClientRect().top <= threshold) {
      current = heading.dataset.sectionKey ?? null;
    }
  });
  setActiveSection(current);
}

function handleScroll(): void {
  selectionMenu.value = null;
  if (scrollFrame) {
    return;
  }
  scrollFrame = window.requestAnimationFrame(() => {
    scrollFrame = 0;
    syncActiveSection();
  });
}

function scrollToBlock(blockId: string): void {
  const element = window.document.getElementById(`paper-block-${blockId}`);
  element?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function handleOutlineSelect(blockId: string): void {
  if (!blockId) {
    return;
  }
  scrollToBlock(blockId);
  revealBlock([blockId]);
}

function scrollToActiveBlock(): void {
  const id = activeBlockId.value;
  if (id) {
    scrollToBlock(id);
  }
}

/** 选区浮条：只处理落在正文区域内的选区。 */
function handleMouseUp(): void {
  const selection = window.getSelection();
  const text = selection?.toString().trim() ?? "";
  const container = bodyRef.value;
  if (!selection || !text || text.length < 4 || !container || selection.rangeCount === 0) {
    selectionMenu.value = null;
    return;
  }
  const range = selection.getRangeAt(0);
  if (!container.contains(range.commonAncestorContainer)) {
    selectionMenu.value = null;
    return;
  }
  const rect = range.getBoundingClientRect();
  selectionMenu.value = {
    text,
    x: rect.left + rect.width / 2,
    y: rect.top,
  };
}

function askSelection(mode: SelectionAskMode): void {
  const menu = selectionMenu.value;
  if (!menu) {
    return;
  }
  emit("ask", menu.text, mode);
  selectionMenu.value = null;
  window.getSelection()?.removeAllRanges();
}

function handleKeydown(event: KeyboardEvent): void {
  if (event.key === "Escape") {
    selectionMenu.value = null;
  }
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
  syncActiveSection();
  window.document.addEventListener("mouseup", handleMouseUp);
  window.document.addEventListener("keydown", handleKeydown);
});

onBeforeUnmount(() => {
  unmount();
  window.document.removeEventListener("mouseup", handleMouseUp);
  window.document.removeEventListener("keydown", handleKeydown);
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
      <div class="paper-reader__actions">
        <div class="paper-reader__modes" role="group" aria-label="原文视图">
          <button
            type="button"
            class="paper-reader__mode"
            :class="{ 'is-active': viewMode === 'text' }"
            @click="viewMode = 'text'"
          >
            正文
          </button>
          <button
            type="button"
            class="paper-reader__mode"
            :class="{ 'is-active': viewMode === 'pdf' }"
            @click="viewMode = 'pdf'"
          >
            原页
          </button>
        </div>
        <el-button
          class="paper-reader__toggle"
          :class="{ 'is-active': outlineVisible }"
          :icon="Tickets"
          text
          size="small"
          aria-label="切换目录"
          @click="outlineVisible = !outlineVisible"
        />
        <el-button
          class="paper-reader__close"
          :icon="Close"
          circle
          text
          aria-label="收起原文"
          @click="emit('close')"
        />
      </div>
    </header>

    <div class="paper-reader__main">
      <PaperOutline
        v-if="viewMode === 'text' && outlineVisible && outline.length"
        :items="outline"
        :active-key="activeSectionKey"
        @select="handleOutlineSelect"
      />

      <PdfViewer
        v-if="viewMode === 'pdf'"
        :boxes="citationBoxes"
        :document-id="props.documentId"
        :page="pdfPage"
        :session-id="props.sessionId"
        @update:page="pdfPage = $event"
      />

      <div v-else ref="scrollRef" class="paper-reader__scroll" @scroll="handleScroll">
        <p v-if="isLoading" class="paper-reader__state">正在读取解析结果…</p>
        <p v-else-if="errorMessage" class="paper-reader__state paper-reader__state--error">
          {{ errorMessage }}
        </p>
        <p v-else-if="!nodes.length" class="paper-reader__state">
          该论文还没有可展示的结构化正文，请等待解析完成或重新上传。
        </p>

        <article v-else ref="bodyRef" class="paper-reader__body">
          <template v-for="node in nodes" :key="node.key">
            <h2
              v-if="node.kind === 'section'"
              class="paper-reader__section"
              :class="`paper-reader__section--h${node.level}`"
              :data-section-key="node.key"
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
    </div>

    <div
      v-if="selectionMenu"
      class="paper-selection"
      :style="{ left: `${selectionMenu.x}px`, top: `${selectionMenu.y}px` }"
    >
      <button type="button" class="paper-selection__action" @click="askSelection('explain')">
        解释这段
      </button>
      <button type="button" class="paper-selection__action" @click="askSelection('followup')">
        追问
      </button>
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
  gap: 12px;
  justify-content: space-between;
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

.paper-reader__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 2px;
}

.paper-reader__toggle.is-active {
  color: var(--color-accent-strong);
  background: var(--color-accent-soft);
}

.paper-reader__modes {
  display: flex;
  padding: 2px;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: 8px;
}

.paper-reader__mode {
  padding: 3px 10px;
  color: var(--color-text-muted);
  font-size: 11px;
  background: none;
  border: 0;
  border-radius: 6px;
}

.paper-reader__mode.is-active {
  color: var(--color-text);
  background: var(--color-panel);
  box-shadow: 0 1px 3px rgba(48, 68, 101, 0.12);
}

.paper-reader__main {
  display: flex;
  flex: 1;
  min-height: 0;
}

.paper-reader__scroll {
  flex: 1;
  min-width: 0;
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
  scroll-margin-top: 24px;
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
  scroll-margin-top: 96px;
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

/* 选区浮条 */
.paper-selection {
  position: fixed;
  z-index: 2300;
  display: flex;
  gap: 2px;
  padding: 4px;
  background: var(--color-text);
  border-radius: 10px;
  box-shadow: 0 10px 24px rgba(23, 32, 51, 0.24);
  transform: translate(-50%, calc(-100% - 10px));
}

.paper-selection__action {
  padding: 5px 10px;
  color: rgba(255, 255, 255, 0.92);
  font-size: 12px;
  background: none;
  border: 0;
  border-radius: 7px;
}

.paper-selection__action:hover {
  color: var(--color-text);
  background: var(--color-white);
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
