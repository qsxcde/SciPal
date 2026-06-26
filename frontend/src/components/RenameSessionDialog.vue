<script setup lang="ts">
import { nextTick, ref, watch } from "vue";
import type { FormInstance, FormRules } from "element-plus";

const props = defineProps<{
  initialTitle: string;
  visible: boolean;
}>();

const emit = defineEmits<{
  close: [];
  submit: [title: string];
  "update:visible": [value: boolean];
}>();

type RenameFormModel = {
  title: string;
};

const formRef = ref<FormInstance>();
const formModel = ref<RenameFormModel>({
  title: "",
});

const formRules: FormRules<RenameFormModel> = {
  title: [
    {
      required: true,
      message: "请输入会话名称",
      trigger: "blur",
    },
    {
      min: 1,
      max: 80,
      message: "会话名称长度需在 1 到 80 个字符之间",
      trigger: "blur",
    },
    {
      validator: (_rule, value: string, callback) => {
        if (value.trim().length === 0) {
          callback(new Error("请输入会话名称"));
          return;
        }
        callback();
      },
      trigger: "blur",
    },
  ],
};

watch(
  () => props.visible,
  async (visible) => {
    if (!visible) {
      return;
    }
    formModel.value.title = props.initialTitle;
    await nextTick();
    formRef.value?.clearValidate();
  },
  { immediate: true },
);

function closeDialog(): void {
  emit("update:visible", false);
  emit("close");
}

async function submit(): Promise<void> {
  const isValid = await formRef.value?.validate().catch(() => false);
  if (!isValid) {
    return;
  }
  emit("submit", formModel.value.title.trim());
  emit("update:visible", false);
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    title="重命名会话"
    width="420px"
    @close="closeDialog"
  >
    <el-form
      ref="formRef"
      :model="formModel"
      :rules="formRules"
      class="rename-dialog"
      label-position="top"
      @submit.prevent
    >
      <el-form-item
        label="会话名称"
        prop="title"
      >
        <el-input
          v-model="formModel.title"
          maxlength="80"
          placeholder="请输入会话名称"
          @keydown.enter.prevent="submit"
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="rename-dialog__footer">
        <el-button @click="closeDialog">
          取消
        </el-button>
        <el-button
          type="primary"
          @click="submit"
        >
          确认
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.rename-dialog {
  padding-top: 6px;
}

.rename-dialog :deep(.el-form-item) {
  margin-bottom: 0;
}

.rename-dialog :deep(.el-input__wrapper) {
  min-height: 42px;
  background: var(--color-surface);
  box-shadow: 0 0 0 1px var(--color-border) inset;
}

.rename-dialog__footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
