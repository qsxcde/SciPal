<script setup lang="ts">
import { MoreFilled, Paperclip, Search } from "@element-plus/icons-vue";
import { computed } from "vue";
import type { ComposerToolState } from "../types";

const props = defineProps<{
  disabled: boolean;
  state: ComposerToolState;
}>();

const emit = defineEmits<{
  openUpload: [];
  toggleMore: [];
  toggleSearch: [];
}>();

const searchButtonClass = computed(() => ({
  "composer-tools__button--selected": props.state.isSearchSelected,
}));

const moreButtonClass = computed(() => ({
  "composer-tools__button--selected": props.state.isMoreMenuVisible,
}));
</script>

<template>
  <div class="composer-tools">
    <div class="composer-tools__group">
      <el-button
        class="composer-tools__button"
        :disabled="disabled"
        :icon="Paperclip"
        circle
        text
        aria-label="上传论文"
        @click="$emit('openUpload')"
      />
      <el-button
        class="composer-tools__button"
        :class="searchButtonClass"
        :disabled="disabled"
        :icon="Search"
        circle
        text
        aria-label="切换检索"
        @click="$emit('toggleSearch')"
      />
      <el-button
        class="composer-tools__button"
        :class="moreButtonClass"
        :disabled="disabled"
        :icon="MoreFilled"
        circle
        text
        aria-label="更多工具"
        @click="$emit('toggleMore')"
      />
    </div>
    <span class="composer-tools__hint">
      {{ state.isSearchSelected ? "检索增强已选中" : "工具仅提供界面状态" }}
    </span>
  </div>
</template>

<style scoped>
.composer-tools {
  display: flex;
  min-width: 0;
  align-items: center;
  gap: 10px;
}

.composer-tools__group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.composer-tools__button {
  color: var(--color-text-soft);
  background: transparent;
  border: 1px solid transparent;
}

.composer-tools__button--selected {
  color: var(--color-text);
  background: var(--color-surface-alt);
  border-color: var(--color-border);
}

.composer-tools__hint {
  overflow: hidden;
  color: var(--color-text-muted);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 760px) {
  .composer-tools {
    width: 100%;
    justify-content: space-between;
  }

  .composer-tools__hint {
    max-width: 46%;
  }
}
</style>
