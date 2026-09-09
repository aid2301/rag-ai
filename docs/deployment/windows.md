# Windows 运行

开发模式使用 [README](../../README.md) 的步骤，激活项目 `.venv` 后运行 `python scripts/dev.py`，或双击 `start-dev.bat`。

生产运行推荐 Docker Compose。若使用现有 Windows 服务管理器手动部署：

1. 把仓库放到固定目录，例如 `C:\apps\rag-ai`，安装 Python 3.11+、Node.js 24+ 并准备 PostgreSQL。
2. 复制 `.env.example` 到 `.env`，配置数据库、管理员密码和模型参数。
3. 在项目根目录执行 `npm --prefix frontend ci` 和 `npm --prefix frontend run build`。
4. 创建 `.venv`，使用其中的 Python 安装 `backend/requirements.txt`。
5. 服务可执行文件使用项目 `.venv\Scripts\python.exe`；工作目录设为项目根目录；参数为 `-m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000`。

服务账号必须能访问数据库并读写 `data/`；为日志配置轮转，并在服务管理器中配置进程重启。需要局域网访问时明确调整监听地址、防火墙和反向代理。不要复制另一台电脑的绝对用户路径。
