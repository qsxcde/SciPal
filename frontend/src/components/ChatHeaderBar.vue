<script setup lang="ts">
import { ArrowDown, ArrowLeft } from "@element-plus/icons-vue";

defineProps<{
  paperHint: string;
  sessionTitle: string;
}>();
</script>

<template>
  <header class="chat-header-bar">
    <span
      class="chat-header-bar__back"
      aria-hidden="true"
    >
      <el-icon>
        <ArrowLeft />
      </el-icon>
    </span>
    <div class="chat-header-bar__content">
      <div class="chat-header-bar__title-row">
        <h2 class="chat-header-bar__title">
          {{ sessionTitle || "新对话" }}
        </h2>
        <el-icon
          class="chat-header-bar__title-icon"
          aria-hidden="true"
        >
          <ArrowDown />
        </el-icon>
      </div>
      <p
        v-if="paperHint"
        class="chat-header-bar__hint"
      >
        {{ paperHint }}
      </p>
      <p
        v-else
        class="chat-header-bar__hint"
      >
        暂未关联论文
      </p>
    </div>
  </header>
</template>

<style scoped>
.chat-header-bar {
  display: flex;
  width: min(100%, 1080px);
  align-items: center;
  gap: 10px;
  margin: 0 auto;
  padding: 0 0 14px;
}

.chat-header-bar__back {
  display: grid;
  width: 34px;
  height: 34px;
  flex: 0 0 auto;
  place-items: center;
  color: var(--color-text-soft);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 999px;
}

.chat-header-bar__content {
  min-width: 0;
}

.chat-header-bar__title-row {
  display: flex;
  align-items: center;
  gap: 5px;
}

.chat-header-bar__title {
  overflow: hidden;
  color: var(--color-text);
  font-size: 20px;
  font-weight: 850;
  line-height: 1.2;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-header-bar__title-icon,
.chat-header-bar__hint {
  color: var(--color-text-muted);
}

.chat-header-bar__title-icon {
  opacity: 0.72;
}

.chat-header-bar__hint {
  margin-top: 3px;
  overflow: hidden;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 1200px) {
  .chat-header-bar {
    width: min(100%, 900px);
  }
}

@media (max-width: 1100px) {
  .chat-header-bar__title {
    max-width: 320px;
    font-size: 18px;
  }
}
</style>
