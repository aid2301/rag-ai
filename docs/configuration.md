# 配置说明

[返回 README](../README.md) · [使用指南](usage.md) · [常见问题](troubleshooting.md)

## 配置从哪里读取

应用静态配置由 `backend/app/core/config.py` 加载，优先级为：

1. 进程环境变量。
2. `backend/.env` 中的同名配置。
3. 项目根目录 `.env`。
4. 代码默认值。

建议只维护根目录 `.env`，减少多处配置互相覆盖。`.env.example` 是部署模板，不含真实凭据，不代表所有代码默认值。

**运行时模型配置另有一层优先级：后台保存到数据库的值优先，未配置时才回退到上述静态配置。** Base URL、API Key、Model 的数据库空字符串会回退到环境默认值；在后台提交空 API Key 表示保持现有密钥，不是删除密钥。

修改后台模型设置后，后续模型调用会读取新的配置。修改 `.env` 后，手动部署需要重启后端；Compose 部署执行 `docker compose up -d` 以重新创建配置发生变化的服务，单纯 `docker compose restart` 不会重新注入环境变量。

## 数据库与管理员

| 变量 | 模板值 / 含义 |
| --- | --- |
| `ADMIN_PASSWORD` | 空，必须自行设置；管理员用户名固定为 `admin` |
| `PG_HOST` | `127.0.0.1`，本地开发连接的数据库地址 |
| `PG_PORT` | `55432`，Compose 将宿主机此端口映射到 PostgreSQL 的 5432 |
| `PG_USER` | `kb` |
| `PG_PASSWORD` | 空，Compose 要求设置 |
| `PG_DATABASE` | `kb` |
| `DATABASE_URL` | 空；非容器部署时，非空 DSN 优先于 PG_* 拼装的地址 |
| `SECRET_KEY` | 空；可设置固定签名密钥，否则自动保存到 `data/secret_key` |

Compose 的应用服务覆盖 `PG_HOST=db`、`PG_PORT=5432` 并清空 `DATABASE_URL`，保证应用连接同一 Compose 内的数据库。用户与数据库名称可以自定义，已有数据库卷不会因为修改环境变量而自动改名或修改密码。

代码为兼容已有本地使用保留了管理员空密码配置回退到 `admin123` 的行为，**不要依赖这个回退值部署**。按 `.env.example` 填写自己的密码；Compose 会强制检查该项。

保留 `SECRET_KEY` 或 `data/secret_key` 可让签名密钥在重启后保持一致。更换密钥会使已有登录令牌失效。管理员和普通用户使用不同类型的令牌，不能互换。

## 模型参数

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `LLM_BASE_URL` | 空 | OpenAI 兼容服务的基础地址，路径必须与服务端要求一致 |
| `LLM_API_KEY` | 空 | 访问该服务的凭据 |
| `LLM_MODEL` | 空 | 服务端实际提供的模型标识 |
| `LLM_TIMEOUT` | `60` | 单次请求超时，单位秒 |
| `LLM_TEMPERATURE` | `0.1` | 生成随机性参数 |
| `LLM_MAX_TOKENS` | `2048` | 默认最大输出 Token 数 |
| `DEFAULT_CHAT_MODE` | `auto` | `auto` / `fast` / `standard` / `deep` |
| `SHOW_THINKING` | `false` | 展示执行阶段与相关详情 |

优先通过后台“测试连接”确认 Base URL、Key 和 Model 的组合可用。兼容接口并不意味着所有服务都支持相同的参数、流式格式或上下文长度，连接测试通过后仍应使用虚构资料完成一次问答验证。

当前配置检查要求 Base URL、API Key、Model 都非空。对于确实不校验密钥的本地兼容服务，可以按该服务要求填写非空占位值；占位值不能用于需要真实凭据的远程服务。

导入时生成画像、查询理解、回答、证据校验和问题分组等步骤都可能调用模型。展示执行阶段本身不增加模型调用。

## 文档与检索参数

以下限制主要按字符数计算，不能直接等同于 Token 数。

| 变量 | 默认值 | 作用 |
| --- | --- | --- |
| `MAX_UPLOAD_SIZE_MB` | `50` | 单文件上传大小上限 |
| `FULL_DOCUMENT_MAX_CHARS` | `12000` | 小于或等于该值的选中文档采用全文上下文策略 |
| `CONTEXT_BUDGET_CHARS` | `28000` | 合并证据正文的总字符预算，仍可能截断全文 |
| `SECTION_MAX_CHARS` | `4000` | 超长章节进一步拆分的阈值 |
| `MAX_SELECTED_DOCUMENTS` | `5` | 文档选择阶段的数量限制；fast 模式另有固定候选数量 |
| `MAX_RERANK_SECTIONS` | `20` | 重排阶段的候选数量限制 |
| `TOP_SECTIONS_AFTER_RERANK` | `8` | 用于组织上下文的主要章节数量 |
| `NEIGHBOR_RADIUS` | `1` | 相邻章节扩展半径；扩展还会考虑同父章节 |

先使用默认值验证资料质量与引用，再按样本调整。提高上下文预算不一定改善回答，也可能增加费用、延迟或超过模型的上下文限制。

## 监听地址、跨域与调试

| 变量 | `.env.example` 中的值 | 说明 |
| --- | --- | --- |
| `HOST` | `127.0.0.1` | Compose 的宿主机绑定地址；容器内部仍监听 0.0.0.0 |
| `PORT` | `8000` | Compose 的宿主机端口，容器内部固定为 8000 |
| `CORS_ORIGINS` | localhost / 127.0.0.1 的 5173 地址 | 逗号分隔的允许来源 |
| `DEBUG` | `false` | 是否返回或记录部分调试追踪信息 |

`HOST` / `PORT` 不会覆盖你手动运行 uvicorn 时传入的命令行参数；`scripts/dev.py` 固定使用开发端口。Vite 自身的监听地址在 `frontend/vite.config.ts` 配置。

局域网部署可将 Compose 的 `HOST` 调整为 `0.0.0.0`，再按实际部署地址设置防火墙、反向代理和跨域来源。公网部署应使用 HTTPS。调试信息可能包含问题和资料相关内容，分享日志或报告前需要脱敏。
