<script setup lang="ts">
import { ref } from "vue";
import { useRouter } from "vue-router";
import { ElMessage } from "element-plus";
import { useAuth } from "../composables/useAuth";
import { toErrorMessage } from "../utils/error";

const router = useRouter();
const { loginUser, registerUser } = useAuth();

const username = ref("");
const password = ref("");
const isRegister = ref(false);
const submitting = ref(false);

async function submit(): Promise<void> {
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
    await router.push({ name: "chat" });
  } catch (error: unknown) {
    ElMessage.error(toErrorMessage(error, "操作失败"));
  } finally {
    submitting.value = false;
  }
}

function toggleMode(): void {
  isRegister.value = !isRegister.value;
}
</script>

<template>
  <div class="login-view">
    <section class="login-view__card">
      <header class="login-view__header">
        <span class="login-view__mark" aria-hidden="true">SP</span>
        <h1 class="login-view__title">SciPal</h1>
        <p class="login-view__subtitle">学术论文阅读助手 · 让引用可追溯</p>
      </header>

      <el-form class="login-view__form" @submit.prevent="submit">
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
            class="login-view__submit"
            @click="submit"
          >
            {{ isRegister ? "注册并进入" : "登录" }}
          </el-button>
        </el-form-item>
      </el-form>

      <p class="login-view__toggle">
        {{ isRegister ? "已有账号？" : "没有账号？" }}
        <a href="#" @click.prevent="toggleMode">
          {{ isRegister ? "去登录" : "去注册" }}
        </a>
      </p>
    </section>
  </div>
</template>

<style scoped>
.login-view {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  background:
    radial-gradient(circle at 18% 22%, rgba(71, 110, 230, 0.12), transparent 42%),
    radial-gradient(circle at 82% 78%, rgba(18, 166, 154, 0.1), transparent 46%), var(--color-page);
}

.login-view__card {
  width: 380px;
  padding: 40px;
  background: var(--color-panel);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  box-shadow: var(--shadow-card);
}

.login-view__header {
  margin-bottom: 28px;
  text-align: center;
}

.login-view__mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  margin-bottom: 14px;
  font-family: var(--font-mono);
  font-size: 14px;
  letter-spacing: 0.06em;
  color: var(--color-white);
  background: var(--gradient-accent);
  border-radius: 12px;
}

.login-view__title {
  margin: 0 0 6px;
  font-size: 26px;
  letter-spacing: -0.01em;
  color: var(--color-text);
}

.login-view__subtitle {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-muted);
}

.login-view__submit {
  width: 100%;
}

.login-view__toggle {
  margin: 0;
  font-size: 13px;
  text-align: center;
  color: var(--color-text-muted);
}

.login-view__toggle a {
  color: var(--color-accent);
  text-decoration: none;
}
</style>
