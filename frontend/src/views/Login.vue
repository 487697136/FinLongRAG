<template>
  <div class="login-page">
    <div class="login-page__bg-glow login-page__bg-glow--1" />
    <div class="login-page__bg-glow login-page__bg-glow--2" />
    <div class="login-page__bg-grid" />

    <div class="login-grid fade-in-up">
      <!-- Brand (left) -->
      <section class="login-brand">
        <div class="login-brand__icon">
          <n-icon :component="GitNetworkOutline" size="44" />
        </div>
        <div class="login-brand__eyebrow">金融研究智能工作台</div>
        <h1 class="login-brand__title">FinLongRAG</h1>
        <p class="login-brand__desc">基于 Agentic RAG 的<br/>面向金融长文本的智能问答与知识服务系统</p>
      </section>

      <!-- Card (right) -->
      <n-card class="login-card glass-card" :bordered="false">
        <!-- Header -->
        <div class="login-card__header">
          <div class="login-card__header-icon">
            <n-icon :component="activeTab === 'login' ? LockClosedOutline : PersonOutline" size="24" />
          </div>
          <div>
            <h2 class="login-card__title">{{ activeTab === 'login' ? '进入 FinLongRAG' : '创建账号' }}</h2>
            <p class="login-card__subtitle">{{ activeTab === 'login' ? '登录后进入金融文档问答与知识服务工作台' : '注册后即可开始构建金融知识库与问答会话' }}</p>
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
                  placeholder="用户名或邮箱地址"
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
                  <n-input v-model:value="registerForm.username" placeholder="用户名">
                    <template #prefix>
                      <n-icon :component="PersonOutline" />
                    </template>
                  </n-input>
                </n-form-item>
                <n-form-item path="email">
                  <n-input v-model:value="registerForm.email" placeholder="邮箱">
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
                    placeholder="设置登录密码（至少6位）"
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
/* ─── Page ─── */
.login-page {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  background: linear-gradient(135deg, #0b1121 0%, #142454 35%, #1e3a8a 65%, #2563eb 100%);
  overflow: hidden;
}

/* ─── Decorations ─── */
.login-page__bg-glow {
  position: absolute;
  border-radius: 50%;
  pointer-events: none;
}
.login-page__bg-glow--1 {
  top: -15%;
  left: -5%;
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.20) 0%, transparent 68%);
}
.login-page__bg-glow--2 {
  bottom: -10%;
  right: -5%;
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba(96, 165, 250, 0.14) 0%, transparent 66%);
}
.login-page__bg-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255,255,255,0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,0.02) 1px, transparent 1px);
  background-size: 60px 60px;
  pointer-events: none;
}

/* ─── Grid: left brand + right card, centered ─── */
.login-grid {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 500px 520px;
  gap: 72px;
  align-items: center;
}

/* ─── Brand (left) ─── */
.login-brand {
  color: #fff;
}

.login-brand__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 80px;
  height: 80px;
  border-radius: 20px;
  background: linear-gradient(135deg, rgba(255,255,255,0.18), rgba(255,255,255,0.06));
  border: 1px solid rgba(255,255,255,0.24);
  color: #93c5fd;
  margin-bottom: 28px;
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  box-shadow: 0 20px 60px rgba(59, 130, 246, 0.30);
}

.login-brand__title {
  margin: 0 0 20px;
  font-size: 52px;
  font-weight: 800;
  line-height: 1;
  letter-spacing: -1px;
  background: linear-gradient(135deg, #ffffff 0%, #bfdbfe 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
}

.login-brand__desc {
  margin: 0 0 28px;
  font-size: 18px;
  line-height: 1.65;
  color: rgba(255,255,255,0.80);
}

.login-brand__features {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 28px;
}

.login-brand__tag {
  padding: 8px 16px;
  border-radius: 999px;
  background: rgba(255,255,255,0.10);
  border: 1px solid rgba(255,255,255,0.14);
  color: rgba(255,255,255,0.88);
  font-size: 13px;
  font-weight: 500;
}

.login-brand__metrics {
  display: grid;
  gap: 14px;
}

.login-brand__metric {
  padding: 16px 18px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(255,255,255,0.10), rgba(255,255,255,0.05));
  border: 1px solid rgba(255,255,255,0.12);
  box-shadow: 0 16px 36px rgba(15, 23, 42, 0.16);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}

.login-brand__metric strong {
  display: block;
  margin-bottom: 6px;
  font-size: 15px;
  font-weight: 700;
  color: #ffffff;
}

.login-brand__metric span {
  display: block;
  font-size: 13px;
  line-height: 1.7;
  color: rgba(255,255,255,0.74);
}

/* ─── Card (right) ─── */
.login-card {
  border-radius: 20px;
  box-shadow: 0 32px 80px rgba(15, 23, 42, 0.38);
  padding: 40px 36px 32px;
  background: linear-gradient(180deg, #ffffff 0%, #f2f6fc 100%);
  border: 1px solid rgba(219, 227, 240, 0.6);
}
.login-card :deep(.n-card__content) {
  padding: 0 !important;
}

.login-card__header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 28px;
  padding-bottom: 24px;
  border-bottom: 1px solid var(--border-color);
}

.login-card__header-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 50px;
  height: 50px;
  border-radius: 14px;
  background: linear-gradient(135deg, var(--brand-100), var(--brand-200));
  color: var(--brand-600);
  flex-shrink: 0;
}

.login-card__title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: var(--text-1);
}

.login-card__subtitle {
  margin: 4px 0 0;
  font-size: 14px;
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
  margin-bottom: 20px;
}

.login-form :deep(.n-form-item:last-of-type) {
  margin-bottom: 8px;
}

.login-form :deep(.n-input) {
  --n-height: 46px;
  --n-font-size: 14px;
}

/* ─── Register grid ─── */
.register-grid {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.register-grid :deep(.n-form-item) {
  margin-bottom: 0;
}
.register-grid {
  margin-bottom: 20px;
}
.register-grid :deep(.n-form-item .n-form-item-label) {
  display: none;
}
.register-grid :deep(.n-input) {
  --n-height: 32px;
  --n-font-size: 13px;
}
.register-grid :deep(.n-form-item-feedback-wrapper) {
  display: none;
}

/* ─── Login button ─── */
.login-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 50px;
  border: none;
  border-radius: 12px;
  background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 50%, #1e40af 100%);
  color: #fff;
  font-size: 16px;
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
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: login-spin 0.7s linear infinite;
}
@keyframes login-spin { to { transform: rotate(360deg); } }

/* ─── Responsive ─── */
@media (max-width: 1080px) {
  .login-grid {
    grid-template-columns: 1fr;
    gap: 36px;
    max-width: 440px;
  }
  .login-brand {
    text-align: center;
  }
  .login-brand__icon,
  .login-brand__eyebrow {
    margin-left: auto;
    margin-right: auto;
  }
  .login-brand__title { font-size: 36px; }
  .login-brand__desc { font-size: 16px; }
  .login-card { padding: 28px 22px 24px; }
}
</style>
