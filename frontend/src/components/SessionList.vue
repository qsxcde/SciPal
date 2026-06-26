<script setup lang="ts">
import SessionListItem from "./SessionListItem.vue";
import type { SidebarSessionItem } from "../types";

defineProps<{
  collapsed: boolean;
  items: SidebarSessionItem[];
}>();

defineEmits<{
  deleteSession: [sessionId: string];
  pinSession: [sessionId: string];
  renameSession: [sessionId: string];
  selectSession: [sessionId: string];
}>();
</script>

<template>
  <el-scrollbar class="session-list">
    <div class="session-list__content">
      <SessionListItem
        v-for="item in items"
        :id="item.id"
        :key="item.id"
        :active="item.active"
        :collapsed="collapsed"
        :is-pinned="item.isPinned"
        :title="item.title"
        :description="item.description"
        @delete="$emit('deleteSession', $event)"
        @pin="$emit('pinSession', $event)"
        @rename="$emit('renameSession', $event)"
        @select="$emit('selectSession', $event)"
      />
      <p
        v-if="items.length === 0"
        class="session-list__empty"
      >
        {{ collapsed ? "暂无会话" : "暂无最近会话" }}
      </p>
    </div>
  </el-scrollbar>
</template>

<style scoped>
.session-list {
  min-height: 0;
  flex: 1;
}

.session-list__content {
  display: flex;
  min-height: 100%;
  flex-direction: column;
  gap: 10px;
  padding-right: 4px;
}

.session-list__empty {
  margin: 8px 0 0;
  color: #899a90;
  font-size: 12px;
  text-align: center;
}
</style>
