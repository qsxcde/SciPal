import { computed, ref } from "vue";
import { listLibraryDocuments } from "../api";
import type { LibraryDocument } from "../api";
import { toErrorMessage } from "../utils/error";

const items = ref<LibraryDocument[]>([]);
const isLoading = ref(false);
const errorMessage = ref("");
let loaded = false;

const documentCount = computed(() => items.value.length);
const readyCount = computed(() => items.value.filter((item) => item.status === "ready").length);

async function load(force = false): Promise<void> {
  if (loaded && !force) {
    return;
  }
  isLoading.value = true;
  errorMessage.value = "";
  try {
    items.value = await listLibraryDocuments();
    loaded = true;
  } catch (error) {
    errorMessage.value = toErrorMessage(error, "读取文献库失败");
  } finally {
    isLoading.value = false;
  }
}

/** 上传/删除后失效，下次进入文献库重新拉取。 */
function invalidate(): void {
  loaded = false;
}

export function useLibrary() {
  return {
    items,
    isLoading,
    errorMessage,
    documentCount,
    readyCount,
    load,
    invalidate,
  };
}
