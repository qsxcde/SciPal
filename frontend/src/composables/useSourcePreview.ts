import { ref } from "vue";
import { getSourceChunk } from "../api";
import type { SourceChunk, SourceRef } from "../api";
import type { SourceSelection } from "../types";
import { toErrorMessage } from "../utils/error";
import { usePaperReader } from "./usePaperReader";

const { revealBlock } = usePaperReader();

/**
 * 引用抽屉的共享状态。
 *
 * 单例设计：消息气泡只负责触发，抽屉挂在布局层，避免逐层透传 props。
 */
const activeSessionId = ref<string | null>(null);
const selection = ref<SourceSelection | null>(null);
const chunk = ref<SourceChunk | null>(null);
const isLoading = ref(false);
const errorMessage = ref("");

function setActiveSession(sessionId: string | null): void {
  if (activeSessionId.value === sessionId) {
    return;
  }
  activeSessionId.value = sessionId;
  close();
}

function close(): void {
  selection.value = null;
  chunk.value = null;
  errorMessage.value = "";
  isLoading.value = false;
}

async function openCitation(source: SourceRef, index: number): Promise<void> {
  selection.value = { index, source };
  chunk.value = null;
  errorMessage.value = "";

  const sessionId = activeSessionId.value;
  if (!sessionId || !source.paper_id) {
    // 历史引用缺 paper_id 时仍展示命中片段，不再请求全文。
    return;
  }

  isLoading.value = true;
  try {
    chunk.value = await getSourceChunk(sessionId, source.paper_id, source.chunk_index);
    // 阅读器可见时同步滚动并高亮命中段落
    revealBlock(chunk.value.block_ids);
  } catch (error) {
    errorMessage.value = toErrorMessage(error, "读取原文失败");
  } finally {
    isLoading.value = false;
  }
}

export function useSourcePreview() {
  return {
    selection,
    chunk,
    isLoading,
    errorMessage,
    setActiveSession,
    openCitation,
    close,
  };
}
