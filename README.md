# 企业合同智能审核与风险预警系统

Phase 0 工程基线。当前只包含 FastAPI/Vue/Celery/PostgreSQL/Redis/ClamAV 的启动骨架、健康检查和开发工具，不包含认证、业务表或正式业务页面。

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

`live` 只检查进程。`ready` 检查关键配置与 PostgreSQL，不检查千问瞬时状态；失败响应不会返回连接串。

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

Phase 0 没有业务表和 migration revision。配置 `DATABASE_URL` 后，空数据库仍可执行：

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

`.env` 只用于本地环境且已被 Git 忽略。千问、SMTP、OCR 和任何真实业务数据均不属于 Phase 0。
