<template>
  <div class="login-page">
    <!-- Decorative background elements -->
    <div class="login-page__bg-glow login-page__bg-glow--1" />
    <div class="login-page__bg-glow login-page__bg-glow--2" />
    <div class="login-page__bg-grid" />

    <section class="brand">
      <div class="brand__mark">
        <div class="brand__mark-inner">
          <n-icon :component="GitNetworkOutline" size="44" />
        </div>
      </div>
      <h1 class="brand__title">FinLongRAG</h1>
      <p class="brand__desc">面向金融长文本的 Agentic RAG 问答与服务系统</p>
      <div class="brand__features">
        <div class="brand__feature-item">
          <div class="brand__feature-dot" />
          <span>结构化文档解析</span>
        </div>
        <div class="brand__feature-item">
          <div class="brand__feature-dot" />
          <span>混合检索与证据引用</span>
        </div>
        <div class="brand__feature-item">
          <div class="brand__feature-dot" />
          <span>持续对话与评测闭环</span>
        </div>
      </div>
    </section>

    <div class="login-card-wrap fade-in-up">
      <n-card class="login-card glass-card" :bordered="false">
        <div class="login-card__header">
          <div class="login-card__header-icon">
            <n-icon :component="activeTab === 'login' ? LockClosedOutline : PersonOutline" size="22" />
          </div>
          <div>
            <h2 class="login-card__title">{{ activeTab === 'login' ? '欢迎回来' : '创建账号' }}</h2>
            <p class="login-card__subtitle">{{ activeTab === 'login' ? '请登录以继续使用系统' : '注册新账号以开始使用' }}</p>
          </div>
        </div>

        <n-tabs v-model:value="activeTab" type="segment" animated class="login-tabs">
          <n-tab-pane name="login" tab="登录">
            <n-form
              ref="loginFormRef"
              :model="loginForm"
              :rules="loginRules"
              size="large"
              class="login-form"
            >
              <n-form-item path="username">
                <n-input
                  v-model:value="loginForm.username"
                  placeholder="用户名或邮箱"
                  :input-props="{ autocomplete: 'username' }"
                  @keyup.enter="handleLogin"
                >
                  <template #prefix>
                    <n-icon :component="PersonOutline" />
                  </template>
                </n-input>
              </n-form-item>
              <n-form-item path="password">
                <n-input
                  v-model:value="loginForm.password"
                  type="password"
                  show-password-on="click"
                  placeholder="密码"
                  :input-props="{ autocomplete: 'current-password' }"
                  @keyup.enter="handleLogin"
                >
                  <template #prefix>
                    <n-icon :component="LockClosedOutline" />
                  </template>
                </n-input>
              </n-form-item>
              <button type="button" class="login-btn" :disabled="loading" @click="handleLogin">
                <span v-if="!loading">登 录</span>
                <span v-else class="login-btn__spinner" />
              </button>
              <p class="login-form__hint">本地开发默认账号：admin / finlongrag</p>
            </n-form>
          </n-tab-pane>

          <n-tab-pane name="register" tab="注册">
            <n-form
              ref="registerFormRef"
              :model="registerForm"
              :rules="registerRules"
              size="large"
              class="login-form"
            >
              <div class="register-grid">
                <n-form-item path="username">
                  <n-input v-model:value="registerForm.username" placeholder="用户名" :input-props="{ autocomplete: 'username' }">
                    <template #prefix>
                      <n-icon :component="PersonOutline" />
                    </template>
                  </n-input>
                </n-form-item>
                <n-form-item path="email">
                  <n-input v-model:value="registerForm.email" placeholder="邮箱" :input-props="{ autocomplete: 'email' }">
                    <template #prefix>
                      <n-icon :component="MailOutline" />
                    </template>
                  </n-input>
                </n-form-item>
                <n-form-item path="password">
                  <n-input
                    v-model:value="registerForm.password"
                    type="password"
                    show-password-on="click"
                    placeholder="密码，至少 6 位"
                    :input-props="{ autocomplete: 'new-password' }"
                  >
                    <template #prefix>
                      <n-icon :component="LockClosedOutline" />
                    </template>
                  </n-input>
                </n-form-item>
                <n-form-item path="confirmPassword">
                  <n-input
                    v-model:value="registerForm.confirmPassword"
                    type="password"
                    show-password-on="click"
                    placeholder="确认密码"
                    :input-props="{ autocomplete: 'new-password' }"
                    @keyup.enter="handleRegister"
                  >
                    <template #prefix>
                      <n-icon :component="LockClosedOutline" />
                    </template>
                  </n-input>
                </n-form-item>
              </div>
              <button type="button" class="login-btn" :disabled="loading" @click="handleRegister">
                <span v-if="!loading">注 册</span>
                <span v-else class="login-btn__spinner" />
              </button>
            </n-form>
          </n-tab-pane>
        </n-tabs>
      </n-card>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  NButton,
  NCard,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NTabPane,
  NTabs,
  useMessage
} from 'naive-ui'
import {
  GitNetworkOutline,
  LockClosedOutline,
  MailOutline,
  PersonOutline
} from '@vicons/ionicons5'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const message = useMessage()
const authStore = useAuthStore()

const activeTab = ref('login')
const loading = ref(false)
const loginFormRef = ref(null)
const registerFormRef = ref(null)

const loginForm = ref({
  username: 'admin',
  password: 'finlongrag'
})

const registerForm = ref({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

const loginRules = {
  username: [{ required: true, message: '请输入用户名或邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}

const registerRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' },
    { min: 3, max: 20, message: '用户名长度应为 3-20 个字符', trigger: 'blur' }
  ],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '请输入有效邮箱', trigger: 'blur' }
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少 6 个字符', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule, value) => value === registerForm.value.password,
      message: '两次输入的密码不一致',
      trigger: 'blur'
    }
  ]
}

async function handleLogin() {
  try {
    await loginFormRef.value?.validate()
    loading.value = true
    await authStore.login(loginForm.value.username, loginForm.value.password)
    message.success('登录成功')
    const redirect = router.currentRoute.value.query.redirect
    router.push(typeof redirect === 'string' && redirect.startsWith('/') ? redirect : '/')
  } catch (error) {
    if (!error.errors) {
      message.error(error.response?.data?.detail || error.message || '登录失败')
    }
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  try {
    await registerFormRef.value?.validate()
    loading.value = true
    await authStore.register(registerForm.value.username, registerForm.value.email, registerForm.value.password)
    message.success('注册成功，请登录')
    activeTab.value = 'login'
    loginForm.value.username = registerForm.value.username
    loginForm.value.password = ''
  } catch (error) {
    if (!error.errors) {
      message.error(error.response?.data?.detail || error.message || '注册失败')
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
/* ─── Page shell ─── */
.login-page {
  position: relative;
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 460px;
  align-items: center;
  gap: 80px;
  padding: 48px clamp(24px, 8vw, 100px);
  background: linear-gradient(135deg, #0b1121 0%, #142454 35%, #1e3a8a 65%, #2563eb 100%);
  overflow: hidden;
}

/* ─── Decorative background ─── */
.login-page__bg-glow {
  position: absolute;
  border-radius: 50%;
  pointer-events: none;
}

.login-page__bg-glow--1 {
  top: -18%;
  left: -8%;
  width: 620px;
  height: 620px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.22) 0%, transparent 68%);
}

.login-page__bg-glow--2 {
  bottom: -12%;
  right: -6%;
  width: 480px;
  height: 480px;
  background: radial-gradient(circle, rgba(96, 165, 250, 0.16) 0%, transparent 66%);
}

.login-page__bg-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
  background-size: 60px 60px;
  pointer-events: none;
}

/* ─── Brand (left) ─── */
.brand {
  position: relative;
  z-index: 1;
  color: #fff;
}

.brand__mark {
  margin-bottom: 32px;
}

.brand__mark-inner {
  width: 88px;
  height: 88px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 20px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.18), rgba(255, 255, 255, 0.06));
  border: 1px solid rgba(255, 255, 255, 0.24);
  box-shadow: 0 24px 64px rgba(59, 130, 246, 0.32);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  color: #93c5fd;
}

.brand__title {
  margin: 0 0 16px;
  font-size: 54px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -0.5px;
  background: linear-gradient(135deg, #ffffff 0%, #bfdbfe 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.brand__desc {
  margin: 0;
  max-width: 580px;
  font-size: 19px;
  line-height: 1.65;
  color: rgba(255, 255, 255, 0.82);
}

.brand__features {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 36px;
}

.brand__feature-item {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 10px 18px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.10);
  border: 1px solid rgba(255, 255, 255, 0.14);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
  color: rgba(255, 255, 255, 0.92);
  font-size: 13.5px;
  font-weight: 500;
  transition: background 0.22s ease, border-color 0.22s ease;
}

.brand__feature-item:hover {
  background: rgba(255, 255, 255, 0.16);
  border-color: rgba(255, 255, 255, 0.24);
}

.brand__feature-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #60a5fa;
  box-shadow: 0 0 8px rgba(96, 165, 250, 0.6);
  flex-shrink: 0;
}

/* ─── Card (right) ─── */
.login-card-wrap {
  position: relative;
  z-index: 1;
}

.login-card {
  border-radius: 20px;
  box-shadow: var(--shadow-login-card);
  padding: 36px 32px 32px;
}

.login-card__header {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 24px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-color);
}

.login-card__header-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: 12px;
  background: linear-gradient(135deg, var(--brand-100), var(--brand-200));
  color: var(--brand-600);
  flex-shrink: 0;
}

.login-card__title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-1);
}

.login-card__subtitle {
  margin: 3px 0 0;
  font-size: 13.5px;
  color: var(--text-4);
}

/* ─── Tabs ─── */
.login-tabs {
  --n-tab-font-size: 15px;
}

/* ─── Form ─── */
.login-form {
  margin-top: 8px;
}

.login-form :deep(.n-form-item) {
  --n-feedback-font-size: 12px;
  margin-bottom: 18px;
}

.login-form :deep(.n-form-item:last-of-type) {
  margin-bottom: 6px;
}

.login-form__hint {
  margin: 12px 0 0;
  font-size: 12.5px;
  color: var(--text-5);
  text-align: center;
}

/* ─── Register grid ─── */
.register-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 14px;
}

.register-grid :deep(.n-form-item) {
  margin-bottom: 16px;
}

@media (max-width: 480px) {
  .register-grid {
    grid-template-columns: 1fr;
  }
}

/* ─── Custom gradient button ─── */
.login-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 46px;
  margin-top: 4px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 50%, #1e40af 100%);
  color: #fff;
  font-size: 15.5px;
  font-weight: 600;
  letter-spacing: 2px;
  cursor: pointer;
  transition: all 0.24s ease;
  box-shadow: 0 6px 24px rgba(37, 99, 235, 0.32);
}

.login-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 12px 32px rgba(37, 99, 235, 0.44);
}

.login-btn:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: 0 4px 12px rgba(37, 99, 235, 0.28);
}

.login-btn:disabled {
  opacity: 0.65;
  cursor: not-allowed;
  transform: none;
  box-shadow: 0 4px 16px rgba(37, 99, 235, 0.18);
}

.login-btn__spinner {
  width: 20px;
  height: 20px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: login-spin 0.7s linear infinite;
}

@keyframes login-spin {
  to { transform: rotate(360deg); }
}

/* ─── Responsive ─── */
@media (max-width: 960px) {
  .login-page {
    grid-template-columns: 1fr;
    gap: 32px;
    padding: 36px 20px;
  }

  .brand__title {
    font-size: 40px;
  }

  .brand__desc {
    font-size: 16px;
  }

  .brand__features {
    gap: 10px;
    margin-top: 24px;
  }

  .brand__feature-item {
    font-size: 12.5px;
    padding: 8px 14px;
  }

  .login-card {
    padding: 28px 22px 24px;
  }
}
</style>
