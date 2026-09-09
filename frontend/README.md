# 前端

React + TypeScript + Vite。完整启动说明见 [根目录 README](../README.md)。

需要 Node.js 24+。使用 `npm ci` 安装依赖，`npm run dev` 启动；`npm test`、`npm run lint`、`npm run build` 分别运行测试、检查和构建。

API 客户端位于 src/api，src/api.ts 保持对页面的统一导出。流式传输测试直接导入客户端代码，通过模拟网络验证协议边界，不访问真实模型。
