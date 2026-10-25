import { computed, ref } from "vue";
import { createSession, deleteDocument, listLibraryDocuments, uploadDocument } from "../api";
import type { LibraryDocument } from "../api";
import { toErrorMessage } from "../utils/error";

/** 仍在校验/解析/索引中的状态，用于决定是否继续轮询。 */
const PROCESSING_STATUSES = new Set(["uploaded", "parsing", "parsed", "chunked", "indexing"]);
const POLL_INTERVAL_MS = 3000;

const items = ref<LibraryDocument[]>([]);
const isLoading = ref(false);
const isUploading = ref(false);
const uploadTotal = ref(0);
const uploadDone = ref(0);
const errorMessage = ref("");

let loaded = false;
let pollTimer: number | null = null;

const documentCount = computed(() => items.value.length);
const readyCount = computed(() => items.value.filter((item) => item.status === "ready").length);
const hasProcessing = computed(() =>
  items.value.some((item) => PROCESSING_STATUSES.has(item.status)),
);

async function load(force = false, silent = false): Promise<void> {
  if (loaded && !force) {
    return;
  }
  if (!silent) {
    isLoading.value = true;
    errorMessage.value = "";
  }
  try {
    items.value = await listLibraryDocuments();
    loaded = true;
  } catch (error) {
    if (!silent) {
      errorMessage.value = toErrorMessage(error, "读取文献库失败");
    }
  } finally {
    if (!silent) {
      isLoading.value = false;
    }
  }
}

function stopPolling(): void {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

/** 有论文正在处理时轮询列表，直到全部进入终态。 */
function startPolling(): void {
  stopPolling();
  if (!hasProcessing.value) {
    return;
  }
  pollTimer = window.setInterval(async () => {
    await load(true, true);
    if (!hasProcessing.value) {
      stopPolling();
    }
  }, POLL_INTERVAL_MS);
}

async function remove(sessionId: string, documentId: string): Promise<boolean> {
  try {
    await deleteDocument(sessionId, documentId);
    items.value = items.value.filter((item) => item.document_id !== documentId);
    return true;
  } catch (error) {
    errorMessage.value = toErrorMessage(error, "删除论文失败");
    return false;
  }
}

/**
 * 批量上传：每篇论文各建一个会话（当前产品是「会话即论文」），
 * 上传完再统一刷新列表，由轮询接管后续状态。
 */
async function uploadMany(files: File[]): Promise<void> {
  if (!files.length || isUploading.value) {
    return;
  }
  isUploading.value = true;
  uploadTotal.value = files.length;
  uploadDone.value = 0;
  errorMessage.value = "";
  const failures: string[] = [];

  for (const file of files) {
    try {
      const sessionId = await createSession();
      await uploadDocument(sessionId, file);
    } catch (error) {
      failures.push(`${file.name}：${toErrorMessage(error, "上传失败")}`);
    } finally {
      uploadDone.value += 1;
    }
  }

  isUploading.value = false;
  if (failures.length) {
    errorMessage.value = failures.join("；");
  }
  await load(true, true);
  startPolling();
}

/** 上传/删除后失效，下次进入文献库重新拉取。 */
function invalidate(): void {
  loaded = false;
}

export function useLibrary() {
  return {
    items,
    isLoading,
    isUploading,
    uploadTotal,
    uploadDone,
    errorMessage,
    documentCount,
    readyCount,
    hasProcessing,
    load,
    remove,
    uploadMany,
    startPolling,
    stopPolling,
    invalidate,
  };
}
