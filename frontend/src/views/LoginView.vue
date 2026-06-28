<script setup lang="ts">
import { ref } from "vue";
import { ElMessage } from "element-plus";
import { useAuth } from "../composables/useAuth";

const { loginUser, registerUser } = useAuth();

const username = ref("");
const password = ref("");
const isRegister = ref(false);
const submitting = ref(false);

async function submit() {
  if (!username.value.trim() || !password.value) {
    ElMessage.warning("请输入用户名和密码");
    return;
  }
  submitting.value = true;
  try {
    if (isRegister.value) {
      await registerUser(username.value.trim(), password.value);
    } else {
      await loginUser(username.value.trim(), password.value);
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : "操作失败";
    ElMessage.error(msg);
  } finally {
    submitting.value = false;
  }
}

function toggleMode() {
  isRegister.value = !isRegister.value;
}
</script>

<template>
  <div class="login-container">
    <div class="login-card">
      <h1 class="login-title">SciPal</h1>
      <p class="login-subtitle">学术论文阅读助手</p>
      <el-form @submit.prevent="submit">
        <el-form-item>
          <el-input
            v-model="username"
            placeholder="用户名"
            :disabled="submitting"
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="password"
            type="password"
            placeholder="密码"
            :disabled="submitting"
            show-password
            @keyup.enter="submit"
          />
        </el-form-item>
        <el-form-item>
          <el-button
            type="primary"
            :loading="submitting"
            class="submit-btn"
            @click="submit"
          >
            {{ isRegister ? "注册" : "登录" }}
          </el-button>
        </el-form-item>
      </el-form>
      <p class="toggle-text">
        {{ isRegister ? "已有账号？" : "没有账号？" }}
        <a href="#" @click.prevent="toggleMode">
          {{ isRegister ? "去登录" : "去注册" }}
        </a>
      </p>
    </div>
  </div>
</template>

<style scoped>
.login-container {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background: #f5f7fa;
}
.login-card {
  width: 360px;
  padding: 40px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}
.login-title {
  text-align: center;
  margin: 0 0 4px;
  font-size: 28px;
  color: #303133;
}
.login-subtitle {
  text-align: center;
  margin: 0 0 28px;
  font-size: 14px;
  color: #909399;
}
.submit-btn {
  width: 100%;
}
.toggle-text {
  text-align: center;
  font-size: 13px;
  color: #909399;
  margin: 0;
}
</style>
