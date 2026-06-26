<template>
  <div class="login-page">
    <section class="brand">
      <div class="brand__mark">
        <n-icon :component="GitNetworkOutline" size="42" />
      </div>
      <h1>FinLongRAG</h1>
      <p>面向金融长文本的 Agentic RAG 问答与服务系统</p>
      <div class="brand__features">
        <span>结构化文档解析</span>
        <span>混合检索与证据引用</span>
        <span>持续对话与评测闭环</span>
      </div>
    </section>

    <n-card class="login-card" :bordered="false">
      <div class="login-card__header">
        <h2>登录系统</h2>
        <p>本地开发默认账号：admin / finlongrag</p>
      </div>

      <n-tabs v-model:value="activeTab" type="segment" animated>
        <n-tab-pane name="login" tab="登录">
          <n-form
            ref="loginFormRef"
            :model="loginForm"
            :rules="loginRules"
            size="large"
            class="form"
          >
            <n-form-item path="username">
              <n-input
                v-model:value="loginForm.username"
                placeholder="用户名或邮箱"
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
                @keyup.enter="handleLogin"
              >
                <template #prefix>
                  <n-icon :component="LockClosedOutline" />
                </template>
              </n-input>
            </n-form-item>
            <n-button type="primary" size="large" block :loading="loading" @click="handleLogin">
              登录
            </n-button>
          </n-form>
        </n-tab-pane>

        <n-tab-pane name="register" tab="注册">
          <n-form
            ref="registerFormRef"
            :model="registerForm"
            :rules="registerRules"
            size="large"
            class="form"
          >
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
                placeholder="密码，至少 6 位"
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
            <n-button type="primary" size="large" block :loading="loading" @click="handleRegister">
              注册
            </n-button>
          </n-form>
        </n-tab-pane>
      </n-tabs>
    </n-card>
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
.login-page {
  min-height: 100vh;
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) 420px;
  align-items: center;
  gap: 64px;
  padding: 48px clamp(24px, 7vw, 96px);
  background:
    radial-gradient(circle at 15% 20%, rgba(37, 99, 235, 0.22), transparent 34%),
    linear-gradient(135deg, #0f172a 0%, #1e3a8a 48%, #2563eb 100%);
}

.brand {
  color: #fff;
}

.brand__mark {
  width: 84px;
  height: 84px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.22);
  box-shadow: 0 24px 80px rgba(15, 23, 42, 0.28);
}

.brand h1 {
  margin: 28px 0 12px;
  font-size: 52px;
  line-height: 1;
}

.brand p {
  margin: 0;
  max-width: 620px;
  font-size: 20px;
  line-height: 1.6;
  color: rgba(255, 255, 255, 0.86);
}

.brand__features {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 32px;
}

.brand__features span {
  padding: 9px 13px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.16);
  color: rgba(255, 255, 255, 0.9);
}

.login-card {
  border-radius: 8px;
  box-shadow: 0 28px 80px rgba(15, 23, 42, 0.28);
}

.login-card__header {
  margin-bottom: 22px;
}

.login-card__header h2 {
  margin: 0;
  font-size: 24px;
}

.login-card__header p {
  margin: 8px 0 0;
  color: #64748b;
}

.form {
  margin-top: 24px;
}

@media (max-width: 900px) {
  .login-page {
    grid-template-columns: 1fr;
    gap: 28px;
    padding: 28px 18px;
  }

  .brand h1 {
    font-size: 38px;
  }

  .brand p {
    font-size: 16px;
  }
}
</style>
