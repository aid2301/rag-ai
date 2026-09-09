# rag-ai · 企业知识库问答系统

面向少量、高价值文档的非向量化 RAG：结合精确匹配、PostgreSQL pg_trgm 和 LLM 文档画像，让回答附带可追溯引用。

前端使用 React、TypeScript、Vite、Tailwind CSS；后端使用 Python、FastAPI、asyncpg 和 PostgreSQL 16。模型通过 OpenAI 兼容接口接入。

## 能力

- 导入 PDF、DOCX、TXT、Markdown、XLSX，按章节解析并生成文档画像。
- 小文档全文进入上下文，大文档按章节检索并扩展相邻证据。
- 支持 fast / standard / deep 模式、多轮对话、SSE 流式回答和引用溯源。
- 管理后台提供知识库、用户、用量、对话审计、问题反馈库和模型配置。
- 普通用户的对话与用量按账号隔离；知识库文档由管理员统一管理。

## 快速开始：Docker

需要 Docker Engine / Docker Desktop 和 Docker Compose v2。

1. 复制根目录的 `.env.example` 为 `.env`。
2. 在 `.env` 中填写 `PG_PASSWORD` 和 `ADMIN_PASSWORD`；模型参数可以稍后在后台填写。
3. 在项目根目录运行：

```bash
docker compose up -d --build
```

打开 <http://localhost:8000>；管理员入口为 <http://localhost:8000/#/admin>，账号为 `admin`，密码使用配置的 `ADMIN_PASSWORD`。

在后台配置模型、创建普通用户，并上传 `examples/documents/demo-guide.md`。使用普通用户账号提问“星桥项目什么时候演示？”，即可检查检索与引用。该示例全部为虚构资料。

## 本地开发

需要 Python 3.11+、Node.js 24+、PostgreSQL 16（可通过 Docker 启动）。

先按上方说明准备 `.env`，再运行：

```bash
docker compose up -d db
python -m venv .venv
```

激活环境：Windows PowerShell 使用 `.venv\Scripts\Activate.ps1`；macOS/Linux 使用 `source .venv/bin/activate`。

```bash
python -m pip install -r backend/requirements-dev.txt
npm --prefix frontend ci
python scripts/dev.py
```

前端 <http://localhost:5173>，后端 API 文档 <http://localhost:8000/docs>。

也可以用两个终端分别启动：

```bash
# 终端 1，项目根目录
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
# 终端 2，项目根目录
npm --prefix frontend run dev
```

根目录 `start-dev.bat` 和 `start.sh` 是开发启动脚本的快捷入口。

## 目录

```text
backend/
  app/
    api/routes/         HTTP 接口和权限检查
    core/               配置、认证、日志
    db/                 连接池、适配器、表结构、迁移
    prompts/            模型提示词
    schemas/            API 数据模型
    services/           文档、检索、RAG、LLM、用户等业务逻辑
  tests/                自动化测试与专用数据库工具
frontend/
  src/
    api/                按领域拆分的 API 客户端和 SSE 解码
    api.ts              兼容导出入口
    components/         通用组件和聊天组件
    pages/              用户与管理页面
  tests/                直接调用生产 API 模块的流式测试
scripts/                开发启动、评估
examples/               虚构文档与评估集
docs/                   架构、开发和部署指南
.github/                GitHub Actions 模板（见目录说明）
```

运行数据放在 `data/`，不进入版本控制。配置以 `.env.example` 为准；更多说明见 [架构](docs/architecture.md)、[开发指南](docs/development.md)、[Docker 部署](docs/deployment/docker.md)、[Windows 服务](docs/deployment/windows.md)。

## 测试与评估

数据库测试使用独立的临时 PostgreSQL，端口 55433，与应用数据库分离：

```bash
docker compose -f compose.test.yml up -d --wait
cd backend
python -m pytest -q
cd ../frontend
npm test
npm run lint
npm run build
cd ..
docker compose -f compose.test.yml down
```

测试库必须以 `_test` 结尾；可通过 `TEST_DATABASE_URL` 指定专用测试实例。测试会清空该测试库的 public schema，禁止指向需要保留的数据。自动测试不调用真实 LLM。

导入示例资料并配置模型后，可以运行真实模型评估：

```bash
python scripts/evaluate.py --mode fast
```

这会调用所配置的模型并产生 Token 用量，输出 `eval_report.json`。指标基于关键词与来源命中，仅用于回归比较；缺失信息的拒答质量仍需人工核验。原 `python evaluate.py` 入口仍然可用。

## 贡献与许可证

欢迎提交 Issue 与 Pull Request，参见 [贡献指南](CONTRIBUTING.md)。项目使用 [MIT License](LICENSE)。
