<script setup lang="ts">
defineProps<{
  paperHint: string;
  sessionTitle: string;
}>();
</script>

<template>
  <header class="chat-header-bar">
    <div class="chat-header-bar__content">
      <h2 class="chat-header-bar__title">
        {{ sessionTitle || "新对话" }}
      </h2>
      <p v-if="paperHint" class="chat-header-bar__hint">
        {{ paperHint }}
      </p>
      <p v-else class="chat-header-bar__hint">暂未关联论文</p>
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

.chat-header-bar__content {
  min-width: 0;
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

.chat-header-bar__hint {
  margin-top: 3px;
  overflow: hidden;
  color: var(--color-text-muted);
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
