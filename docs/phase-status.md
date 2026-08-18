# Phase Status

## Document Purpose

本文件是项目实际开发进度的唯一人工记录。`docs/development-plan.md` 定义应该如何开发；本文件记录仓库实际完成到哪里。每次会话开始先读取本文件，每个 Phase 完成后先更新本文件，再进入下一 Phase。

## Status Definitions

- `Not Started`：尚未进入该 Phase。
- `In Progress`：正在实现或修复，尚未满足全部完成条件。
- `Verification Pending`：已有实现快照，但缺少可追溯的完整测试、Review、回归或完成报告，不能视为正式完成。
- `Blocked`：存在阻塞当前 Phase 的契约、产品、安全或外部条件。
- `Completed`：范围、测试、Review、回归、文档和 Git diff review 全部完成，且本文件已记录证据。

## Current Position

- Last updated: `2026-08-18`
- Branch: `main`
- Verification baseline: `a80c11a` (`docs: refresh phase status snapshot`)
- Working tree at verification start: clean; this update changes documentation only and does not change application code, Migration or secrets.
- Current boundary: Phase 0 and Phase 1 are `Completed` with Docker-backed health, migration and integration evidence; Phase 2 remains `In Progress` because independent Review found security, delivery and UI/test blockers. P-01、P-08、P-09 均已在契约层关闭，但对应实现和测试尚未全部满足。
- Next allowed work: fix or explicitly resolve the listed Phase 2 blockers, add the missing auth/E2E evidence, then update this record before Phase 3.
- Prototype/design documentation does not advance the implementation Phase by itself.

## Phase 0: Project Bootstrap

- Status: `Completed`
- Current completion boundary: FastAPI/Vue/Celery/PostgreSQL/Redis/ClamAV 工程骨架、健康检查、质量命令和 Compose 基线已有实现快照。
- Completed implementation: 见 Git snapshot `a52155e`。
- Verification evidence: `.venv\Scripts\python.exe -m pytest backend/tests/test_config.py backend/tests/test_health.py backend/tests/test_logging.py backend/tests/test_worker.py` -> 15 passed；`.venv\Scripts\python.exe -m ruff check backend` -> passed；`.venv\Scripts\python.exe -m mypy backend/app` -> passed；`npm --prefix frontend run lint` -> passed；`npm --prefix frontend run typecheck` -> passed；`npm --prefix frontend run test` -> 3 files/8 tests passed；`npm --prefix frontend run build` -> passed with Vite chunk-size warning；`docker compose -f deploy/compose/compose.yml config` -> passed；current Compose images rebuilt successfully；Docker Compose services healthy；container `GET /api/v1/health/live` -> 200；container `GET /api/v1/health/ready` -> 200。
- Exposure note: reverse proxy intentionally returns 404 for `/api/v1/health/ready`; API Contract/README define `ready` as Internal-only and expose only `live` through the proxy。
- API Contract: 健康检查接口已存在；未因本次文档任务修改。
- ORM / Migration: Alembic 已初始化；Phase 0 不创建业务 revision。
- Frontend / UI: 启动骨架，不代表正式业务 UI。
- Review result: Independent Review found no Phase 0 blocker after the Docker-backed checks；no business implementation was added to this Phase。
- Completed at: `2026-08-18`，本记录更新后进入 Git diff review。

## Phase 1: Shared Persistence and API Invariants

- Status: `Completed`
- Current completion boundary: tenant persistence、通用错误、分页、幂等、审计等实现和 Migration 快照已存在。
- Completed implementation: 见 Git snapshot `1663637` 和 `backend/migrations/versions/20260817_0001_phase1_shared_persistence.py`。
- Verification evidence: `.venv\Scripts\python.exe -m pytest backend/tests/unit` -> 10 passed；`.venv\Scripts\python.exe -m pytest backend/tests/integration/shared` -> 10 passed；`.venv\Scripts\python.exe -m pytest backend/tests` -> 38 passed；`.venv\Scripts\alembic.exe upgrade head` -> passed；`.venv\Scripts\alembic.exe downgrade base` -> passed；`.venv\Scripts\alembic.exe upgrade head` -> passed；final `alembic current` -> `20260817_0002 (head)`；`.venv\Scripts\python.exe -m ruff check backend` -> passed；`.venv\Scripts\python.exe -m mypy backend/app` -> passed。
- Database verification target: isolated Docker PostgreSQL database `contract_verify_20260818`; integration database `contract_test` and Redis database 15。
- Frontend / UI: API Client 基础，不包含正式业务页面。
- Review result: Independent Review found no Phase 1 blocker after migration/integration evidence；compound tenant constraints, idempotency, audit rollback and error boundaries are covered by the passing integration suite。
- Completed at: `2026-08-18`，本记录更新后进入 Git diff review。

### Phase 0 Completion Record（2026-08-18）

- Changes: 工程骨架、健康检查、Compose、质量命令和环境模板已存在；本次只补充验证证据。
- API Contract / OpenAPI: 未变化；`live` 对外、`ready` Internal-only 的暴露边界与契约一致。
- ORM / Migration: 无 Phase 0 业务 Migration。
- Frontend / UI: 仅启动骨架，无正式业务页面。
- Tests: backend bootstrap checks 15 passed；frontend lint/typecheck/unit/build passed；ruff、mypy、Compose config passed；current Compose images built successfully；Docker services healthy；容器 live/ready smoke 200。
- Review / Regression: 独立 Review 未发现 Phase 0 阻塞项；无应用代码变更，直接相关回归包含在 backend 全量 38 passed 中。
- Known Issues / Pending Decisions: 无 Phase 0 待决；反向代理拒绝 `ready` 是已记录的 Internal-only 设计。
- Git: `main`，验证基线 `a80c11a`；本次账本文档尚未提交；无应用代码、Migration 或 Secret 变更。
- Commit / Push: 本记录更新后执行 diff review；本条目不代表已提交或推送。
- Next Phase: Phase 1 已完成；继续核对 Phase 2 阻塞项，不进入 Phase 3。

### Phase 1 Completion Record（2026-08-18）

- Changes: tenant persistence、复合租户约束、幂等、分页、审计和公共错误实现已存在；本次补齐真实 Docker PostgreSQL/Redis 验证证据。
- API Contract / OpenAPI: 未变化；全局错误、分页、幂等和权限边界与契约核对通过。
- ORM / Migration: `20260817_0001_phase1_shared_persistence.py` 在独立数据库完成 `upgrade -> downgrade -> upgrade`；最终 head 为 `20260817_0002`。
- Frontend / UI: API Client 基础；无正式业务页面。
- Tests: unit 10 passed；shared integration 10 passed；backend full suite 38 passed；ruff、mypy passed。
- Review / Regression: 独立 Review 未发现 Phase 1 阻塞项；迁移、复合 tenant 约束、幂等并发、审计回滚和错误边界已由真实 PostgreSQL 集成测试覆盖。
- Known Issues / Pending Decisions: 无 Phase 1 待决；后续组织 API 仍须遵循已关闭的 P-01。
- Git: `main`，验证基线 `a80c11a`；本次账本文档尚未提交；无应用代码、Migration 或 Secret 变更。
- Commit / Push: 本记录更新后执行 diff review；本条目不代表已提交或推送。
- Next Phase: Phase 2 仍需关闭独立 Review 的实现/测试阻塞项后才能进入 Phase 3。

## Phase 2: Authentication and Session Security

- Status: `In Progress`
- Current completion boundary: 登录、退出、会话、密码重置、邀请接受的后端和 Vue 实现快照已存在。
- Completed implementation: 见 Git snapshot `4a443f8`、认证模块、AUTH 页面和 `backend/migrations/versions/20260817_0002_phase2_authentication.py`。
- Verification evidence: `.venv\Scripts\python.exe -m pytest backend/tests/unit` -> 10 passed；`.venv\Scripts\python.exe -m pytest backend/tests/test_config.py backend/tests/test_health.py backend/tests/test_logging.py backend/tests/test_worker.py` -> 15 passed；`npm --prefix frontend run lint` -> passed；`npm --prefix frontend run typecheck` -> passed；`npm --prefix frontend run test` -> 3 files/8 tests passed；`npm --prefix frontend run build` -> passed with Vite chunk-size warning。
- Verification evidence: `.venv\Scripts\python.exe -m pytest backend/tests/integration/auth` -> 3 passed；full `.venv\Scripts\python.exe -m pytest backend/tests` -> 38 passed；Phase 2 migration included in isolated `upgrade -> downgrade -> upgrade` cycle；frontend lint/typecheck/unit/build passed as recorded below。
- Incomplete evidence: no Playwright auth suite exists; UI has not passed the AUTH prototype/state review; the independent Review findings below remain open。
- API Contract decisions: P-01 closed by API Contract 2.2.1；P-08 closed by API Contract 3.1；P-09 closed by API Contract 3.5 with one background attempt, retry cap 0, safe failure observability and uniform `503 SMTP_NOT_CONFIGURED` before account lookup。
- Independent Review: 2026-08-18, read-only review by independent reviewer; findings below are blocking until fixed or explicitly re-scoped.
- Blocking findings:
  1. Login email rate-limit key uses raw `body.email`; case/whitespace variants bypass the per-account limit (`backend/app/modules/identity/api.py`, `schemas.py`).
  2. Password-reset SMTP delivery runs in `BackgroundTasks` without the P-09-required failure capture, safe structured log/metric and tests (`backend/app/modules/identity/api.py`, `backend/app/integrations/notifications/smtp.py`)；the contract now freezes one attempt with retry cap 0, so this is an implementation blocker rather than a Pending Decision。
  3. Every `GET /auth/session` rotates the single stored CSRF hash, creating a concurrent-tab invalidation race (`api.py`, `service.py`).
  4. Failed/disabled login paths do not append the required failed-login audit event (`backend/app/modules/identity/service.py`; architecture audit requirement).
  5. Auth integration coverage lacks disabled user, Origin/CSRF failures, token expiry/reuse boundaries, rate limits, SMTP failure and concurrent CSRF cases.
  6. AUTH-002/003/004 UI success/error states and disabled controls do not yet meet the frontend PRD/prototype acceptance; no Playwright coverage exists.
  7. Source-generated OpenAPI for password-reset request currently declares only `202/422`; it does not project the contract-required `429/503` responses.
  8. Reverse-proxy client IP forwarding is not wired into Uvicorn/API rate-limit source; deployment-level rate limiting needs a trusted-proxy decision.
- Resolved during review: API Contract 3.5 now lists `SMTP_NOT_CONFIGURED` and freezes the one-attempt/retry-cap-0/observability boundary；P-01、P-08、P-09 are no longer Pending Decisions。
- Next step: fix the P1 findings, implement P-09 failure observability, add missing auth tests and Playwright flows, then rerun Phase 2 integration, Review and regression before marking `Completed`.

## Independent Review Record

- Reviewer: independent read-only reviewer (`/root/independent_review`)
- Review scope: Phase 0-2 completion conditions, Phase 2 authentication/tenant/CSRF/audit/security, API Contract alignment, frontend auth acceptance and test coverage.
- Result: Phase 0 and Phase 1 completion evidence is now recorded and both are `Completed`; Phase 2 cannot be marked `Completed` because the blocking findings above remain.
- Blocking findings are recorded under Phase 2 above; no application-code fixes were made during this verification turn.

## Phase 3: Platform and Organization Configuration

- Status: `Not Started`
- Entry condition: Phase 2 正式 `Completed`，Phase 3 所需 Pending Decisions 已关闭，API Contract 已 Review。
- Planned UI: PLATFORM-001、PLATFORM-002、PLATFORM-003、ORG-001、LAYOUT-001 对应增量。

## Remaining Phases

Phase 4-16 均为 `Not Started`。范围、依赖和验收标准见 `docs/development-plan.md`；不得因原型已经存在而提前实现。

## Completion Record Template

完成任何 Phase 时复制以下模板并替换对应条目：

```text
Phase / Name:
Status: Completed
Completed at:
Current completion boundary:
Changes:
API Contract / OpenAPI:
ORM / Migration:
Frontend / UI Page IDs:
Tests (commands and exact results):
Review / Re-review:
Regression:
Known Issues / Pending Decisions:
Git branch / HEAD / status / diff summary:
Commit / Push:
Next Phase and entry conditions:
```
