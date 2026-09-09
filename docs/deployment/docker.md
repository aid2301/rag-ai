# Docker 部署

从项目根目录复制 `.env.example` 到 `.env`，填写数据库与管理员密码，再执行：

```bash
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 kb
```

访问 `http://localhost:8000`。Compose 默认只绑定宿主机回环地址；局域网访问可在 `.env` 设置 `HOST=0.0.0.0`，并按实际需求配置防火墙与 HTTPS 反向代理。

数据库使用 PostgreSQL 16，pg_trgm 扩展由启动过程创建。Compose 的 kb 服务固定连接 db:5432，使用 PG_* 配置，忽略 `.env` 中的 DATABASE_URL。

## 持久化

- `pgdata` Docker 卷：用户、会话、知识库索引、问题反馈和模型设置。
- `./data`：上传文档与自动生成的签名密钥。

备份时同时保存数据库、data 目录和 `.env`，这些内容可能包含敏感资料。已有数据库卷的密码不会因修改 PG_PASSWORD 自动变化，升级既有部署时保持原密码，或通过数据库管理流程更改。

## 更新与停止

```bash
docker compose up -d --build
docker compose down
```

停止命令保留持久卷。更新前备份，启动日志中检查迁移结果与 `/api/health` 的数据库连接状态。

## 构建

Dockerfile 使用 Node.js 24 构建前端、Python 3.11 运行后端。镜像只复制后端应用和前端构建产物；`.dockerignore` 使用允许列表，避免把环境文件、数据库、内部材料和缓存发送到构建上下文。

## 测试服务

`compose.test.yml` 是独立、可销毁的测试数据库，使用临时文件系统，停止删除容器后不保留测试数据。不要将它作为生产数据库。
