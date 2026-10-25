<script setup lang="ts">
import { CopyDocument, RefreshRight, VideoPause } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";

const props = defineProps<{
  canRegenerate: boolean;
  content: string;
  isStreaming: boolean;
}>();

const emit = defineEmits<{
  regenerate: [];
  stop: [];
}>();

/**
 * Copies the assistant response into the system clipboard when available.
 */
async function handleCopy(): Promise<void> {
  const content = props.content.trim();
  if (!content) {
    ElMessage.warning("当前回答还没有可复制的内容。");
    return;
  }

  if (!navigator.clipboard?.writeText) {
    ElMessage.error("当前环境不支持复制，请手动选择内容。");
    return;
  }

  try {
    await navigator.clipboard.writeText(content);
    ElMessage.success("已复制回答内容。");
  } catch {
    ElMessage.error("复制失败，请稍后重试。");
  }
}
</script>

<template>
  <div class="message-actions">
    <el-button
      v-if="isStreaming"
      :icon="VideoPause"
      class="message-actions__button"
      text
      @click="emit('stop')"
    >
      停止生成
    </el-button>

    <template v-else>
      <el-button
        v-if="canRegenerate"
        :icon="RefreshRight"
        class="message-actions__button"
        text
        @click="emit('regenerate')"
      >
        重新生成
      </el-button>
      <el-button :icon="CopyDocument" class="message-actions__button" text @click="handleCopy">
        复制回答
      </el-button>
    </template>
  </div>
</template>

<style scoped>
.message-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.message-actions__button.el-button {
  padding: 0;
  color: var(--color-text-soft);
  font-size: 12px;
  font-weight: 600;
}

.message-actions__button.el-button:hover {
  color: var(--color-text);
}
</style>
