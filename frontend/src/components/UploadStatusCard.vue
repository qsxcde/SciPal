<script setup lang="ts">
import type { UploadStatus } from "../types";

defineProps<{
  status: UploadStatus;
}>();
</script>

<template>
  <div class="upload-status-card">
    <div
      class="upload-status-card__icon"
      :class="{ 'upload-status-card__icon--loading': status.phase === 'parsing' }"
    >
      {{ status.phase === "ready" ? "PDF" : "..." }}
    </div>
    <div class="upload-status-card__content">
      <strong>{{ status.fileName }}</strong>
      <span>
        {{ status.phase === "parsing" ? "解析中..." : status.fileSizeLabel }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.upload-status-card {
  display: flex;
  width: min(280px, 100%);
  align-items: center;
  gap: 9px;
  padding: 8px 10px;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
  border-radius: 11px;
}

.upload-status-card__icon {
  display: grid;
  width: 30px;
  height: 30px;
  place-items: center;
  color: var(--color-accent-strong);
  font-size: 9px;
  font-weight: 900;
  background: var(--color-surface);
  border: 1px solid rgba(71, 110, 230, 0.24);
  border-radius: 9px;
}

.upload-status-card__icon--loading {
  color: var(--color-text-muted);
  animation: upload-pulse 1.1s ease-in-out infinite;
}

.upload-status-card__content {
  display: flex;
  min-width: 0;
  flex-direction: column;
  gap: 2px;
}

.upload-status-card__content strong {
  overflow: hidden;
  color: var(--color-text);
  font-size: 12px;
  font-weight: 800;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.upload-status-card__content span {
  color: var(--color-text-muted);
  font-size: 11px;
}

@media (max-width: 1100px) {
  .upload-status-card {
    width: min(240px, 100%);
  }
}

@keyframes upload-pulse {
  0%,
  100% {
    opacity: 0.75;
  }

  50% {
    opacity: 1;
  }
}
</style>
