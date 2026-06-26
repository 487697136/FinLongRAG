# FinLongRAG Frontend

这是 FinLongRAG 的 Vue 前端工程，基于 `amsrag-web/frontend` 迁移并适配当前 FastAPI 后端。

## 技术栈

- Vue 3
- JavaScript
- Vite
- Naive UI
- Pinia
- Vue Router
- Axios

## 目录说明

```text
frontend/
  public/                  静态资源，例如 favicon 和 logo。
  src/api/                 Axios 实例、认证、知识库、文档、会话和评测 API。
  src/assets/              全局 CSS、基础样式和设计变量。
  src/components/          通用组件、布局组件和聊天组件。
  src/composables/         组合式逻辑，例如聊天滚动和 Markdown 渲染。
  src/router/              前端路由。
  src/stores/              Pinia 状态管理。
  src/theme/               Naive UI 主题配置。
  src/utils/               格式化和辅助函数。
  src/views/               登录、问答、知识库、文档、评测、图谱和设置页面。
  index.html               Vite HTML 入口。
  package.json             前端依赖和脚本。
  package-lock.json        npm 锁定文件。
  vite.config.js           Vite 配置和开发代理。
```

## 开发运行

后端默认运行在 `http://127.0.0.1:7860`。

```powershell
cd E:\课程项目\short_term\FinLongRAG\frontend
npm install
npm run dev
```

如果后端端口不同：

```powershell
$env:VITE_API_PROXY_TARGET="http://127.0.0.1:8000"
npm run dev
```

## 构建

```powershell
cd E:\课程项目\short_term\FinLongRAG\frontend
npm run build
```

构建产物输出到 `frontend/dist/`。该目录是生成产物，不提交 GitHub。生产或演示时，后端会挂载 `frontend/dist/` 作为单页应用。

## 启动方式约定

项目统一使用根目录的一键启动脚本：

```powershell
cd E:\课程项目\short_term\FinLongRAG
.\start.bat
```

旧的前端独立启动脚本已删除，避免和根目录启动流程冲突。
