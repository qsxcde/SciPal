<script setup lang="ts">
import type { SourceRef } from "../../../api";
import { formatPageRange } from "../../../utils/format";

defineProps<{
  sources: SourceRef[];
}>();

const emit = defineEmits<{
  select: [source: SourceRef, index: number];
}>();
</script>

<template>
  <ul v-if="sources.length" class="source-citations" aria-label="引用来源">
    <li v-for="(source, index) in sources" :key="`${source.section}#${source.chunk_index}`">
      <button
        type="button"
        class="source-citations__chip"
        :title="source.text_excerpt || source.section"
        @click="emit('select', source, index)"
      >
        <span class="source-citations__index">{{ index + 1 }}</span>
        <span class="source-citations__section">{{ source.section }}</span>
        <span
          v-if="formatPageRange(source.page_start, source.page_end)"
          class="source-citations__page"
        >
          {{ formatPageRange(source.page_start, source.page_end) }}
        </span>
      </button>
    </li>
  </ul>
</template>

<style scoped>
.source-citations {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.source-citations__chip {
  display: inline-flex;
  max-width: 260px;
  align-items: center;
  gap: 6px;
  padding: 4px 10px 4px 4px;
  color: var(--color-text-soft);
  font-size: 12px;
  background: var(--color-panel);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  transition:
    border-color 0.16s ease,
    color 0.16s ease,
    background 0.16s ease;
}

.source-citations__chip:hover {
  color: var(--color-accent-strong);
  background: var(--color-accent-soft);
  border-color: var(--color-border-accent);
}

.source-citations__chip:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 1px;
}

.source-citations__index {
  display: inline-grid;
  width: 18px;
  height: 18px;
  flex: 0 0 auto;
  place-items: center;
  font-family: var(--font-mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--color-white);
  background: var(--color-accent);
  border-radius: 50%;
}

.source-citations__section {
  overflow: hidden;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-citations__page {
  flex: 0 0 auto;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 11px;
}
</style>
