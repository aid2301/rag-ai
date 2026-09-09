# 开发指南

## 开发与测试

安装、启动和全量检查命令见 [README](../README.md)。开发服务默认使用 8000/5173，Vite 将 `/api` 代理到后端。若改后端端口，需要同步修改 Vite 代理。

自动测试通过临时目录隔离上传文件，并清空模型参数，避免测试意外调用真实接口。数据库测试使用 `compose.test.yml` 的 55433 端口；应用默认使用 55432。

无 Docker 时，可以手动准备 PostgreSQL 测试库 `kb_test`，允许测试用户创建 pg_trgm 扩展，然后设置 `TEST_DATABASE_URL`。

```powershell
$env:TEST_DATABASE_URL = 'postgresql://kb:kb@127.0.0.1:55433/kb_test'
cd backend
python -m pytest -q
```

每个数据库用例会重建该专用测试库的 public schema，不能并行运行共享同一测试库的测试进程。不使用应用的 DATABASE_URL 作为测试库地址。

不依赖 PostgreSQL 的检查可以先运行：

```bash
cd backend
python -m pytest -q tests/test_text.py tests/test_json_utils.py tests/test_document_parser.py tests/test_llm_usage.py tests/test_release_regressions.py
```

## 新增功能

- 新增表修改 schema_pg.py，既有库的字段升级同时加入 migrations.py。
- API 路由检查账号与资源归属，不依赖前端隐藏按钮来控制权限。
- 前端 API 按业务领域维护，兼容导出集中在 src/api.ts。
- 修改流式协议时同时更新 sse.ts 和 frontend/tests/chat.test.mjs。
- 评估脚本使用真实模型，自动化测试通过 mock 或启发式回退运行。

## 原项目材料

整理前的内部交接、验收脚本与业务样例保留在本机忽略目录 `docs/internal/`，不属于开源项目。运行数据、编辑器缓存和本地备份也不纳入公开提交。
