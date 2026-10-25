<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import { Delete, Refresh, UploadFilled } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { useLibrary } from "../composables/useLibrary";
import { UPLOAD_STATUS_LABELS } from "../constants/upload";
import type { LibraryDocument } from "../api";
import { formatFileSize, formatUpdatedAt } from "../utils/format";

const emit = defineEmits<{
  open: [sessionId: string];
}>();

const {
  items,
  isLoading,
  isUploading,
  uploadTotal,
  uploadDone,
  errorMessage,
  documentCount,
  readyCount,
  load,
  remove,
  uploadMany,
  startPolling,
  stopPolling,
} = useLibrary();

const fileInputRef = ref<HTMLInputElement | null>(null);

const STATUS_TONES: Record<string, string> = {
  ready: "is-ready",
  failed: "is-failed",
  parsing: "is-busy",
  parsed: "is-busy",
  chunked: "is-busy",
  indexing: "is-busy",
  uploaded: "is-idle",
};

function statusLabel(status: string): string {
  return UPLOAD_STATUS_LABELS[status] ?? status;
}

function statusTone(status: string): string {
  return STATUS_TONES[status] ?? "is-idle";
}

function openDocument(sessionId: string): void {
  emit("open", sessionId);
}

function pickFiles(): void {
  fileInputRef.value?.click();
}

async function handleFiles(event: Event): Promise<void> {
  const target = event.target as HTMLInputElement;
  const files = Array.from(target.files ?? []);
  target.value = "";
  await uploadMany(files);
  if (uploadTotal.value) {
    ElMessage.success(`已提交 ${uploadTotal.value} 篇论文，解析完成后可在列表中打开`);
  }
}

async function handleDelete(document: LibraryDocument): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `删除《${document.filename}》后不可恢复，分块与索引会一并清理。`,
      "删除论文",
      { type: "warning", confirmButtonText: "删除", cancelButtonText: "取消" },
    );
  } catch {
    return;
  }
  const removed = await remove(document.session_id, document.document_id);
  if (removed) {
    ElMessage.success("已删除");
  }
}

onMounted(async () => {
  await load();
  startPolling();
});

onBeforeUnmount(() => {
  stopPolling();
});
</script>

<template>
  <section class="library" aria-label="文献库">
    <header class="library__bar">
      <div>
        <p class="library__eyebrow">文献库 · {{ documentCount }} 篇</p>
        <h1 class="library__title">我的论文</h1>
        <p class="library__subtitle">
          已完成索引 {{ readyCount }} 篇<span v-if="documentCount > readyCount">
            · 其余仍在解析或索引中</span
          >
        </p>
      </div>

      <div class="library__actions">
        <el-button
          class="library__upload"
          :icon="UploadFilled"
          :loading="isUploading"
          size="small"
          @click="pickFiles"
        >
          上传论文
        </el-button>
        <el-button
          class="library__refresh"
          :icon="Refresh"
          :loading="isLoading"
          text
          size="small"
          @click="load(true)"
        >
          刷新
        </el-button>
      </div>
    </header>

    <input
      ref="fileInputRef"
      class="library__file-input"
      type="file"
      accept=".pdf,application/pdf"
      multiple
      @change="handleFiles"
    />

    <p v-if="isUploading" class="library__progress">
      正在上传 {{ uploadDone }}/{{ uploadTotal }}…
      <span class="library__progress-bar" aria-hidden="true">
        <span
          class="library__progress-fill"
          :style="{ width: `${uploadTotal ? (uploadDone / uploadTotal) * 100 : 0}%` }"
        />
      </span>
    </p>

    <div class="library__body">
      <p v-if="isLoading && !items.length" class="library__state">正在读取文献库…</p>
      <p v-else-if="errorMessage && !items.length" class="library__state library__state--error">
        {{ errorMessage }}
      </p>
      <div v-else-if="!items.length" class="library__empty">
        <p class="library__empty-title">还没有收录论文</p>
        <p class="library__empty-hint">
          点击右上角「上传论文」可一次选择多份 PDF，解析完成后会出现在这里。
        </p>
      </div>

      <template v-else>
        <p v-if="errorMessage" class="library__inline-error">{{ errorMessage }}</p>
        <table class="library__table">
          <thead>
            <tr>
              <th scope="col">论文</th>
              <th scope="col">所属会话</th>
              <th scope="col">状态</th>
              <th scope="col" class="library__num">片段</th>
              <th scope="col" class="library__num">大小</th>
              <th scope="col" class="library__num">更新</th>
              <th scope="col" class="library__actions-col">
                <span class="visually-hidden">操作</span>
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="item in items"
              :key="item.document_id"
              class="library__row"
              tabindex="0"
              @click="openDocument(item.session_id)"
              @keydown.enter="openDocument(item.session_id)"
            >
              <td class="library__file">{{ item.filename }}</td>
              <td class="library__session">{{ item.session_title }}</td>
              <td>
                <span class="library__status" :class="statusTone(item.status)">
                  {{ statusLabel(item.status) }}
                </span>
              </td>
              <td class="library__num">{{ item.chunk_count }}</td>
              <td class="library__num">{{ formatFileSize(item.file_size) }}</td>
              <td class="library__num library__time">{{ formatUpdatedAt(item.updated_at) }}</td>
              <td class="library__actions-col">
                <el-button
                  class="library__delete"
                  :icon="Delete"
                  text
                  size="small"
                  aria-label="删除论文"
                  @click.stop="handleDelete(item)"
                />
              </td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>
  </section>
</template>

<style scoped>
.library {
  display: flex;
  min-width: 0;
  flex-direction: column;
  background: var(--color-panel);
}

.library__bar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 26px 34px 18px;
  border-bottom: 1px solid var(--color-border);
}

.library__eyebrow {
  margin: 0 0 6px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  letter-spacing: 0.04em;
}

.library__title {
  margin: 0;
  color: var(--color-text);
  font-family: var(--font-serif);
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.01em;
}

.library__subtitle {
  margin: 6px 0 0;
  color: var(--color-text-muted);
  font-size: 12px;
}

.library__actions {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  gap: 8px;
}

.library__upload {
  font-size: 12px;
}

.library__refresh {
  color: var(--color-text-soft);
  font-size: 12px;
}

.library__file-input {
  display: none;
}

.library__progress {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 0;
  padding: 10px 34px;
  color: var(--color-accent-strong);
  font-size: 12px;
  background: var(--color-accent-soft);
}

.library__progress-bar {
  flex: 1;
  max-width: 220px;
  height: 4px;
  overflow: hidden;
  background: rgba(71, 110, 230, 0.18);
  border-radius: 999px;
}

.library__progress-fill {
  display: block;
  height: 100%;
  background: var(--color-accent);
  transition: width 0.2s ease;
}

.library__body {
  flex: 1;
  min-height: 0;
  padding: 8px 34px 40px;
  overflow-y: auto;
}

.library__state {
  margin: 40px 0;
  color: var(--color-text-muted);
  font-size: 13px;
  text-align: center;
}

.library__state--error {
  color: var(--color-danger);
}

.library__inline-error {
  margin: 12px 0 0;
  padding: 8px 12px;
  color: var(--color-danger);
  font-size: 12px;
  background: rgba(217, 83, 79, 0.08);
  border-radius: 8px;
}

.library__empty {
  margin: 88px auto;
  max-width: 380px;
  text-align: center;
}

.library__empty-title {
  margin: 0 0 8px;
  color: var(--color-text);
  font-family: var(--font-serif);
  font-size: 18px;
}

.library__empty-hint {
  margin: 0;
  color: var(--color-text-muted);
  font-size: 13px;
  line-height: 1.7;
}

.library__table {
  width: 100%;
  margin-top: 12px;
  border-collapse: collapse;
  font-size: 13px;
}

.library__table th {
  padding: 10px 12px;
  color: var(--color-text-muted);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-align: left;
  text-transform: uppercase;
  border-bottom: 1px solid var(--color-border);
}

.library__row {
  cursor: pointer;
  transition: background 0.16s ease;
}

.library__row:hover,
.library__row:focus-visible {
  background: var(--color-surface-alt);
  outline: none;
}

.library__row td {
  padding: 13px 12px;
  border-bottom: 1px solid var(--color-border);
  vertical-align: middle;
}

.library__file {
  color: var(--color-text);
  font-family: var(--font-serif);
  font-size: 14px;
  font-weight: 600;
}

.library__session {
  max-width: 200px;
  overflow: hidden;
  color: var(--color-text-soft);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.library__num {
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
  text-align: right;
  white-space: nowrap;
}

.library__time {
  font-size: 11px;
}

.library__actions-col {
  width: 48px;
  text-align: right;
}

.library__delete {
  color: var(--color-text-muted);
}

.library__delete:hover {
  color: var(--color-danger);
}

.library__status {
  display: inline-block;
  padding: 2px 8px;
  font-size: 11px;
  border-radius: 999px;
}

.library__status.is-ready {
  color: #0b6b62;
  background: var(--color-aqua-soft);
}

.library__status.is-busy {
  color: var(--color-accent-strong);
  background: var(--color-accent-soft);
}

.library__status.is-failed {
  color: var(--color-danger);
  background: rgba(217, 83, 79, 0.1);
}

.library__status.is-idle {
  color: var(--color-text-muted);
  background: var(--color-surface-alt);
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}

@media (max-width: 1100px) {
  .library__bar,
  .library__body {
    padding-right: 20px;
    padding-left: 20px;
  }

  .library__table th:nth-child(2),
  .library__table td:nth-child(2) {
    display: none;
  }
}
</style>
