import { computed, ref } from "vue";
import { getPaperContent } from "../api";
import type { PaperContent, SourceBlockBox } from "../api";
import type { ReaderOutlineItem } from "../types";
import { toErrorMessage } from "../utils/error";

const HIGHLIGHT_DURATION_MS = 2400;

/**
 * 阅读器共享状态。
 *
 * 单例原因：引用面板与阅读器分处不同组件树层级，需要共享「当前高亮块」。
 */
const content = ref<PaperContent | null>(null);
const documentId = ref<string | null>(null);
const isLoading = ref(false);
const errorMessage = ref("");
const activeBlockId = ref<string | null>(null);
const activeSectionKey = ref<string | null>(null);
const isMounted = ref(false);
/** 被引用命中的原文块坐标，供 PDF 原页高亮 */
const citationBoxes = ref<SourceBlockBox[]>([]);
const citationPage = ref<number | null>(null);

let highlightTimer: number | null = null;

const hasContent = computed(() => Boolean(content.value?.blocks.length));

/** 大纲：按 section_path 变化取每节第一个块作为锚点。 */
const outline = computed<ReaderOutlineItem[]>(() => {
  const items: ReaderOutlineItem[] = [];
  let lastPath = "";
  for (const block of content.value?.blocks ?? []) {
    const path = block.section_path.join(" > ");
    if (!path || path === lastPath) {
      continue;
    }
    lastPath = path;
    items.push({
      key: `section-${path}`,
      title: block.section_path[block.section_path.length - 1] ?? path,
      level: Math.min(block.section_path.length + 1, 4),
      blockId: block.id,
      pageNumber: block.page_number,
    });
  }
  return items;
});

function clearHighlight(): void {
  if (highlightTimer !== null) {
    window.clearTimeout(highlightTimer);
    highlightTimer = null;
  }
  activeBlockId.value = null;
}

/** 高亮并滚动到引用命中的第一个块；未挂载时只记录，不生效。 */
function revealBlock(blockIds: string[] | null | undefined): void {
  const target = blockIds?.[0];
  if (!target) {
    return;
  }
  if (!isMounted.value) {
    return;
  }
  clearHighlight();
  activeBlockId.value = target;
  highlightTimer = window.setTimeout(clearHighlight, HIGHLIGHT_DURATION_MS);
}

async function load(sessionId: string, id: string): Promise<void> {
  if (documentId.value === id && content.value) {
    return;
  }
  documentId.value = id;
  content.value = null;
  errorMessage.value = "";
  isLoading.value = true;
  try {
    content.value = await getPaperContent(sessionId, id);
  } catch (error) {
    errorMessage.value = toErrorMessage(error, "读取正文失败");
  } finally {
    isLoading.value = false;
  }
}

function mount(): void {
  isMounted.value = true;
}

function unmount(): void {
  isMounted.value = false;
  clearHighlight();
}

function setActiveSection(key: string | null): void {
  activeSectionKey.value = key;
}

/** 引用定位：同时记录原页坐标，阅读器据此切到「原页」并高亮。 */
function revealCitation(blocks: SourceBlockBox[] | null, page: number | null): void {
  citationBoxes.value = blocks ?? [];
  citationPage.value = page;
}

function reset(): void {
  content.value = null;
  documentId.value = null;
  errorMessage.value = "";
  isLoading.value = false;
  activeSectionKey.value = null;
  citationBoxes.value = [];
  citationPage.value = null;
  unmount();
}

export function usePaperReader() {
  return {
    content,
    hasContent,
    outline,
    isLoading,
    errorMessage,
    activeBlockId,
    activeSectionKey,
    citationBoxes,
    citationPage,
    load,
    revealBlock,
    revealCitation,
    clearHighlight,
    setActiveSection,
    mount,
    unmount,
    reset,
  };
}
