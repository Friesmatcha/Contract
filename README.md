# 企业合同智能审核与风险预警系统

当前仓库已包含 Phase 0 工程骨架、Phase 1 共享持久化/API 基础、Phase 2 认证实现快照，以及前端 PRD、设计系统和 Stitch HTML/PNG 原型。正式 Phase 完成状态不根据 commit 名称推测，以 `docs/phase-status.md` 中记录的测试、Review 和回归证据为准。

## 项目文档

- 业务需求：`docs/requirements.md`
- 技术架构：`docs/architecture.md`
- API 唯一契约：`docs/api-contract.md`
- Phase 计划与验收：`docs/development-plan.md`
- 实际开发进度：`docs/phase-status.md`
- 前端 UI 入口：`docs/ui/README.md`
- 前端页面 PRD：`docs/ui/frontend-prd.md`
- 前端视觉规范：`docs/ui/design-system.md`
- HTML/PNG 原型：`docs/ui/stitch/`

## 环境要求

- Python 3.12
- Node.js 22 LTS 与 npm
- Docker Desktop / Docker Compose

## 本地后端

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
python -m uvicorn backend.app.main:app --reload --no-access-log
```

API 默认监听 `http://localhost:8000`：

- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`

`live` 只检查进程。`ready` 检查关键配置与 PostgreSQL，不检查模型 Provider 瞬时状态；失败响应不会返回连接串。

Worker 和 Scheduler 使用同一个后端环境：

```powershell
python -m celery -A backend.app.worker.celery_app:celery_app worker --loglevel=INFO
python -m celery -A backend.app.worker.celery_app:celery_app beat --loglevel=INFO
```

## 本地前端

```powershell
npm --prefix frontend install
npm --prefix frontend run dev
```

Vite 默认监听 `http://localhost:5173`，并将 `/api` 代理到本地 API。

## 数据库迁移

仓库当前包含 Phase 1 和 Phase 2 Migration。配置 `DATABASE_URL` 后执行：

```powershell
python -m alembic upgrade head
```

## 质量门禁

```powershell
python -m pytest backend/tests
python -m ruff check backend
python -m mypy backend/app
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
docker compose -f deploy/compose/compose.yml config
```

## Docker Compose

先从 `.env.example` 创建本地 `.env` 并替换占位密码，然后运行：

```powershell
docker compose -f deploy/compose/compose.yml up --build
```

浏览器入口为 `http://localhost:8081`。Compose 服务为 `reverse-proxy`、`api`、`worker`、`scheduler`、`postgres`、`redis` 和 `clamav`；业务文件使用 `file-volume` 命名卷。

反向代理只公开 `live`；Internal `ready` 仅供容器健康检查和受控运维网络使用，`http://localhost:8081/api/v1/health/ready` 会被拒绝。

`.env` 只用于本地环境且已被 Git 忽略。默认真实 Provider 为 DeepSeek `deepseek-v4-flash`，Base URL 为 `https://api.deepseek.com`，使用 Bearer Token 和 JSON Output；Qwen 仍作为可选 Provider 保留。真实 API Key 只能在本地 Secret 环境配置。普通自动化测试不得依赖真实 DeepSeek/Qwen、真实 SMTP、真实业务合同或不稳定公网服务。
