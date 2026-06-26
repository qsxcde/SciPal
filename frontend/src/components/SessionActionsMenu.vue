<script setup lang="ts">
type SessionActionCommand = "delete" | "pin" | "rename";

const emit = defineEmits<{
  delete: [];
  pin: [];
  rename: [];
}>();

defineProps<{
  isPinned: boolean;
}>();

function handleCommand(command: SessionActionCommand): void {
  if (command === "rename") {
    emit("rename");
    return;
  }
  if (command === "pin") {
    emit("pin");
    return;
  }
  if (command === "delete") {
    emit("delete");
  }
}
</script>

<template>
  <el-dropdown
    trigger="click"
    @command="handleCommand"
  >
    <span class="session-actions-menu__trigger">
      <slot />
    </span>
    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item command="rename">
          重命名
        </el-dropdown-item>
        <el-dropdown-item command="pin">
          {{ isPinned ? "取消置顶" : "置顶" }}
        </el-dropdown-item>
        <el-dropdown-item
          command="delete"
          divided
        >
          删除
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<style scoped>
.session-actions-menu__trigger {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
}
</style>
