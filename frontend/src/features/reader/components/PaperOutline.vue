<script setup lang="ts">
import type { ReaderOutlineItem } from "../../../types";

defineProps<{
  items: ReaderOutlineItem[];
  activeKey: string | null;
}>();

const emit = defineEmits<{
  select: [blockId: string];
}>();
</script>

<template>
  <nav class="paper-outline" aria-label="论文目录">
    <p class="paper-outline__title">目录</p>
    <ol class="paper-outline__list">
      <li v-for="item in items" :key="item.key">
        <button
          type="button"
          class="paper-outline__item"
          :class="[`paper-outline__item--l${item.level}`, { 'is-active': item.key === activeKey }]"
          @click="emit('select', item.blockId)"
        >
          <span class="paper-outline__dot" aria-hidden="true" />
          <span class="paper-outline__label">{{ item.title }}</span>
          <span v-if="item.pageNumber" class="paper-outline__page">{{ item.pageNumber }}</span>
        </button>
      </li>
    </ol>
  </nav>
</template>

<style scoped>
.paper-outline {
  display: flex;
  width: 180px;
  flex: 0 0 180px;
  flex-direction: column;
  padding: 20px 10px 24px 14px;
  overflow-y: auto;
  border-right: 1px solid var(--color-border);
}

.paper-outline__title {
  margin: 0 0 10px;
  padding-left: 8px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.paper-outline__list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.paper-outline__item {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 7px;
  padding: 5px 8px;
  color: var(--color-text-soft);
  font-size: 12px;
  text-align: left;
  background: none;
  border: 0;
  border-radius: 6px;
  transition:
    color 0.16s ease,
    background 0.16s ease;
}

.paper-outline__item:hover {
  color: var(--color-accent-strong);
  background: var(--color-accent-soft);
}

.paper-outline__item.is-active {
  color: var(--color-accent-strong);
  font-weight: 600;
  background: var(--color-accent-soft);
}

.paper-outline__dot {
  width: 4px;
  height: 4px;
  flex: 0 0 auto;
  background: var(--color-border-strong);
  border-radius: 50%;
}

.paper-outline__item.is-active .paper-outline__dot {
  background: var(--color-accent);
}

.paper-outline__label {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.paper-outline__item--l3 {
  padding-left: 18px;
}

.paper-outline__item--l4 {
  padding-left: 28px;
  font-size: 11px;
}

.paper-outline__page {
  margin-left: auto;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  font-size: 10px;
}
</style>
