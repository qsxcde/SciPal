import { computed, ref } from "vue";
import { getPaperContent } from "../api";
import type { PaperContent } from "../api";
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
const isMounted = ref(false);

let highlightTimer: number | null = null;

const hasContent = computed(() => Boolean(content.value?.blocks.length));

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

function reset(): void {
  content.value = null;
  documentId.value = null;
  errorMessage.value = "";
  isLoading.value = false;
  unmount();
}

export function usePaperReader() {
  return {
    content,
    hasContent,
    isLoading,
    errorMessage,
    activeBlockId,
    load,
    revealBlock,
    clearHighlight,
    mount,
    unmount,
    reset,
  };
}
