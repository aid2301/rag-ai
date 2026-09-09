# GitHub Actions 模板

`ci-template.yml` 提供后端 PostgreSQL 测试、前端测试/Lint/构建与 Docker 构建三个任务。当前作为模板提供，不会自动执行。

启用时，将文件放到 `.github/workflows/ci.yml` 再提交。通过 HTTPS 令牌推送工作流时，需要 GitHub 令牌具备相应的工作流写入权限。模板只授予仓库内容只读权限，测试使用虚构数据和临时数据库。
