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
- Verification baseline: `c3b46ba` (`feat(auth): complete phase 2 security and ui flows`).
- Working tree at verification start: clean; the Phase 2 implementation, migration, tests and UI evidence are now recorded in this completion snapshot.
- Current boundary: Phase 0, Phase 1, Phase 2 and Phase 3 are `Completed` with Docker-backed health, migration, integration and independent Review evidence. Phase 3 completion is recorded below; Phase 4 remains `Not Started`.
- Phase 3 entry review: API Contract 8.1-8.9 and the PLATFORM-001/002/003, ORG-001 and LAYOUT-001 mappings were reviewed. P-10 is closed by the API-first platform/deployment model boundary and the corresponding architecture synchronization.
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

- Status: `Completed`
- Completed at: `2026-08-18`
- Current completion boundary: login, logout, session loading, CSRF rotation with a five-minute previous-token grace period, password reset, invitation acceptance, normalized rate limits, failed-login audit and SMTP safe observability are implemented. AUTH-001 through AUTH-004 cover success, error, missing-token, disabled and non-continuable states.
- Changes: authentication service/API, CSRF grace migration, trusted-proxy configuration, SMTP failure wrapper, Vue auth pages, Playwright coverage, Element Plus registration and auth visual styling. No Phase 3 organization or contract business work was added.
- API Contract / OpenAPI: the manual contract did not change. P-01, P-08 and P-09 remain closed. The reset-request OpenAPI projection has `202/422/429/503`; invalid login email returns `400 INVALID_CREDENTIALS`; Origin, CSRF, disabled-user, rate-limit and SMTP configuration behavior align with the contract.
- ORM / Migration: added `backend/migrations/versions/20260818_0003_phase2_csrf_grace.py`. Isolated Docker PostgreSQL database `contract_phase2_verify_20260818` completed `upgrade -> downgrade -> upgrade`; final revision `20260818_0003 (head)`. The CSRF grace timestamp is explicitly timezone-aware in ORM and migration.
- Frontend / UI Page IDs: AUTH-001, AUTH-002, AUTH-003 and AUTH-004 were checked against `frontend-prd.md`, `design-system.md` and Stitch assets. Playwright runs at 1440px and 1280px generated login, invitation and password-reset screenshots without overflow or overlap.
- Tests: `python -m pytest backend/tests` -> 53 passed; auth integration subset -> 18 passed; `python -m ruff check backend` -> passed; `python -m mypy backend/app` -> passed; `npm --prefix frontend run test -- --run` -> 4 files/12 tests passed; `npm --prefix frontend run e2e` -> 12 passed across Chromium 1440/1280; frontend lint/typecheck/build passed, with the existing Vite chunk-size warning.
- Docker / Smoke: `docker compose -f deploy/compose/compose.yml up -d --build api worker scheduler reverse-proxy` built and became healthy; proxy live -> 200; API container ready -> 200; container OpenAPI reported reset responses `202/422/429/503`; Compose config passed.
- Independent Review / Re-review: an independent read-only review initially found two P1 issues (login invalid-email status and CSRF identity-map refresh) plus UI P2 gaps. After fixes, re-review found no P1 blocker. `populate_existing + FOR UPDATE` and stale-session regression are covered, as are Result/missing-token/non-continuable auth states.
- Regression: backend full suite and frontend lint/typecheck/unit/build/e2e were rerun after fixes; no blocking regression found.
- Known Issues / Pending Decisions: Playwright uses controlled API mocks for deterministic browser UI paths; live browser-to-API wiring remains a deployment smoke concern, while the API itself is covered by PostgreSQL integration and OpenAPI assertions. Vite emits a non-blocking chunk-size warning. Phase 2 has no blocking Pending Decision.
- Git branch / HEAD / status / diff summary: `main` / `c3b46ba`; application and ledger snapshot committed with 24 files changed, then pushed after final diff review. No secrets or unrelated cleanup are included.
- Commit / Push: authorized by the user; normal commit and push follow this ledger/diff review, without force push or amend.
- Next Phase and entry conditions: Phase 3 remains `Not Started`; enter only after this Phase 2 ledger is committed/pushed and Phase 3 Pending Decisions/API entries are reviewed.

## Independent Review Record

- Reviewer: independent read-only reviewer (`/root/phase2_independent_review`)
- Review scope: Phase 2 authentication/tenant/CSRF/audit/security, API Contract/OpenAPI alignment, migration, frontend auth acceptance, viewport evidence and test coverage.
- Result: initial P1 findings were fixed and re-reviewed on 2026-08-18; no remaining P1 blocker. Remaining browser-live integration coverage is recorded as non-blocking Future Work under Phase 2.

## Phase 3: Platform and Organization Configuration

- Status: `Completed`
- Entry condition: satisfied. Phase 2 is `Completed`; Phase 3 P-10 is closed; API Contract 8.1-8.9 and the mapped UI specifications have been reviewed.
- Planned UI: PLATFORM-001、PLATFORM-002、PLATFORM-003、ORG-001、LAYOUT-001 对应增量。

### Phase 3 Completion Record（2026-08-19）

- Status: `Completed`。
- Current completion boundary: 平台管理员可完成组织列表、创建、详情和更新（8.1-8.4）；组织成员可读取所属组织资料，组织管理员可读取/更新非秘密设置（8.5-8.7）；平台管理员可读取/更新平台级非秘密模型运行参数（8.8-8.9）。后端完成 RBAC、租户隔离、名称规范化唯一性、幂等创建、乐观锁、停用时现有会话撤销、审计和秘密脱敏；未实现成员邀请、组织级模型覆盖或模型名/密钥 API。
- Changes: 新增组织与平台模型配置 Service/API、Pydantic Schema、ORM Model、Alembic revision、集成测试；新增组织/模型前端 API 类型与客户端、应用壳、平台组织列表/详情、组织设置和模型配置页面；同步环境配置、Compose、架构和契约文档。
- API Contract / OpenAPI: P-10 已关闭并同步 `docs/architecture.md`；8.4 已补充 `409 ORGANIZATION_NAME_CONFLICT`，明确组织名称按 `lower(trim(name))` 在平台范围唯一；停用组织成员资料/设置按已确认边界返回 `404 ORGANIZATION_NOT_FOUND`，未引入未定义错误码。容器内 OpenAPI 已核对 8.1-8.9 九个路径及其响应状态投影。
- ORM / Migration: `backend/migrations/versions/20260818_0004_phase3_organization_configuration.py` 新增 `organizations.normalized_name`、名称唯一/规范化约束和平台模型单例配置表；独立 PostgreSQL 数据库 `contract_phase3_verify_20260819` 完成 `upgrade head -> downgrade base -> upgrade head`，最终 `20260818_0004 (head)`，并核对关键约束/索引。
- Frontend / UI Page IDs: PLATFORM-001/002/003、ORG-001、LAYOUT-001 已按 UI PRD、design-system 和 Stitch 映射实现；覆盖 loading、empty、error、forbidden、conflict、disabled 和 retry 状态，Playwright 在 Chromium 1440px/1280px 生成截图并检查无溢出/重叠。
- Tests: `.venv\Scripts\python.exe -m pytest backend/tests -q` -> 61 passed；`.venv\Scripts\python.exe -m pytest backend/tests/integration/organizations -q` -> 8 passed；`.venv\Scripts\python.exe -m ruff check backend` -> passed；`.venv\Scripts\python.exe -m mypy backend/app` -> passed；`npm --prefix frontend run test -- --run` -> 6 files/21 tests passed；`npm --prefix frontend run e2e` -> 18 passed（Chromium 1440px/1280px）；`npm --prefix frontend run lint`、`typecheck`、`build` -> passed；build 保留既有 Vite chunk-size warning。
- Docker / Smoke: `docker compose -f deploy/compose/compose.yml config` -> passed；Compose 相关服务重建并健康；代理 `/api/v1/health/live` -> 200；API 容器内部 `/api/v1/health/ready` -> 200；代理对外 `/api/v1/health/ready` -> 404（既有 Internal-only 边界）；容器内 OpenAPI 8.1-8.9 路径/状态码断言通过。
- Review / Re-review: 独立后端 Review 初始发现的名称冲突契约和停用组织错误码阻塞已由契约修订、实现和回归测试关闭；独立前端 Review 未发现 P1/P2 阻塞；完成相关回归后无剩余当前 Phase 阻塞项。一次审查期间提出的停用组织重新登录/会话语义扩展未纳入本 Phase，已撤回并记录为待后续决策。
- Regression: 后端全量、组织授权/事务/冲突测试和前端全量 Unit/E2E/lint/typecheck/build 均在最终范围下重跑通过；未修改 Phase 4 或后续业务。
- Known Issues / Pending Decisions: Playwright 使用受控 API mock，真实浏览器到部署 API 的联调仍属于部署 smoke；Vite chunk-size warning 非阻塞。停用组织后的新登录及 `/auth/session` 组织列表语义未在本 Phase 擅自改变，需产品/安全确认后另行同步契约；当前已保证停用后现有会话撤销及组织资料/设置 404 隐藏。API 尚未为可调数值设置定义平台最大值，当前仅执行契约已有的最小/范围校验。
- Git branch / HEAD / status / diff summary: `main` / `c72d8bd`；工作区保留本 Phase 及此前未提交的实现/文档改动，已执行 diff review，无 Secret 或生成报告纳入；未覆盖用户修改。
- Commit / Push: 未执行 Commit、Push、amend 或 force push；等待用户明确授权 Git Snapshot。
- Next Phase and entry conditions: Phase 4 保持 `Not Started`；进入前须由用户确认 Phase 4 的 Pending Decisions/API/UI 映射，并按同一 Plan -> Implement -> Test -> Review -> Fix -> Regression 流程开始。

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
