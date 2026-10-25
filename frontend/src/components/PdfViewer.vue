<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import * as pdfjs from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { fetchDocumentFile } from "../api";
import type { SourceBlockBox } from "../api";
import { toErrorMessage } from "../utils/error";

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl;

const props = defineProps<{
  boxes: SourceBlockBox[];
  documentId: string;
  page: number;
  sessionId: string;
}>();

const emit = defineEmits<{
  "update:page": [page: number];
}>();

const canvasRef = ref<HTMLCanvasElement | null>(null);
const stageRef = ref<HTMLElement | null>(null);
const documentRef = shallowRef<pdfjs.PDFDocumentProxy | null>(null);
const loadingTaskRef = shallowRef<pdfjs.PDFDocumentLoadingTask | null>(null);
const totalPages = ref(0);
const isLoading = ref(true);
const errorMessage = ref("");
let renderToken = 0;

const pageBoxes = computed(() =>
  props.boxes.filter((box) => box.page_number === props.page && box.bbox),
);

const pageLabel = computed(() => (totalPages.value ? `${props.page} / ${totalPages.value}` : "—"));

/** 归一化坐标 → 画布百分比定位 */
function boxStyle(box: SourceBlockBox): Record<string, string> {
  const bbox = box.bbox;
  if (!bbox) {
    return {};
  }
  return {
    left: `${bbox.x0 * 100}%`,
    top: `${bbox.y0 * 100}%`,
    width: `${Math.max(0.01, bbox.x1 - bbox.x0) * 100}%`,
    height: `${Math.max(0.005, bbox.y1 - bbox.y0) * 100}%`,
  };
}

async function renderCurrentPage(): Promise<void> {
  const doc = documentRef.value;
  const canvas = canvasRef.value;
  if (!doc || !canvas) {
    return;
  }
  const token = ++renderToken;
  try {
    const pdfPage = await doc.getPage(props.page);
    if (token !== renderToken) {
      return;
    }
    const baseViewport = pdfPage.getViewport({ scale: 1 });
    const available = stageRef.value?.clientWidth ?? 720;
    const scale = Math.max(0.4, Math.min(2.5, (available - 8) / baseViewport.width));
    const viewport = pdfPage.getViewport({ scale });

    const context = canvas.getContext("2d");
    if (!context) {
      return;
    }
    canvas.width = Math.floor(viewport.width);
    canvas.height = Math.floor(viewport.height);
    canvas.style.width = `${Math.floor(viewport.width)}px`;
    canvas.style.height = `${Math.floor(viewport.height)}px`;
    await pdfPage.render({ canvasContext: context, viewport, canvas }).promise;
  } catch (error) {
    if (token === renderToken) {
      errorMessage.value = toErrorMessage(error, "PDF 渲染失败");
    }
  }
}

async function loadDocument(): Promise<void> {
  isLoading.value = true;
  errorMessage.value = "";
  await loadingTaskRef.value?.destroy();
  loadingTaskRef.value = null;
  documentRef.value = null;
  try {
    const buffer = await fetchDocumentFile(props.sessionId, props.documentId);
    const task = pdfjs.getDocument({ data: buffer });
    loadingTaskRef.value = task;
    const loaded = await task.promise;
    documentRef.value = loaded;
    totalPages.value = loaded.numPages;
    if (props.page > loaded.numPages) {
      emit("update:page", 1);
    }
    await renderCurrentPage();
  } catch (error) {
    errorMessage.value = toErrorMessage(error, "PDF 渲染失败");
  } finally {
    isLoading.value = false;
  }
}

let resizeTimer = 0;
function handleResize(): void {
  window.clearTimeout(resizeTimer);
  resizeTimer = window.setTimeout(() => {
    void renderCurrentPage();
  }, 160);
}

watch(
  () => props.page,
  () => {
    void renderCurrentPage();
  },
);

watch(
  () => props.documentId,
  () => {
    void loadDocument();
  },
);

onMounted(async () => {
  await loadDocument();
  window.addEventListener("resize", handleResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  window.clearTimeout(resizeTimer);
  void loadingTaskRef.value?.destroy();
});
</script>

<template>
  <div class="pdf-viewer">
    <header class="pdf-viewer__toolbar">
      <el-button text size="small" :disabled="page <= 1" @click="emit('update:page', page - 1)">
        上一页
      </el-button>
      <span class="pdf-viewer__pager">{{ pageLabel }}</span>
      <el-button
        text
        size="small"
        :disabled="!totalPages || page >= totalPages"
        @click="emit('update:page', page + 1)"
      >
        下一页
      </el-button>
    </header>

    <div ref="stageRef" class="pdf-viewer__stage">
      <p v-if="isLoading" class="pdf-viewer__state">正在加载 PDF…</p>
      <p v-else-if="errorMessage" class="pdf-viewer__state pdf-viewer__state--error">
        {{ errorMessage }}
      </p>

      <div v-show="!isLoading && !errorMessage" class="pdf-viewer__page">
        <canvas ref="canvasRef" class="pdf-viewer__canvas" />
        <span
          v-for="box in pageBoxes"
          :key="box.id"
          class="pdf-viewer__hit"
          :style="boxStyle(box)"
          aria-hidden="true"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.pdf-viewer {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  background: var(--color-surface-alt);
}

.pdf-viewer__toolbar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 8px 16px;
  background: var(--color-panel);
  border-bottom: 1px solid var(--color-border);
}

.pdf-viewer__pager {
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
}

.pdf-viewer__stage {
  flex: 1;
  min-height: 0;
  padding: 18px;
  overflow: auto;
  text-align: center;
}

.pdf-viewer__state {
  margin: 48px 0;
  color: var(--color-text-muted);
  font-size: 13px;
}

.pdf-viewer__state--error {
  color: var(--color-danger);
}

.pdf-viewer__page {
  position: relative;
  display: inline-block;
  box-shadow: 0 12px 30px rgba(48, 68, 101, 0.14);
}

.pdf-viewer__canvas {
  display: block;
  max-width: 100%;
  background: var(--color-white);
}

.pdf-viewer__hit {
  position: absolute;
  background: rgba(71, 110, 230, 0.22);
  border: 1px solid var(--color-accent);
  border-radius: 3px;
  box-shadow: 0 0 0 3px rgba(71, 110, 230, 0.12);
  animation: pdf-hit-pulse 1.6s ease-in-out 2;
}

@keyframes pdf-hit-pulse {
  0%,
  100% {
    background: rgba(71, 110, 230, 0.16);
  }

  50% {
    background: rgba(71, 110, 230, 0.38);
  }
}
</style>
