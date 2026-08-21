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

- Last updated: `2026-08-21`
- Branch: `main`
- Verification baseline: `3b83f77` (Phase 14B implementation snapshot, based on the verified Phase 14A ledger baseline `65edccc`) plus its immediately following Phase 14B ledger snapshot on `main`/`origin/main`.
- Working tree after the Phase 14B Git Snapshot: tracked source and documentation changes are committed; generated `.pytest-phase14a-tmp/`, `.pytest-phase14b-tmp/` and `test-results/` remain untracked and are preserved, not treated as source.
- Current boundary: Phase 0 through Phase 14B are `Completed`; Phase 15 and Phase 16 remain `Not Started`.
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
- Git branch / HEAD / status / diff summary: `main` / `8cd238c`；Phase 3 实现与文档快照已提交，工作区在 Phase 4 开始前干净，无 Secret 或生成报告纳入。
- Commit / Push: `8cd238c` 已正常提交并推送；本次 Phase 4 开始后不自动 Commit/Push。
- Next Phase and entry conditions: Phase 4 保持 `Not Started`；进入前须由用户确认 Phase 4 的 Pending Decisions/API/UI 映射，并按同一 Plan -> Implement -> Test -> Review -> Fix -> Regression 流程开始。

## Phase 4: Membership, Invitation and Support Access

- Status: `Completed`
- Started at: `2026-08-19`
- Scope: API Contract 8.10-8.13、8.16-8.18；成员邀请/重发及 `queued/sent/failed` 投递状态；最后组织管理员保护；会话撤销；最长 4 小时的只读支持授权及逐次访问审计；ORG-002、ORG-003。
- Explicitly out of scope: 合同 viewer 授权、平台管理员业务下载、支持授权写操作、自动 SMTP 重试。
- Entry review: Phase 3 baseline、API Contract、Phase 4 development plan、ORG-002/ORG-003 UI PRD、design-system 和 Stitch 原型已核对；P-01、P-02、P-08、P-09、P-10 已关闭。邀请投递状态扩展已先同步 API Contract 和 architecture。

### Phase 4 Completion Record（2026-08-19）

- Status: `Completed`。
- Current completion boundary: 组织管理员可分页筛选成员、发送和重发邀请、查看 `queued/sent/failed` 投递状态、修改角色/状态；重发作废旧令牌；最后一个有效组织管理员受保护；角色/状态变化撤销相关会话。组织管理员可查询、创建和撤销最长 4 小时的临时平台支持授权；活跃目标唯一、过期状态按有效时间判断、创建/撤销/逐次使用写审计。
- Changes: 新增成员与支持授权 Service/API、Pydantic Schema、ORM Model、Alembic revision、SMTP 投递状态后台更新和重发速率限制；新增 ORG-002 成员管理、ORG-003 支持授权页面、API Client、类型、路由和应用壳导航；邀请接受后清空仅适用于待邀请成员的投递状态；补充状态机和幂等边界回归。
- API Contract / OpenAPI: 8.10-8.13、8.16-8.18 已按 `docs/api-contract.md` 实现；字段、状态码、权限、幂等键和错误码与人工契约一致。运行时 OpenAPI 路径断言确认 Phase 4 的 5 个唯一路径均存在。支持授权校验器为后续业务 JSON GET 接口提供 `X-Support-Access-Grant` 访问审计边界；当前 Phase 不实现合同业务接口、下载或写操作。
- ORM / Migration: `backend/migrations/versions/20260819_0005_phase4_membership_support_access.py` 扩展成员邀请字段并新增 `support_access_grants`、活动授权部分唯一索引、过期/分页索引和完整性约束。独立 PostgreSQL 数据库 `contract_phase4_migration` 已完成 `upgrade -> downgrade -> upgrade`，最终 revision `20260819_0005 (head)`；集成测试使用专用 `contract_phase4_test`，未继续使用被旧草稿迁移污染的默认 `contract_test`。
- Frontend / UI Page IDs: ORG-002、ORG-003 已按 UI PRD、design-system 和 Stitch 原型实现，覆盖 loading、empty、error、forbidden、conflict、disabled、processing、retry、确认和危险操作状态；Playwright 在 Chromium 1440px/1280px 通过。
- Tests: `$env:TEST_DATABASE_URL=...contract_phase4_test; .venv\Scripts\python.exe -m pytest backend/tests/integration/organizations -q` -> 14 passed；同库 `pytest backend/tests -q` -> 67 passed，均有 pytest 缓存目录权限 warning；`python -m ruff check backend` -> passed；`python -m mypy backend/app` -> passed；`npm --prefix frontend run test -- --run` -> 7 files/24 tests passed；`npm --prefix frontend run lint`、`typecheck`、`build` -> passed；build 保留既有 Vite chunk-size warning；独立 Vite 服务复用下 `npx playwright test phase4.spec.ts --workers=1` -> 4 passed（1440px/1280px）。
- Review / Re-review: 第二遍 read-only diff/security review 检查了 tenant/RBAC、越权隐藏、状态迁移、最后管理员并发锁、幂等重放、令牌失效、审计摘要、SMTP 错误边界、迁移和前后端契约；发现并修复激活无用户成员、动态授权幂等重放、邀请接受投递状态和 SMTP 配置检查顺序问题，修复后相关回归通过。
- Regression: 后端全量与认证/组织集成回归、前端全量 Unit/质量门禁和 Phase 4 E2E 已在最终代码上重跑；未修改 Phase 5 或后续业务。
- Known Issues / Pending Decisions: Playwright 由独立 Vite 服务复用运行可正常退出，Playwright 自己管理 Vite 时在当前 Windows 环境下测试断言通过但子进程不收尾；真实浏览器到部署 API 的联调仍属于部署 smoke。pytest 缓存目录权限 warning 和 Vite chunk-size warning 非阻塞。默认 `contract_test` 仍保留旧草稿迁移状态，后续验证应使用干净专用 PostgreSQL 库或先修复该环境；未修改默认库。
- Git branch / HEAD / status / diff summary: `main` / `8cd238c`；工作区保留 Phase 4 未提交实现和文档变更，未包含 Secret、`.env`、原始合同、上传文件或生成报告；`git diff --check` 通过。
- Commit / Push: 未执行 Commit 或 Push，等待用户明确授权；未 amend、force push 或修改历史。
- Next Phase and entry conditions: Phase 5 保持 `Not Started`；进入前核对合同目录、viewer 授权和归档语义的 API Contract 与 P-07，关闭其当前 Phase 决策后再开始。

## Phase 5: Contract Catalog and Viewer Access

- Status: `Completed`。
- Completed at: `2026-08-19`。
- Current completion boundary: 组织管理员和审核员可创建、列表筛选、查看、编辑、归档和恢复本组织合同元数据；viewer 只能读取显式授权合同；组织管理员可授予/撤销同组织有效 viewer 的 `read` 权限。合同创建支持服务端展示编号、幂等和乐观版本；列表支持游标、搜索、状态、类型和负责人筛选；归档合同只读，恢复仅组织管理员可执行。
- Explicitly out of scope: 文件上传、文件下载、文档解析、OCR、审核任务、active ReviewTask 归档 guard、模型、风险、报告和物理删除。
- Entry review: 已核对 `docs/development-plan.md` Phase 5 范围、依赖、验收标准和 Pending Decisions，以及 `docs/api-contract.md` 8.14-8.15、9.1-9.6；P-07 判断为本 Phase 非阻塞，按计划只实现合同自身归档语义，active ReviewTask guard 留至 Phase 9A。
- Changes: 新增合同 Model/Schema/Service/API、租户复合外键、合同展示编号序列、合同查看授权和审计；新增 `20260819_0006_phase5_contract_catalog.py`；接入应用路由/CORS header/测试清理；新增合同 API Client、类型、列表/创建/详情页面、应用壳导航和 Phase 5 Playwright。
- API Contract / OpenAPI: 未修改人工契约；8.14-8.15、9.1-9.6 的方法、路径、字段、权限、错误和状态码按契约实现；集成测试断言八条 Phase 5 OpenAPI 路径投影存在。支持授权通过既有 `X-Support-Access-Grant` 只读 JSON 边界访问合同列表/详情，并沿用逐次访问审计。
- ORM / Migration: 新增 `contracts`、`contract_access_grants`，包含组织复合外键、viewer 授权唯一约束、状态/类型/标题/版本约束和列表索引。独立 PostgreSQL 数据库 `contract_phase5_migration` 完成 `upgrade head -> downgrade -1 -> upgrade head`，最终 revision `20260819_0006 (head)`；默认 `contract_test` 未修改。
- Frontend / UI Page IDs: `CONTRACT-001`、`CONTRACT-002`、`CONTRACT-003` 按 frontend PRD、design-system 和 Stitch 原型实现；覆盖 loading、empty、error、forbidden、conflict、archived/read-only、retry、归档/恢复确认和 viewer 授权操作；补充 `owner_id` 筛选，未伪造授权列表事实。
- Tests: `$env:TEST_DATABASE_URL=postgresql+psycopg://contract:replace-me@127.0.0.1:5432/contract_phase5_test; .venv\Scripts\python.exe -m pytest backend/tests/integration/contracts -q` -> 4 passed，pytest cache permission warning；同库 `.venv\Scripts\python.exe -m pytest backend/tests -q` -> 70 passed，同一 warning；`.venv\Scripts\python.exe -m ruff check backend` -> passed；`.venv\Scripts\python.exe -m mypy backend/app` -> passed；`npm --prefix frontend run test -- --run` -> 9 files/27 tests passed；`npm --prefix frontend run lint`、`typecheck`、`build` -> passed，build 保留既有 Vite chunk-size warning；独立 Vite 服务复用下 `npx playwright test phase5.spec.ts --workers=1` -> 4 passed（Chromium 1440px/1280px）；`git diff --check` -> passed。
- Review / Re-review: 完成最终 diff/security review，检查 API Contract/OpenAPI、tenant scope、复合租户约束、viewer 越权隐藏、支持只读边界、CSRF/RBAC、幂等、乐观锁、归档状态、审计、Migration 回滚和前后端调用映射；修复非法游标可能返回 500 的边界并补充 422 回归，补齐前端负责人筛选。未发现当前 Phase 阻塞项。
- Regression: 后端全量、合同集成、前端全量 Unit/质量门禁、OpenAPI 路径断言和 Phase 5 E2E 均在最终修改后重跑通过；未修改 Phase 6/7 或后续审核/模型/报告功能。
- Known Issues / Pending Decisions: Playwright 使用受控 API mock，真实浏览器到部署 API 的联调仍属于部署 smoke；pytest 缓存目录存在 Windows 权限 warning；Vite chunk-size warning 非阻塞；默认 `contract_test` 保留旧草稿 migration 状态，后续验证继续使用干净专用 PostgreSQL 库；P-07 仍按计划在 Phase 9A 关闭，不阻塞本 Phase。
- Git branch / HEAD / status / diff summary: `main` / `5202463`；工作区保留本 Phase 未提交修改，包含后端合同模块/Migration/测试、前端合同页面/API/测试/E2E、路由导航和测试 fixture 更新；未包含 Secret、`.env`、原始合同或生成报告。
- Commit / Push: 未执行 Commit、Push、amend 或 force push，遵守用户约束。
- Next Phase and entry conditions: Phase 6 进入前需重新核对 Secure File Lifecycle 范围和 API 9.7-9.8；本 Phase 不提供上传、下载或解析接口。

## Phase 6: Secure File Lifecycle

- Status: `Completed`。
- Completed at: `2026-08-19`。
- Current completion boundary: 组织管理员和审核员可按契约上传单个合同文件；服务端执行告知确认、扩展名/MIME/签名/基础结构/大小校验、流式 SHA-256、ClamAV 扫描和隔离区到随机存储键的原子移动。合同文件版本支持当前版本切换、幂等重放和审计；组织成员及授权 viewer 可安全下载，支持授权明确禁止下载；归档合同、跨组织和未授权文件均不泄露资源存在性。
- Explicitly out of scope: 文档解析、OCR、审核任务、ModelGateway、风险/条款/报告和文件物理清理。
- Entry review: 已核对 `docs/development-plan.md` Phase 6、`docs/api-contract.md` 9.7-9.8、`docs/requirements.md` 文件需求、`docs/architecture.md` 文件存储/安全章节、CONTRACT-004 UI PRD、design-system 和 Stitch 原型；未发现阻塞 Pending Decision。
- Changes: 新增 `FileObject`/`ContractFile` ORM、`FileStore` 本地隔离区和原子存储、ClamAV TCP 适配器、上传/下载 API、安全响应头、限流/审计、文件版本摘要；新增 CONTRACT-004 页面、XHR 上传进度、告知确认、版本表和下载入口；补充 OpenAPI 投影断言、文件安全集成测试、ClamAV 协议单测和 Phase 6 Playwright。
- API Contract / OpenAPI: 未修改人工契约；9.7/9.8 方法、路径、表单、响应、错误、CSRF、幂等、授权和支持授权禁下载边界按契约实现；运行时 OpenAPI 路径/状态投影由 `test_contract_file_openapi_projects_phase6_paths` 覆盖。
- ORM / Migration: 新增 `backend/migrations/versions/20260819_0007_phase6_secure_file_lifecycle.py`，包含 `file_objects`、`contract_files`、组织复合外键、版本/current 唯一约束、状态/哈希/大小约束和 storage key 唯一约束。独立 PostgreSQL 数据库 `contract_phase6_migration` 完成 `upgrade head -> downgrade -1 -> upgrade head`，最终 `20260819_0007 (head)`；默认 `contract_test` 保留旧草稿污染，未修改。
- Frontend / UI Page IDs: `CONTRACT-004` `/contracts/:contractId/files` 已按原型实现上传、告知、处理中、空数据、失败、禁止、归档禁用、viewer 只读和安全下载入口；合同详情文件区域同步接入版本和下载。
- Tests: `$env:TEST_DATABASE_URL=...contract_phase6_test; $env:REDIS_URL=...; .venv\Scripts\python.exe -m pytest backend/tests -q` -> 76 passed，1 个 Windows pytest cache permission warning；Phase 6 文件集成 -> 4 passed；`backend/tests/unit/test_clamav.py` -> 1 passed；`.venv\Scripts\python.exe -m ruff check backend` -> passed；`.venv\Scripts\python.exe -m mypy backend/app` -> passed；`npm --prefix frontend run lint`、`typecheck` -> passed；Vitest -> 10 files / 30 tests passed；`npm --prefix frontend run build` -> passed，保留既有 Vite chunk-size warning；`npm --prefix frontend run e2e -- --workers=1` -> 30 passed，Chromium 1440px/1280px；当前源码临时 API 镜像在 Compose 网络内执行 ClamAV clean smoke -> passed；`git diff --check` -> passed。
- Review / Re-review: 复核 tenant/RBAC、viewer 授权、支持授权禁下载、跨组织隐藏、幂等/并发版本、原子移动/失败清理、文件名路径隔离、审计/限流、响应头、Migration 约束和前后端契约。修复 ClamAV `stream: OK\0` 响应误判、补齐契约冻结的模型告知文案、补充加载 skeleton 和 OpenAPI/边界测试；修复后后端全量、前端全量质量门禁和全量 Playwright 均重跑通过。
- Regression: 后端全量 76 passed；前端 Unit/质量门禁和历史 Phase 3-5 + Phase 6 E2E 30 passed；未实现 Phase 7 解析/OCR 或后续审核/模型/报告功能。
- Known Issues / Pending Decisions: Playwright 使用受控 API mock，真实浏览器到部署 API 联调仍属于部署 smoke；当前运行中的 API 容器未重启，ClamAV smoke 使用当前源码临时镜像完成；宿主机未暴露 ClamAV 3310 是 Compose 内部网络设计；pytest cache Windows 权限 warning 和 Vite chunk-size warning 非阻塞。Phase 6 不做文件物理清理，保留至后续契约范围。
- Git branch / HEAD / status / diff summary: `main`；本 Phase 快照包含后端文件生命周期、Migration、测试、前端 CONTRACT-004、Phase 6 E2E 和本阶段账本；未包含 Secret、`.env`、原始合同或生成报告；完成快照后工作区应保持干净。
- Commit / Push: 已按用户授权执行正常 Commit/Push；不执行 amend 或 force push。
- Next Phase and entry conditions: Phase 7 保持 `Not Started`；进入前需重新核对文档解析/OCR/Evidence 契约、解析库和金样数据，不在本 Phase 提前实现。

## Phase 7: Document Parsing, OCR and Evidence

- Status: `Completed`。
- Completed at: `2026-08-19`。
- Current completion boundary: DOCX 保留段落、标题、表格单元格和原始顺序，以逻辑块/字符区间定位；文本 PDF 保存物理页、文本块和渲染页图；扫描 PDF/PNG/JPEG 逐页执行 OCR，保存 bbox、置信度、空白/低置信度/失败状态。解析结果按文件、解析器版本、OCR 阈值和组织页数上限生成 fingerprint，并复用成功结果。
- Explicitly out of scope: 千问、分类/要素抽取、风险判断、条款比对、审核任务编排、报告和物理文件清理。
- Entry review: 已核对 `docs/development-plan.md` Phase 7 范围/依赖/验收标准/Pending Decisions、`docs/api-contract.md` 9.9-9.10、`docs/requirements.md` FR-D、`docs/architecture.md` 文档/OCR/Evidence/安全/异步章节，以及 `docs/ui/README.md`、`frontend-prd.md`、`design-system.md` 和 CONTRACT-005 Stitch 原型；UI-P09 已关闭，P-04/P-05/P-07 不阻塞本 Phase。
- Changes: 新增 `backend/app/modules/documents/` 的解析模型、服务、Schema 和只读 API；新增 `backend/app/integrations/ocr/` 的 PaddleOCR adapter；扩展 `LocalFileStore.put` 用于安全页图落盘；接入应用路由、Alembic model registry、DOCX/PDF/图片金样和 PostgreSQL 集成测试；新增 `frontend/src/pages/documents/`、API/types、CONTRACT-005 路由/样式、Vitest 和 Phase 7 Playwright。
- API Contract / OpenAPI: 先更新并 Review 9.9 为 PDF/图片物理页、9.10 为 DOCX/全量逻辑块；实现 `include_blocks`、`include_source_spans`、SourceSpan、404/409 错误语义和 viewer/support tenant authorization；集成测试断言两条 OpenAPI 路径投影存在。物理页不存在/越权返回 `DOCUMENT_OR_PAGE_NOT_FOUND`，逻辑块不存在/越权返回 `DOCUMENT_NOT_FOUND`。
- ORM / Migration: 新增 `backend/migrations/versions/20260819_0008_phase7_documents.py`，创建 `document_versions`、`document_pages`、`document_blocks`、`source_spans`，包含解析 fingerprint、页/块顺序、哈希/状态/置信度/证据目标 CHECK、组织复合外键和索引。独立 PostgreSQL 数据库 `contract_phase7_migration` 完成 `upgrade head -> downgrade -1 -> upgrade head`，最终 revision `20260819_0008 (head)`；默认 `contract_test` 未修改。
- Frontend / UI Page IDs: `CONTRACT-005` `/documents/:documentVersionId` 按 PRD/design-system/Stitch 实现 PDF/图片页码、页图/文本/证据上下文、DOCX 逻辑块、OCR 状态、loading/empty/error/forbidden/conflict/retry 和无物理页状态；Playwright 覆盖 Chromium 1440px/1280px。
- Tests: `$env:TEST_DATABASE_URL=...contract_phase7_regression; .venv\Scripts\python.exe -m pytest backend/tests/golden/documents backend/tests/integration/documents -q` -> 10 passed，1 个 Windows pytest cache permission warning；最终独立库 `$env:TEST_DATABASE_URL=...contract_phase7_final; .venv\Scripts\python.exe -m pytest backend/tests -q` -> 86 passed，同一 warning；`.venv\Scripts\python.exe -m compileall -q backend`、`ruff check backend`、`mypy backend/app` -> passed；`npm --prefix frontend run test -- document-preview` -> 3 passed；Vitest -> 11 files/33 tests passed；`npm --prefix frontend run lint`、`typecheck`、`build` -> passed，build 保留 Vite chunk-size warning；`npm --prefix frontend run e2e` -> Chromium 1440px/1280px 的 32 个断言均显示 passed，命令在 Windows Vite 子进程收尾时未退出并按既有问题手动中断；PaddleOCR 3.7.0 + PaddlePaddle 3.3.1 CPU model initialization 和空白 PNG `recognize()` -> `lines 0`；`git diff --check` -> passed。
- Review / Re-review: 完成契约、OpenAPI、tenant/RBAC、viewer/support 只读边界、复合外键、解析幂等/fingerprint、page limit、OCR failure/low confidence/blank handling、文件页图清理、事务原子性、bbox 兼容、Migration downgrade 和前后端映射 review；修复 page/block flush 顺序、PaddleOCR 3 bbox/Windows cache/oneDNN 兼容、超页拒绝、失败事务残留、物理页 404 错误码和 DOCX fallback。未发现当前 Phase 阻塞项。
- Regression: 最终后端全量 86 passed；Phase 7 定向 10 passed；前端 Unit/质量门禁 33 passed；Phase 3-6 历史 E2E 与 Phase 7 页面在两种桌面 viewport 的 32 个断言通过；未实现 Phase 8A/8B、审核/模型/报告功能。
- Known Issues / Pending Decisions: 默认 `contract_test` 保留旧草稿 migration 污染，未修改；pytest cache Windows permission warning 和 Vite chunk-size warning 非阻塞；Playwright 断言通过但 Windows 下 Vite 子进程收尾不退出；`alembic check` 仍报告 Phase 0-6 已有的时间类型、`file_objects.size_bytes`、组织唯一约束和 support FK ORM/Migration 漂移，未修改已发布 migration；PaddleOCR 首次运行需要可写模型缓存和模型源/预热模型，普通自动化测试使用 Fake OCR；无 Phase 7 阻塞 Pending Decision，P-07 仍留至 Phase 9A。
- Git branch / HEAD / status / diff summary: `main` / `b4c4f84`；Phase 7 实现已形成 30 个文件、3007 insertions/12 deletions 的独立实现提交，本台账更新作为最终状态快照；未包含 Secret、`.env`、原始合同、模型缓存或生成报告，未覆盖用户已有修改。
- Commit / Push: 用户已明确授权正常 Commit/Push；实现提交 `b4c4f84` 已创建，本台账快照提交后两笔提交一并推送；不执行 amend、force push 或历史重写。
- Next Phase and entry conditions: Phase 8A/8B 保持 `Not Started`；进入前按 `docs/development-plan.md` 重新 Review P-04/P-05、规则/模板版本契约和并行 Migration merge 计划。

## Phase 8A: Versioned Risk Rules

- Status: `Completed`。
- Completed at: `2026-08-20`。
- Current completion boundary: 组织管理员可在显式 tenant scope 下创建规则集、创建和编辑草稿、复制已发布版本、发布、停用/启用和显式切换默认规则集；审核员只能读取已发布版本，viewer 和跨组织访问被拒绝。已实现白名单 DSL（关键词、正则、金额/日期阈值、字段存在性、逻辑组合），不执行风险分析、任意 Python、SQL 或表达式。
- Contract / decisions: 先更新并 Review `docs/api-contract.md` 10.1、11.1-11.8，补齐默认标识、显式切换请求/响应、停用冲突、`VERSION_SOURCE_INVALID` 和缺少默认配置错误；P-04/P-05 已同步关闭到 `docs/development-plan.md`、`docs/requirements.md`、`docs/architecture.md` 和 `docs/ui/frontend-prd.md`。`docs/development-plan.md` 的 Phase 8A 测试路径已修正为实际目录 `backend/tests/integration/risks`、`backend/tests/unit/risks`。
- Changes: 新增 `backend/app/modules/risks/rules/` Model/Schema/Service/API、`backend/tests/{unit,integration}/risks/`、`backend/migrations/versions/20260819_0009_phase8a_risk_rules.py`、风险规则 API Client/校验器/条件编辑器和 RULE-001 `/risk-rule-bundles`、RULE-002 `/risk-rule-bundles/:bundleId`、RULE-003 `/risk-rule-bundle-versions/:versionId` 页面；共享应用壳补齐多组织上下文选择和资源深链同步。
- API / authorization: 8 个 11.1-11.8 接口的 Method、Path、字段、错误、RBAC、CSRF、幂等和乐观锁已由人工契约和 OpenAPI 投影核对；资源路径从资源归属推导组织，不信任客户端 `organization_id`、角色或错误的 `X-Organization-ID`。集合接口保留显式组织选择，默认切换、发布和审计在同一事务内完成。
- ORM / Migration: `20260819_0009` 线性继承 `20260819_0008`，未创建虚假 merge revision，未修改已发布 Migration。独立 PostgreSQL `contract_phase8a_migration` 完成 `upgrade head -> downgrade 20260819_0008 -> upgrade head`，最终 revision 为 `20260819_0009`；核对 `uq_risk_rule_bundles_default`、current-version 发布约束触发器、已发布版本/规则不可变触发器均存在，基线为 1 个默认规则集、1 个发布版本、11 条规则。独立测试库使用 `contract_phase8a_test`；默认 `contract_test` 的历史旧 Migration 污染未修改。
- Tests: `$env:TEST_DATABASE_URL=...contract_phase8a_test; .venv\Scripts\python.exe -m pytest backend/tests/unit/risks backend/tests/integration/risks -q` -> 44 passed；同库 `.venv\Scripts\python.exe -m pytest backend/tests -q` -> 130 passed；`.venv\Scripts\python.exe -m ruff check backend`、`.venv\Scripts\python.exe -m mypy backend/app`、`.venv\Scripts\python.exe -m compileall -q backend`、`git diff --check` -> passed；Phase 8A OpenAPI projection -> 1 passed。`npm --prefix frontend run test` -> 15 files / 56 tests passed；`npm --prefix frontend run lint`、`typecheck`、`build` -> passed；`npx playwright test phase8a.spec.ts --workers=1` -> 8 passed（Chromium 1440px/1280px）；`npx playwright test --workers=1` -> 40 passed（Chromium 1440px/1280px）。
- Review / Re-review: 独立只读 re-review 于 2026-08-20 完成，未发现 P0/P1 运行时、安全、tenant/RBAC、事务/并发、Migration 或前后端一致性阻塞；确认资源深链组织同步、平台管理员多组织选择器和 `source_version_id` 错误码修复。发现的两个 P2 文档问题已关闭：本记录已更新，Phase 8A 测试路径已与实际目录一致。修复后的回归、质量门禁、Migration 往返和全量 E2E 均已重跑通过。
- Regression / scope: 后端全量 130 passed，前端全量 Unit/质量门禁和 40 项历史+Phase 8A Playwright 回归通过；未实现 Phase 8B 条款模板、Phase 9A 审核任务、风险分析或条款比对。
- Known Issues / Pending Decisions: Windows pytest cache 仍有权限 warning；Vite build 保留既有 chunk-size warning；Playwright 使用受控 API mock，Windows 下 Vite 子进程收尾仍可能不退出；默认 `contract_test` 旧 Migration 漂移和既有 `alembic check` ORM/Migration 漂移未修改；根目录未跟踪 `test-results/` 为测试生成产物，不纳入实现。P-04/P-05 已关闭，无 Phase 8A 阻塞 Pending Decision。
- Git branch / HEAD / status / diff summary: `main` / `bb2e3ef`；`git status --short` 显示 Phase 8A 后端/Migration/测试/前端与契约文档修改，以及共享组织上下文回归修改；未跟踪 Phase 8A 新文件和 `test-results/`。工作区未提交，未执行 Commit、Push、amend、force push 或历史重写；`docs/codex-handoff.md` 已删除且未重新创建。
- Next Phase and entry conditions: Phase 8B 已在后续工作中完成；Phase 9A 仍保持 `Not Started`，不得将本记录理解为已进入审核任务开发。

## Phase 8B: Versioned Clause Templates

- Status: `Completed`。
- Completed at: `2026-08-20`。
- Current completion boundary: 在显式 tenant scope 下，组织管理员可管理条款模板、模板版本和标准条款，创建/复制/编辑草稿、发布、停用/启用和通过现有 12.4 PATCH 契约显式切换默认模板；审核员可读取模板和已发布版本，不能读取草稿或执行写操作。已发布版本及其条款不可编辑，历史审核引用的版本不受后续发布影响。Phase 8B 实现 CLAUSE-001 `/clause-templates`、CLAUSE-002 `/clause-templates/:templateId`、CLAUSE-003 `/clause-templates/:templateId/versions/:versionId`；未实现 Word/Excel 导入、条款比对、自动法律意见、风险分析或 Phase 9A 审核任务。
- Entry review: 已读取并核对 `AGENTS.md`、`docs/phase-status.md`、`docs/development-plan.md`、`docs/api-contract.md`、`docs/requirements.md`、`docs/architecture.md`、`docs/ui/README.md`、`docs/ui/frontend-prd.md`、`docs/ui/design-system.md` 和 CLAUSE-001/002/003 Stitch 原型；P-05 固定语义已关闭且本 Phase 未修改人工 API Contract。
- Changes: 新增 `backend/app/modules/clauses/templates/` Model/Schema/Service/API、`backend/migrations/versions/20260819_0010_phase8b_clause_templates.py`、CLAUSE 集成测试和 OpenAPI 投影测试；接入 `backend/app/main.py` 与 `backend/migrations/env.py`。新增 `frontend/src/api/clauseTemplates.ts` 和类型、CLAUSE-001/002/003 页面、路由、AppShell 导航、共享样式、Vitest 和 `frontend/e2e/phase8b.spec.ts`。
- API / authorization: 12.1-12.8 的 Method、Path、Query/Body、响应、错误、CSRF、Idempotency、RBAC 和 state transition 与现有人工契约一致；资源路径根据可信资源组织推导，集合接口使用显式 `X-Organization-ID` tenant scope，不信任客户端组织/角色/权限/归属。Reviewer 只读已发布版本；默认选择严格按合同类型和规范化业务场景精确匹配，不回退。
- ORM / Migration: `20260819_0010` 线性继承 `20260819_0009`，未修改已发布 Migration、未创建虚假 merge revision。新增模板/版本/标准条款、组织复合外键、默认模板部分唯一索引、current published 复合外键、发布状态与已发布不可变触发器；发布、默认切换、审计在事务内完成，并以组织/资源行锁和约束保证并发安全。独立 PostgreSQL `contract_phase8b_migration` 完成 `upgrade 0010 -> downgrade 0009 -> upgrade head`，最终 `20260819_0010 (head)`；最终核对 5 个模板、5 个版本、40 条演示条款、5 个默认模板。独立测试库为 `contract_phase8b_test`；默认 `contract_test` 未修改。
- Frontend / UI Page IDs: CLAUSE-001/002/003 按 UI PRD、design-system 和 Stitch 原型实现列表、详情/版本历史、草稿编辑器/标准条款抽屉；覆盖 loading、empty、error、forbidden、conflict、disabled、processing、retry 和已发布只读状态。浏览器实测在 1440px/1280px 下列表、详情、已发布版本和草稿编辑器无横向溢出；筛选栏和下拉 placeholder 已按 1280px 验收修正。
- Tests: `$env:TEST_DATABASE_URL=...contract_phase8b_test; $env:REDIS_URL=...; .venv\Scripts\python.exe -m pytest backend/tests/integration/clauses -q` -> 5 passed，1 个 Windows pytest cache permission warning；同库 `.venv\Scripts\python.exe -m pytest backend/tests -q` -> 135 passed，同一 warning；`.venv\Scripts\python.exe -m ruff check backend`、`.venv\Scripts\python.exe -m mypy backend/app`、`.venv\Scripts\python.exe -m compileall -q backend`、`git diff --check` -> passed；`npm run test` -> 17 files / 61 tests passed；`npm run lint`、`npm run typecheck` -> passed；`npm run build` -> passed，保留既有 Vite chunk-size warning；`npx playwright test phase8b.spec.ts --workers=1` -> 4 passed（Chromium 1440px/1280px），Windows Vite 测试服务收尾未自动退出，已手动停止，测试断言均通过。
- OpenAPI check: `test_clause_template_openapi_projects_phase8b_contract` -> passed；为避免新增分页响应类名影响 Phase 8A OpenAPI 投影，条款模块使用专用 `ClauseTemplateCursorPageResponse` schema 名称；Phase 8A 全量 OpenAPI 回归随后端全量测试通过。
- Review / Re-review: 完成只读 diff review，检查 requirements/API Contract/OpenAPI、tenant/RBAC、默认模板状态机、事务/并发/幂等、数据库约束/触发器、已发布不可变、审计、前后端调用映射和 UI 状态。修复了 PostgreSQL 触发器异常断言、条款分页 schema 与 Phase 8A 的 OpenAPI 命名碰撞、1280px 筛选栏换行和空下拉默认文案；最终未发现当前 Phase 阻塞 finding。
- Regression / scope: 后端 135 个测试、Phase 8B 定向 5 个测试、前端 61 个 Unit 测试、Phase 8B 4 个两 viewport E2E 和质量门禁均在最终修改后通过；未实现 Phase 9A，未回滚或重实现 Phase 8A，未修改默认 `contract_test` 的旧污染或既有 Alembic 漂移。
- Known Issues / Pending Decisions: Windows pytest cache permission warning、Vite chunk-size warning 和 Windows Playwright/Vite 子进程收尾问题均为非阻塞；根目录 `test-results/` 为未跟踪测试生成物，不纳入提交。`alembic check` 的既有 Phase 0-6 ORM/Migration 漂移未修改。P-05 已关闭；无阻塞本 Phase 的 Pending Decision。
- Git branch / HEAD / status / diff summary: `main` / `ee1d5a3`；Phase 8B 源码、Migration、测试和前端实现已形成独立功能快照；功能提交后无源代码修改，用户/测试生成的未跟踪 `test-results/` 保持未提交；本次未覆盖或恢复其他既有修改。
- Commit / Push: 用户已授权；`ee1d5a3`（`feat(clauses): add versioned clause templates`）已正常提交并推送到 `origin/main`，本账本更新作为后续 docs snapshot 正常提交并推送；未 amend、force push 或重写历史。
- Next Phase and entry conditions: Phase 8B Git Snapshot 门禁已关闭。Phase 9A 保持 `Not Started`，只允许在后续会话重新读取 Source of Truth、核对 Git/迁移状态并关闭 P-07 对任务创建/归档有影响的语义后进入；不得同时进入 Phase 9B 或实现模型、分类/抽取、风险、条款比对、通知或报告。

## Phase 9A: Review Task and Async Orchestration

- Status: `Completed`。
- Completed at: `2026-08-20`。
- Current completion boundary: 完成 `ReviewTask`、`ReviewStageRun`、10.1 创建、10.2 查询、10.3 失败重试、Celery 编排、Fake Stage Executor、阶段状态机、attempt、lease、heartbeat、Worker 崩溃恢复、补偿、Redis orphan requeue、重复投递幂等、组织并发上限 3 和输入快照锁定。未实现 ModelGateway、Qwen 调用、分类、字段抽取、风险分析、条款比对、通知、报告或真实业务结果。
- Entry / Contract review: 已重新读取并核对本 Phase 要求的 Source of Truth、REVIEW-001/002 和 CONTRACT-003 原型/规范；P-07 已关闭。`GET /review-tasks/{id}` 按任务资源归属建立 tenant context 并忽略客户端组织 Header；viewer 只能读取显式合同授权任务；支持访问只能读取；创建/重试不接受客户端 tenant、role、权限或结果内容。
- Contract update: 10.1-10.3 增加快照返回边界、stage 事实、`RETRY_LIMIT_EXCEEDED` 和每任务最多 3 次显式 retry；9.5 增加 active `pending|parsing|reviewing|pending_review` 归档 guard、终态历史只读和不级联语义。架构同步 lease 超时 `retryable -> 新 attempt`、补偿次数和任务 retry 上限。REVIEW-001 文案明确“离开未提交表单”，不表示取消已创建任务。
- Changes: 新增 `backend/app/modules/reviews/{models,schemas,service,api}.py`、`backend/app/worker/{review_tasks,compensation}.py`、Migration `backend/migrations/versions/20260820_0011_phase9a_review_tasks.py`；接入 `backend/app/main.py`、`backend/app/worker/celery_app.py` 和 `backend/migrations/env.py`；合同服务增加同事务归档 guard，并按“组织锁 -> 合同锁”顺序避免创建/归档死锁。新增 reviews async 集成/单元测试、OpenAPI 投影测试。
- ORM / Migration: `20260820_0011` 线性继承实际唯一 head `20260819_0010`，新增 review task/stage run、组织复合外键、活动任务部分唯一索引、stage attempt 唯一约束、租约/状态索引、快照和序列；未修改已发布 Migration，未创建 merge revision。独立 PostgreSQL `contract_phase9a_migration` 完成 `upgrade -> downgrade -1 -> upgrade`，最终 `20260820_0011 (head)`；测试使用 `contract_phase9a_test`，未修改默认 `contract_test` 的历史污染。
- Frontend / UI Page IDs: 新增 REVIEW-001 `/contracts/:contractId/reviews/new`、REVIEW-002 `/reviews/:reviewTaskId`，并接入 CONTRACT-003 创建入口/active review 状态。覆盖 loading、empty、error、forbidden、conflict、disabled、processing、失败 retry、网络错误；前台 2 秒起始退避，隐藏页面 10-60 秒降频，恢复可见立即刷新，终态停止轮询；只展示任务/stage 状态，不展示结果或风险结论。最终 E2E 覆盖 Chromium 1440px/1280px。
- Tests: `TEST_DATABASE_URL=...contract_phase9a_test; REDIS_URL=...; .venv\Scripts\python.exe -m pytest backend/tests/integration/reviews_async -q` -> 11 passed，1 个 Windows pytest cache permission warning；同库 `.venv\Scripts\python.exe -m pytest backend/tests` -> 148 passed，同一 warning；`.venv\Scripts\python.exe -m ruff check backend` -> passed；`.venv\Scripts\python.exe -m mypy backend/app` -> passed；9A OpenAPI 投影 -> 1 passed / 10 deselected，同一 warning；`npm --prefix frontend run test` -> 18 files / 64 tests passed；frontend lint/typecheck passed；build passed，保留既有 Vite chunk-size warning；`npm --prefix frontend run e2e` -> 52 passed，包含 1440px/1280px，Windows Vite 子进程收尾未自动退出，已在全部断言通过后手动停止。
- Review / Re-review: 独立只读 Review 初次发现 lease 状态、retry 上限、REVIEW-001 Cancel 文案、隐藏页轮询和归档并发锁顺序问题；已完成 Contract/architecture/UI PRD 更新和实现修复。真实 PostgreSQL 并发测试暴露并关闭创建/归档死锁；独立 re-review 确认上述阻塞项全部关闭，无新的 blocking code finding。
- Regression / scope: 后端全量、9A 专项、OpenAPI、frontend unit/lint/typecheck/build 和两 viewport Playwright 均在最终修复后重跑通过。数据库层覆盖重复领取、并发创建、活动唯一性、并发上限、租约过期、新 attempt、retry 上限、Redis orphan requeue、归档竞争、viewer、support read-only 和跨组织隐藏；未进入 Phase 9B。
- Known Issues / Pending Decisions: Windows pytest cache permission warning、Vite chunk-size warning 和 Playwright/Vite 子进程收尾问题均非阻塞；未运行真实 Celery worker 的 broker 断连/消息物理丢失故障注入，当前以数据库 orphan 扫描、重复投递幂等和 Fake Stage Executor 验证恢复边界；真实部署 broker smoke 留作部署验证。`test-results/` 为未跟踪测试生成物，保留且不纳入提交。无阻塞本 Phase 的 Pending Decision。
- Git branch / snapshot / status: `main`；Phase 9A 实现快照为 `6be1ff7`，其后续账本快照与实现一并推送，local `main` 与 `origin/main` 已对齐；tracked 工作区无修改，`test-results/` 保持未跟踪；未覆盖、恢复或清理用户已有修改/未知文件。
- Commit / Push: 用户已授权；`6be1ff7`（`feat(reviews): add async review orchestration`）已正常提交，本账本更新作为后续 docs snapshot 正常提交并一并推送到 `origin/main`；未 amend、force push 或修改历史。
- Next Phase and entry conditions: Phase 9A Git Snapshot 门禁已关闭；Phase 9B 明确保持 `Not Started`。后续会话进入 9B 前必须重新读取 Source of Truth，核对 Git、远端和 Migration 基线，并严格限制在 9B；不得进入 9C 或提前实现后续报告、通知等范围。

## Phase 9B: Model Gateway / External Model Boundary

- Status: `Completed`。
- Completed at: `2026-08-20`。
- Current completion boundary: 建立 provider-neutral `ModelGateway`，提供 classification、extraction、risk analysis、clause comparison/advice 四类版本化能力边界；实现严格 request/result Schema、证据校验、Fake fixture/error injection 和离线 Qwen adapter。实现 timeout、连接错误、429/5xx、Retry-After、指数退避、有限重试和一次输出修复重试；记录 request/model fingerprint、provider request ID、prompt/schema/sanitization version、token、cost、latency、status/error telemetry。未实现正式分类、字段抽取、风险分析、条款比对业务流程，也未持久化任何业务结果。
- Entry / Contract review: 已读取并核对 `AGENTS.md`、`docs/phase-status.md`、`docs/development-plan.md` Phase 9B/Phase 9B Test Boundary/P-10、`docs/api-contract.md` 2.3、5.4、8.8-8.9、10.1-10.3、18.2、20、`docs/requirements.md` 7.1/8.3/8.4 和 `docs/architecture.md` 5.1-5.2、6.4、9.3、10.2、12-15.4。P-10 平台/部署配置边界保持关闭；无新增浏览器 API、路由、页面或 prompt/组织模型配置接口。
- Changes: 新增 `backend/app/integrations/model/{schemas,gateway,fake,qwen}.py`、`backend/app/shared/model_telemetry.py`、模型单元/集成测试；`ReviewTask` 快照改为冻结的平台 baseline prompt/schema/sanitization 版本；Qwen 协议仅存在 integrations/model 边界，普通测试使用生成的测试密钥占位值和离线 opener，不访问真实付费服务。
- ORM / Migration: 新增 `ModelCall` ORM 和 Migration `backend/migrations/versions/20260820_0012_phase9b_model_calls.py`；model_calls 显式保存 organization/task/stage 关联、provider/model 版本快照、fingerprint、usage/cost/latency/status/error；复合外键阻止跨组织 task/stage 关联，并以数据库约束保护 capability、状态、指纹和非负计量值。为 stage 复合外键新增 `review_stage_runs(organization_id, review_task_id, id)` 唯一约束；未修改已发布 Migration。专用 PostgreSQL `contract_phase9b_migration` 完成 `downgrade 20260820_0011 -> upgrade head`，最终 `20260820_0012 (head)` 且保持单一 head。
- API Contract / OpenAPI: 未修改人工 API Contract；无新增 browser API/UI。OpenAPI 投影检查为 40 条路径，模型路径仅保留既有 `/api/v1/platform/model-configuration`，review task 路径未变化；现有平台配置响应/审计秘密遮蔽边界保持不变。
- Frontend / UI Page IDs: 无前端文件、页面、路由或 API Client 变化；严格停留在后端 ModelGateway/持久化边界。
- Tests: `.venv\Scripts\python.exe -m pytest backend/tests/unit/model_gateway backend/tests/integration/model_gateway backend/tests/integration/reviews_async -q` -> 31 passed，1 个 Windows pytest cache permission warning；专用库 `$env:TEST_DATABASE_URL=...contract_phase9b_test; $env:REDIS_URL=...; .venv\Scripts\python.exe -m pytest backend/tests -q` -> 168 passed，1 个同类 warning；`.venv\Scripts\python.exe -m ruff check backend` -> passed；`.venv\Scripts\python.exe -m mypy backend/app` -> passed；`.venv\Scripts\python.exe -m compileall -q backend` -> passed；`git diff --check` -> passed；Qwen adapter 契约测试使用注入 opener，无公网/真实密钥调用。
- Review / Re-review: 独立审查覆盖 tenant/RBAC/复合外键、事务回滚、retry 与 repair retry、timeout/429/5xx/invalid JSON/schema/unknown fields/evidence、fingerprint/version、token/cost/latency、Secret/log/prompt/response 泄露和 OpenAPI 不变性。审查发现并修复了内部调用未显式传递 capability、HTTP 408 映射、Retry-After 日期解析和 provider request ID 长度边界；最终未发现 Phase 9B 阻塞 finding。
- Regression / scope: 9B 专项、9A async 直接回归、后端全量、Migration 往返、OpenAPI 投影和质量门禁均在最终代码下通过；未进入 Phase 9C，Phase 9A Worker 仍不会产生真实业务结果，未新增分类/抽取/风险/比对结果表或业务 API。
- Known Issues / Pending Decisions: `alembic check` 仍报告仓库既有旧 Migration/ORM 漂移（timestamp 类型、`file_objects.size_bytes`、organization 唯一约束、support access 外键等），未报告 `model_calls` 漂移；按范围未修改已发布 Migration 或默认 `contract_test` 污染。Windows pytest cache permission warning 非阻塞；`test-results/` 是原有及本次测试生成物，保持未跟踪且未清理。真实 Qwen 付费 smoke 未执行，按约束留给受保护环境；无阻塞本 Phase 的 Pending Decision。
- Git branch / HEAD / status / diff summary: `main`；Phase 9B 实现快照为 `1113a15`，其后续账本快照与实现一并推送后 local `main` 与 `origin/main` 对齐；tracked 工作区无修改，`test-results/` 保持未跟踪；未覆盖、恢复、删除用户已有修改或未知文件。
- Commit / Push: 用户已明确授权；`1113a15`（`feat(model): add provider-neutral model gateway`）已正常提交并推送，本账本更新作为后续 docs snapshot 正常提交并推送到 `origin/main`；未 amend、force push 或修改历史。
- Next Phase and entry conditions: Phase 9C 明确保持 `Not Started`。本次任务到此停止；进入 9C 前必须重新读取 Source of Truth 并获得用户单独授权，不提前实现正式分类、字段抽取、风险、条款比对、审核结果、预警、通知、报告或新的浏览器业务 API/UI。

## Phase 9C: Classification and Extraction

- Status: `Completed`。
- Completed at: `2026-08-20`。
- Current completion boundary: 完成合同分类、7 个核心字段抽取、结构化结果校验、SourceSpan/Evidence 多证据关联、`detected|not_found|needs_confirmation|confirmed|corrected` 公共状态模型、缺失值 JSON `null`、输入/模型/结果 fingerprint 和成功结果复用；接通 Phase 9A Worker 与 Phase 9B Fake Model Gateway；新增 10.5 结果读取的分类/字段初始投影和 REVIEW-003 只读分类、字段、置信度、证据跳转页面。未实现风险分析、条款比对、预警、人工修订、反馈、完成审核、通知、报告或 Phase 10 及后续业务。
- Entry / Contract review: 已读取并核对本 Phase 要求的 Source of Truth、REVIEW-003 `default`/`evidence-open`/`viewer-readonly` 原型和 API Contract 5.1、5.5、5.6、6、10.1-10.7、18.2、20；P-03 已关闭。公共结果状态保留 `detected`，10.5/10.7 不新增 `found`；缺失字段保存 JSON `null`，使用 `not_found` 或 `needs_confirmation`，未伪造证据。
- Changes: 新增 `backend/app/modules/reviews/results/{models,schemas,service,worker}.py`、`backend/migrations/versions/20260820_0013_phase9c_results.py`、Phase 9C 契约/集成/OpenAPI 测试；扩展 Fake Gateway 的 7 字段默认响应和 extraction evidence 语义；新增结果 API、TypeScript 类型/API Client、REVIEW-003 路由/页面、证据跳转和文档 SourceSpan ID；仅调整 Phase 9A E2E 的过时“结果入口禁用”断言。
- API / authorization: 新增 `GET /api/v1/review-tasks/{review_task_id}/results`，返回 PostgreSQL 持久化分类、7 个字段、状态、置信度和 Source Locator；支持 `include_evidence`，保留 10.5 风险/条款查询参数作为后续投影边界，当前不生成或筛选风险/条款事实。任务资源、viewer 显式合同授权、平台支持只读授权和组织范围均在后端校验；不返回供应商响应、Redis 状态、完整 prompt 或完整模型响应。Phase 9C OpenAPI 投影断言通过，结果路由已加入现有 API。
- ORM / Migration: 新增 `contract_classifications`、`extracted_fields`、`contract_classification_evidence`、`extracted_field_evidence`，包含组织复合外键、任务/字段唯一约束、状态/置信度/指纹 CHECK、Evidence 关联和主证据快捷引用；`20260820_0013` 线性继承实际唯一 head `20260820_0012`，未修改已发布 Migration。独立 PostgreSQL `contract_phase9c_test` 完成 `downgrade 20260820_0012 -> upgrade head`，最终 `20260820_0013 (head)`。
- Frontend / UI Page IDs: REVIEW-003 `/reviews/:reviewTaskId/results` 实现分类、7 个字段、模型值/当前值、置信度、缺失状态、证据 quote 和 PDF/图片/DOCX 定位跳转；viewer/forbidden、processing、error、retry、empty evidence、只读状态均有边界。文档预览按 `source_span_id` 高亮目标证据，未为 DOCX 伪造页码；1440px/1280px E2E 回归通过。
- Tests: `...pytest backend/tests/contract/classification_extraction backend/tests/integration/classification_extraction -q` -> 5 passed，1 个 Windows pytest cache permission warning；同专用库 `...pytest backend/tests -q` -> 173 passed，同一 warning；`ruff check backend`、`mypy backend/app`、`compileall -q backend`、`git diff --check` -> passed；前端 `npm run lint`、`typecheck`、`test`、`build` -> passed，18 files / 64 tests；`npm run e2e -- --workers=1` -> 52/52 断言通过，包含 Chromium 1440px/1280px，Windows Vite webserver 在断言完成后未自动退出并按既有边界手动停止；Migration downgrade/upgrade 和 Phase 9C OpenAPI test -> passed。
- Review / Re-review: 独立审查覆盖 requirements/API Contract、P-03、tenant/RBAC、复合外键、证据合法性、状态/null 语义、fingerprint reuse、事务/Worker 接入、Fake Gateway、OpenAPI、前后端映射和 Phase 10 越界；修正测试夹具父子 flush 顺序、Worker 阶段查询的显式组织范围、结果页 lint warning、结果 API OpenAPI fixture 和过时 E2E 断言。最终未发现 Phase 9C blocking finding。
- Regression / scope: 最终后端全量、前端全量质量门禁、Phase 9A E2E 直接回归、全量 52 条两视口 E2E 和 Migration 往返均在最终修改后通过；未实现风险分析、条款比对、预警、通知、报告、人工修订、反馈或完成审核。
- Known Issues / Pending Decisions: Windows pytest cache permission warning、Vite chunk-size warning 和 Windows Playwright/Vite 子进程收尾问题均为非阻塞；真实 Qwen smoke 未执行，普通测试全部使用 Fake Gateway；既有 `alembic check` 漂移和默认 `contract_test` 历史污染按前序记录保留，未在本 Phase 顺便修复；`test-results/` 保留为未跟踪测试生成物，不删除、不提交。无阻塞本 Phase 的 Pending Decision；Phase 10 明确保持 `Not Started`。
- Git branch / HEAD / status / diff summary: `main`；Phase 9C 实现提交 `d132f62` 包含 28 个文件、2719 insertions/30 deletions，本账本更新作为紧随其后的文档快照；完成后 tracked 工作区干净，仅保留未跟踪 `test-results/`，未覆盖、恢复、删除用户已有修改或未知文件。
- Commit / Push: 用户已明确授权；`d132f62`（`feat(extraction): add classification and structured extraction`）已正常提交，本账本更新作为后续 docs snapshot 正常提交，并将两者推送到 `origin/main`；未 amend、force push 或修改历史。
- Next Phase and entry conditions: Phase 10 保持 `Not Started`。后续若进入 Phase 10，必须重新读取 Source of Truth 并单独确认范围，再在同一结果读取边界中增加风险/条款事实；本 Phase 到此停止。

## Phase 10: Risk Analysis, Clause Comparison and Result Aggregation

- Status: `Completed`。
- Completed at: `2026-08-20`。
- Current completion boundary: 在锁定的规则/模板版本和文档证据范围内完成白名单确定性风险规则、ModelGateway 风险分析、标准条款比对、规则/模型结果去重、证据验证、稳定 fingerprint/reuse 和统一结果聚合；条款状态区分 `matched/deviated/missing/uncertain`，缺失条款允许无定位，其余可确认结论必须引用当前文档的合法 SourceSpan。人工修订、预警处置、通知、报告和自动训练仍不在本 Phase。
- Entry / Pending Decision review: 已完整核对 `AGENTS.md`、`docs/phase-status.md`、`docs/development-plan.md` Phase 10、Testing Strategy、Phase 9C boundary 和 Pending Decisions，以及 Phase 10 直接相关的 requirements/architecture/API Contract 章节、UI README/PRD/design-system 和 REVIEW-003 全部适用原型状态。P-03 已关闭；无阻塞当前 Phase 的新 Pending Decision。
- Changes: 扩展 `backend/app/integrations/model/schemas.py` 的风险空结果、条款 `uncertain` 和证据语义；新增 `backend/app/modules/reviews/results/{models,schemas,service,worker}.py` 的风险/条款结果事实、证据关联、规则执行、模型调用关联、去重/reuse 和结果读取聚合；新增 `backend/migrations/versions/20260820_0014_phase10_review_results.py`；补充风险正负例/阈值/逻辑/跨句/证据/空结果复用测试、Review Results 集成测试、Phase 10 Playwright 和前端结果类型/API/UI。
- API Contract / OpenAPI: 未修改人工 API Contract，未新增浏览器接口或路由；沿用 `GET /api/v1/review-tasks/{review_task_id}/results`，接入 `risk_severity`、`risk_status`、`clause_status` 和 `include_evidence` 的类型化查询及风险/条款响应投影。Phase 10 相关 OpenAPI 投影测试通过；不返回供应商原始响应、Redis 状态、完整合同、完整 prompt 或完整模型响应。
- ORM / Migration: 新增 `risk_findings`、`risk_finding_evidence`、`clause_comparisons`、`clause_comparison_evidence`，包含组织复合外键、任务/阶段/规则/模板/模型调用/文档/SourceSpan 关联、状态/等级/置信度/指纹 CHECK、结果唯一指纹和筛选索引。`20260820_0014` 线性继承实际唯一 head `20260820_0013`，未修改已发布 Migration；独立 PostgreSQL `contract_phase10_final` 完成 `downgrade -1 -> upgrade head`，最终唯一 head 为 `20260820_0014`。
- Frontend / UI Page IDs: REVIEW-003 `/reviews/:reviewTaskId/results` 接入风险摘要与筛选、风险发现表、条款对照表、状态/严重度/来源/置信度、证据定位跳转、无结果和处理中状态；viewer 继续只读，未提供 Phase 12 人工编辑入口。Phase 10 E2E 在 Chromium 1440px/1280px 通过；Playwright 仍受 Windows Vite webserver 子进程收尾问题影响，断言通过后手动停止。
- Tests: 独立库 Phase 10 定向回归（Review Results、风险规则引擎、OpenAPI）`24 passed`；同一独立 PostgreSQL 库后端全量 `python -m pytest backend/tests -q` -> `196 passed`，1 个 Windows pytest cache permission warning；全量 `ruff check backend`、`mypy backend/app`、`compileall -q backend` 和 `git diff --check` -> passed；前端 `npm --prefix frontend run lint` -> passed（140 个非阻塞格式 warning）、`typecheck` -> passed、Vitest `19 files / 68 tests passed`、`build` -> passed（保留 Vite chunk-size warning）；Phase 10 Playwright -> Chromium 1440px/1280px 各 1 个测试通过；Migration downgrade/upgrade 和 OpenAPI 投影通过。默认 `contract_test` 的既有 `invited_at` 漂移在一次未指定独立库的尝试中重现，未修改该库，验收结果均以独立库为准。
- Review / Re-review: 完成独立只读 diff/security review，覆盖需求和契约一致性、tenant/RBAC/viewer/support 只读边界、规则版本和模板版本锁定、`rule_id`/`standard_clause_id`/`model_call_id` 关联、SourceSpan/Evidence 合法性、`uncertain`/missing 语义、指纹去重/reuse、Worker 阶段路由、事务和模型输出安全；未发现 Phase 10 blocking finding。
- Regression / scope: 后端全量 196 tests、前端全量 Unit/质量门禁、Phase 10 两桌面视口 E2E、OpenAPI 和 Migration 往返均在最终修改后通过；未进入 Phase 11，未实现预警、站内通知、人工修订、反馈、报告或后续 Phase。
- Known Issues / Pending Decisions: Windows pytest cache permission warning、Vite chunk-size warning、Vue lint 非阻塞格式 warning 和 Playwright/Vite 子进程收尾问题均保留为 Known Issues；既有 `contract_test` 污染和已发布 Migration/ORM drift 按固定边界未修复；真实 Qwen smoke 未执行，普通自动化测试全部使用 Fake Model Gateway；`test-results/` 保持未跟踪、未删除、未提交。无阻塞本 Phase 的 Pending Decision。
- Git branch / HEAD / status / diff summary: `main`；Phase 10 实现快照为 `b64d9e9`，包含后端结果模型/服务/Worker/API schema、`0014` migration、测试、REVIEW-003 前端类型/API/页面/样式，共 18 个文件、3004 insertions/161 deletions；本账本更新作为紧随其后的文档快照。完成后 tracked 工作区干净，仅保留未跟踪 `test-results/`，未覆盖、恢复或删除用户已有修改。
- Commit / Push: 用户已明确授权；`b64d9e9`（`feat(review-results): add risk and clause analysis`）已正常提交，本账本更新作为后续 docs snapshot 正常提交，并将两者推送到 `origin/main`；未 amend、force push 或修改历史。
- Next Phase and entry conditions: Phase 11-16 保持 `Not Started`。进入下一 Phase 前需按开发计划重新进行 entry review；本次不实现预警、通知或任何后续 Phase 能力。

## Phase 11: Warnings and In-App Notifications

- Status: `Completed`.
- Entry / Pending Decision review: Re-read the Phase 11 development-plan boundary, API Contract 13.1-13.3 and 14.1-14.3, requirements/architecture warning and notification sections, UI README/PRD/design system, and WARNING-001/WARNING-002/NOTIFY-001 assets. P-11 was closed for the minimum Phase 11 Warning/WarningEvent/Notification model. The contract clarification records that `assign` and `note` are legal only in `pending_confirmation` or `in_progress`; `assign` requires an active same-organization reviewer and `note` requires non-empty text.
- Scope boundary: Implemented warning trigger/deduplication, event state machine, assignment/deadline, in-app notifications/read state/delivery facts, warning list/detail, notification drawer, and result `warning_total`. Email/WeChat, fulfillment reminders, manual result edits, and Phase 12+ behavior were not implemented.
- Changes: Added `backend/app/modules/warnings/{models,schemas,service,api}.py`, `backend/app/integrations/notifications/in_app.py`, migration `20260820_0015_phase11_warnings_notifications.py`, warning generation at the final review stage transaction boundary, warning/notification API types and client, WARNING-001/WARNING-002 pages, NOTIFY-001 drawer, router/navigation/styles, unit/integration tests, and 1440px/1280px Playwright coverage.
- API Contract / OpenAPI: Updated the human contract and synchronized architecture/PRD state-matrix clarifications. Six Phase 11 routes are registered and a unit OpenAPI projection test passes. Query enums for warning status/severity/contract type/sort/direction and notification status are type constrained; malformed cursors return the shared validation error.
- ORM / Migration: `20260820_0015` is a linear child of the actual head `20260820_0014`; ORM models are registered with Alembic and use composite organization foreign keys, active dedupe uniqueness, state/read/delivery constraints and indexes. `alembic heads` and `history` show `20260820_0015 (head)`. Independent Docker PostgreSQL database `contract_phase11_test` completed `upgrade head -> downgrade -1 -> upgrade head`; final revision is `20260820_0015 (head)`.
- Frontend / UI Page IDs: WARNING-001 `/warnings`, WARNING-002 `/warnings/:warningId`, and NOTIFY-001 header drawer cover loading, empty/error/forbidden/read-only/processing paths present in the implementation. Viewer write actions are hidden; support access is read-only. The notification count polls every 60 seconds and is cleaned up on unmount.
- Tests: `.venv\Scripts\python.exe -m pytest backend/tests/unit/warning_state backend/tests/integration/warnings -q` -> `10 passed`; `.venv\Scripts\python.exe -m pytest backend/tests -q --basetemp D:\Contract\.pytest-phase11-tmp` against isolated `contract_phase11_test` -> `206 passed`; `.venv\Scripts\python.exe -m ruff check backend`, `.venv\Scripts\python.exe -m mypy backend/app`, `.venv\Scripts\python.exe -m compileall -q backend`, and `git diff --check` -> passed. Explicit backend bootstrap tests -> `15 passed`. `npm --prefix frontend run test -- --run` -> `20 files / 71 tests passed`; `typecheck`, `build`, and `lint` exit 0. Lint retains 140 existing Vue formatting warnings; build retains the existing Vite chunk warning. Phase 11 Playwright assertions were observed passed for Chromium 1440px/1280px (`4 passed`), but the Windows Vite/Playwright process did not cleanly exit and was manually stopped after the assertions.
- Integration / Review: Warning/Notification integration tests passed `5 passed` within the Phase 11 integration run and the backend full suite passed `206 passed` against isolated PostgreSQL. Independent read-only review covered tenant/RBAC/support read-only access, state transitions, assignment validation, deduplication/concurrency constraints, evidence lookup including primary-result evidence fallback, notification read/delivery separation, migration linearity, API/UI alignment, API read-transaction boundaries, and scope. The contract-test clarification for `assign`/`note` is documented and covered for every warning state. No remaining current-Phase blocking finding was identified.
- Known Issues / Pending Decisions: The current UI uses a reviewer ID reference input for assignment because Phase 11 exposes no reviewer-directory read API to non-admin reviewers; server-side same-organization active-reviewer validation remains authoritative. Notification delivery is in-app persistence in this Phase; automatic compensation/retry scheduling remains Phase 14B. Existing default `contract_test` pollution, Alembic drift and the pre-existing Windows pytest temp-directory permission issue were not changed; the final full suite used a temporary repository basetemp which was removed after verification. Real Qwen smoke was not run; automated model-path tests use Fake Model Gateway. `test-results/` remains untracked, preserved, and not submitted.
- Git branch / HEAD / status / diff summary: `main`; Phase 11 implementation snapshot is `3c0a7ff`, containing the warning/notification backend, `0015` migration, contract/architecture/PRD clarifications, tests, and WARNING-001/WARNING-002/NOTIFY-001 frontend implementation. This ledger update is the immediately following documentation snapshot. After completion the tracked working tree is clean and only the preserved untracked `test-results/` remains.
- Commit / Push: The user explicitly authorized the Git Snapshot and normal push. `3c0a7ff` (`feat(warnings): add warning and notification workflow`) and this following ledger snapshot are pushed to `origin/main`; no amend, force push, history rewrite, cleanup, or deletion was performed.
- Next Phase and entry conditions: Phase 12 completed in the following implementation snapshot `74d091e`; Phase 13 through Phase 16 remain `Not Started`.

## Phase 12: Human Review, Feedback and Completion

- Status: `Completed`.
- Completed at: `2026-08-20`。
- Entry / Pending Decision review: 完整核对 `AGENTS.md`、`docs/phase-status.md`、`docs/development-plan.md` Phase 12/Testing/Pending Decisions、`docs/requirements.md`、`docs/architecture.md`、`docs/api-contract.md` 10.4、10.6-10.9、16.1-16.2，以及 UI README、frontend PRD、design system、REVIEW-003 全部人工编辑/冲突/阻塞/viewer/evidence 状态资产和 ADMIN-003 Feedback Summary 规范/资产。已关闭 P-11 的 Phase 12 最小模型补齐；P-12 批量审核保持 Future Work；UI-P10 明确不假造完整修订历史，只展示当前响应和本次会话修订。
- Scope boundary: 完成分类、字段、风险、条款人工修订、不可变 ResultRevision、乐观锁、Evidence/SourceSpan 校验、Feedback 创建/幂等/租户统计、完成审核命令和 REVIEW-003/ADMIN-003 UI；未实现直接修改风险严重度、覆盖模型原值、自动训练、批量审核、报告或任何 Phase 13+ 功能。
- Changes: 新增 `backend/app/modules/reviews/revisions/`、`backend/app/modules/feedback/`、Phase 12 API/Schema/Service/测试和 `20260820_0016_phase12_human_review.py`；补齐 ReviewTask `completed_by/completed_at`、结果 `edited_by/edited_at` 和 API 投影；新增 REVIEW-003 编辑/409 冲突/阻塞/viewer/evidence 状态、ADMIN-003 反馈统计、API Client、类型和 Playwright；修复文档预览页 1280px 负边距导致的 4px 横向溢出，并补齐 Phase 12 文档证据 mock。
- API Contract / OpenAPI: 先更新并 review 10.4、10.6-10.9、16.1-16.2，冻结完成审核必须人工项：classification/field `needs_confirmation`、risk `pending_review`、clause `uncertain` 和无当前锁定文档合法 SourceSpan 的风险；`confirmed` 风险仍必须有证据。修订接口保持 before/after、version、reason、evidence ID 和状态语义；severity/source、model 原值和证据关联不可由修订请求改写。Feedback subject 必须属于当前任务和组织，`modified` 显式提供 corrected value；OpenAPI 路径投影测试通过，且完成命令非法状态按契约返回 409。
- ORM / Migration: `20260820_0016` 线性继承 `20260820_0015`，新增 `result_revisions`、`feedback`、完成/编辑元数据、复合 tenant 外键、版本 CHECK、索引和追加事实边界。独立 PostgreSQL `contract_phase12_test` 核对 `20260820_0016 (head)`，完成 `head -> downgrade -1 -> upgrade head`；默认 `contract_test` 未修改。
- Frontend / UI Page IDs: REVIEW-003 `/reviews/:reviewTaskId/results` 覆盖分类/字段/风险/条款编辑、model/current 对照、版本冲突刷新、阻塞列表、viewer 只读、证据跳转和本次会话修订记录；不渲染假造的完整 history feed。ADMIN-003 `/feedback/summary` 覆盖筛选、统计、loading/error/empty/forbidden/retry 和 1440px/1280px 无横向溢出。
- Tests: 独立库 `.venv\Scripts\python.exe -m pytest backend/tests/integration/human_review -q` -> `6 passed`；同库后端全量 -> `212 passed`，1 个 pytest cache permission warning；`.venv\Scripts\python.exe -m ruff check backend`、`.venv\Scripts\python.exe -m mypy backend/app` -> passed。前端 `npm --prefix frontend run test -- --run` -> `21 files / 76 tests passed`；`npm --prefix frontend run typecheck`、`npm --prefix frontend run build`、`npm --prefix frontend run lint` -> exit 0，lint 为 0 errors/348 existing formatting warnings，build 保留既有 chunk-size warning。`npm --prefix frontend run e2e -- phase12.spec.ts --workers=1` -> `4 passed`（Chromium 1440px/1280px）；Phase 7/10/11 直接相关历史 E2E -> `8 passed`。`git diff --check` -> passed；OpenAPI projection、migration downgrade/upgrade -> passed。
- Review / Re-review: 独立 review 检查 requirements/API Contract、P-11/P-12/UI-P10、tenant/RBAC/viewer、乐观锁/事务、before/after、evidence、model/current 边界、Feedback 幂等与统计、Migration、OpenAPI 和 UI 响应式。发现并修复完成命令 `INVALID_STATE_TRANSITION` 应返回 409 的阻塞 finding；修复后 Phase 12 集成、后端全量、前端门禁和相关 E2E 已重跑通过。
- Regression / scope: 后端 212 tests、前端 76 tests/质量门禁、Phase 12 两桌面视口 E2E、Phase 7/10/11 相关 E2E、OpenAPI 和 Migration 往返均在最终修改后通过；未实现 Phase 13 报告或任何后续 Phase。
- Known Issues / Pending Decisions: 默认 `contract_test` 仍有历史 `invited_at` Migration 污染，未修改；pytest cache 权限 warning、Vue lint 格式 warning、Vite chunk-size warning 和 Windows Playwright/Vite 子进程收尾问题均为非阻塞。真实 Qwen smoke 未执行，自动化模型路径使用 Fake Model Gateway。`test-results/` 保持未跟踪、保留且未提交。
- Git branch / HEAD / status / diff summary: `main`；Phase 12 实现快照为 `74d091e`，包含后端修订/反馈/完成审核服务、`0016` Migration、契约与测试、REVIEW-003 和 ADMIN-003 前端实现；本台账更新作为紧随其后的文档快照。完成后 tracked 工作区干净，仅保留未跟踪 `test-results/`，未覆盖、删除或纳入提交。
- Commit / Push: 用户已明确授权；`74d091e`（`feat(human-review): add revisions feedback and completion`）和本台账快照已正常提交并推送到 `origin/main`；未执行 amend、force push 或历史重写。
- Next Phase and entry conditions: Phase 13、Phase 14A、Phase 14B、Phase 15、Phase 16 均保持 `Not Started`；本次在 Phase 12 台账更新后停止，不进入任何后续功能。

## Phase 13: Immutable HTML/PDF Reports

- Status: `Completed`。
- Completed at: `2026-08-21`。
- Current completion boundary: 完成报告生成、状态查询、HTML 在线预览和 HTML/PDF 安全下载；状态固定为 `generating|ready|failed|expired`。报告在创建事务中冻结合同文件版本、组织报告设置、审核任务、分类/字段/风险/条款结果及证据、人工修订/反馈/完成记录和免责声明到不可变 `snapshot_json`；后续结果变化只影响新报告记录。失败使用新幂等键再次 POST，不增加报告专用 retry API；报告历史列表不实现。
- Entry / Pending Decision review: 已读取并核对本 Phase 要求的 `AGENTS.md`、`docs/phase-status.md`、`docs/development-plan.md` Phase 13/测试边界/Pending Decisions、`docs/requirements.md`、`docs/architecture.md`、`docs/api-contract.md` 15.1-15.3，以及 `docs/ui/README.md`、`docs/ui/frontend-prd.md`、`docs/ui/design-system.md`、REPORT-001 全部适用状态资产和 REVIEW-003 报告入口。P-06 已关闭：明确四状态、同幂等键同 fingerprint 重放、同任务/格式已有 generating 返回 `REPORT_ALREADY_GENERATING`、ready/failed/expired 用新幂等键创建新记录、`now >= expires_at` 过期、`expires_at = generated_at + retention_days`、无专用 retry API。UI-P11 已执行，不实现历史列表 feed。
- Changes: 新增 `backend/app/modules/reports/` 的 Report ORM/Schema/Service/API、版本化 Jinja2 模板、Fake/Chromium renderer；新增 `backend/app/worker/reports.py` 和 lease recovery/定时补偿；接入 `backend/app/main.py`、`backend/app/worker/celery_app.py`、`backend/migrations/env.py`、本地 FileStore 和 Docker Chromium 边界；新增 `frontend/src/api/reports.ts`、REPORT-001 页面/路由、REVIEW-003 生成入口、类型和样式；新增报告集成/快照测试及 `frontend/e2e/phase13.spec.ts`。
- API / authorization / security: 已同步 API Contract 15.1-15.3 的 Method、Path、状态、幂等、并发、过期、下载授权和稳定错误码。组织行锁和 generating 部分唯一索引保护并发；viewer 每次下载重新校验合同 read grant；组织成员按可信 tenant scope 访问；平台支持授权和平台管理员禁止下载并隐藏为 `404`。模板默认 HTML escaping；PDF 只由固定 Chromium CLI renderer 从同一版本 HTML 生成；响应设置安全 Content-Type、Content-Disposition、CSP、`no-store` 和 `nosniff`；不信任模型 HTML，不公开内部 renderer/FileStore 错误。
- ORM / Migration: 新增线性 Migration `backend/migrations/versions/20260821_0017_phase13_reports.py`，新增 `reports`、display sequence、复合 tenant 外键、状态/生命周期 CHECK、generating 唯一索引、并发/租约索引和 FileObject 复合外键；增加数据库触发器保护 Report identity、format、template version、snapshot_json 和 created_at 不可变。独立 PostgreSQL `contract_phase13_test` 完成 `20260821_0017 -> downgrade -1 -> upgrade head`，最终 head 为 `20260821_0017`。默认 `contract_test` 的历史 `invited_at` Migration 污染未修改。
- Frontend / UI Page IDs: REVIEW-003 报告创建入口支持 `html|pdf` 和新幂等键；REPORT-001 `/reports/:reportId` 覆盖 loading、generating polling、ready inline HTML/download、failed safe error/重新生成入口、expired/disabled download、forbidden safe state；没有报告历史列表或专用 retry API。Phase 13 Playwright 在 Chromium 1440px/1280px 下验证上述页面状态且无横向溢出。
- Tests: 独立 PostgreSQL `$env:TEST_DATABASE_URL=postgresql+psycopg://contract:replace-me@127.0.0.1:5432/contract_phase13_test; $env:REDIS_URL=redis://127.0.0.1:6379/15; .venv\Scripts\python.exe -m pytest backend/tests -q --basetemp .pytest-phase13-final-tmp` -> `219 passed`，1 个 Windows pytest cache permission warning；报告专项 `backend/tests/integration/reports backend/tests/snapshot/reports` -> `7 passed`，1 个同类 warning；`.venv\Scripts\python.exe -m ruff check backend`、`.venv\Scripts\python.exe -m mypy backend/app`、`git diff --check` -> passed；`npm --prefix frontend run test -- --run` -> `21 files / 76 tests passed`；`npm --prefix frontend run lint` -> exit 0，0 errors/386 warnings；`npm --prefix frontend run typecheck`、`npm --prefix frontend run build` -> exit 0，保留既有 Vite chunk-size warning；独立 Vite 服务下 `npx playwright test phase13.spec.ts --workers=1` -> `8 passed (13.7s)`，覆盖 Chromium 1440px/1280px；报告 OpenAPI 投影包含在专项测试并通过。
- Migration / OpenAPI: `.venv\Scripts\alembic.exe heads` 和 `history` 显示唯一 `20260821_0017 (head)`；独立库完成 migration downgrade/upgrade 往返；`test_report_openapi_projects_phase13_contract` 检查 15.1-15.3 路由、状态码、Idempotency-Key header 和下载错误投影通过。
- Review / Re-review: 独立只读复核覆盖 P-06、snapshot 不可变边界、HTML/PDF 同源模板、Chromium/FileStore、租约/重复投递/并发、REPORT_EXPIRED、tenant/viewer/support 下载授权、escaping/CSP/Content-Disposition、UI 状态和 UI-P11。修复了重复 Report import、幂等重放被 renderer 可用性提前阻断、snapshot 数据库保护，以及已过期报告重复下载错误返回 `409` 而非契约要求 `410 REPORT_EXPIRED`；修复后专项、全量和前端回归通过，无剩余当前 Phase blocking finding。
- Regression / scope: 未修改历史报告、未信任模型 HTML、未允许平台支持下载、未实现审计运营/保留期物理清理/通知补偿/报告专用 retry API/历史列表，也未进入 Phase 14 或后续功能。普通自动化继续使用 Fake Model Gateway；未执行真实 Qwen 或付费外部服务 smoke。
- Known Issues / Pending Decisions: 默认 `contract_test` 仍有既有 `invited_at` Migration 污染，未修改；`.pytest-phase10-tmp/` 保留且未清理；根目录 `test-results/` 及 Playwright 生成物保持未跟踪、不提交；pytest cache permission warning、Vue lint formatting warnings、Vite chunk-size warning 和 Windows Playwright/Vite 子进程收尾问题均非阻塞。提交前 `git fetch origin` 已成功，基线 `HEAD...origin/main` 为 `0 0`。
- Git branch / HEAD / status / diff summary: `main` / `31ae93f`；提交前 `origin/main=ac2ccf5` 且无远端分叉；Phase 13 源码、Migration、契约、测试和前端变更已形成实现快照，`test-results/` 保持未跟踪。用户原有 Phase 13 实现与本次审查修复均保留，未恢复、覆盖或清理无关文件。
- Commit / Push: 用户已明确授权；`31ae93f`（`feat(reports): add immutable HTML and PDF reports`）已正常提交，本台账更新作为后续 docs snapshot 正常提交，并将两者推送到 `origin/main`；未执行 amend、force push 或历史重写。
- Next Phase and entry conditions: Phase 14A、Phase 14B、Phase 15、Phase 16 均保持 `Not Started`。本次在 Phase 13 台账更新后停止；进入任何后续 Phase 前必须重新读取 Source of Truth 并获得单独授权。

## Phase 14A: Audit and Observability

- Status: `Completed`。
- Completed at: `2026-08-21`。
- Current completion boundary: 完成 17.1-17.4 组织/平台审计查询、审核/预警运营统计、内部 Prometheus `/metrics`、敏感日志过滤和 ADMIN-001、ADMIN-002、PLATFORM-004 管理页面；审计日志保持只读、不可变查询边界，本阶段未执行物理清理、通知补偿、对象存储迁移、批量审核、Grafana 部署或审计导出。
- Entry / Pending Decision review: 已完整核对 `AGENTS.md`、`docs/phase-status.md`、Phase 14A 计划/测试边界/Pending Decisions、`docs/requirements.md` FR-A04/FR-O、`docs/architecture.md` 审计/日志/指标/权限/tenant/事务边界、`docs/api-contract.md` 17.1-17.4、UI README/PRD/design system 及 PLATFORM-004、ADMIN-001、ADMIN-002 原型。P-06 已关闭；P-11 清理引用字段 Review 保持 Phase 14B 边界；P-12 批量审核保持 Future Work。未发现阻塞当前 Phase 的 Source of Truth 冲突；model cost 通过内部 `/metrics` 暴露，不新增未定义业务 API。
- Changes: 新增 `backend/app/modules/audit/`、`backend/app/modules/operations/` 和 `backend/app/observability/`；接入 HTTP/review/OCR/model/warning/report 指标、ModelGateway telemetry、日志脱敏和关键业务审计覆盖；新增前后端 API 类型/client、ADMIN-001 组织/平台审计页、ADMIN-002 运营指标页、路由/导航/响应式样式及 Phase 14A Unit/Integration/Playwright 测试。运营页按路由中的 `organizationId` 和对应 membership 请求，避免多组织用户的 tenant 请求错位。
- API Contract / OpenAPI: 补充 17.3/17.4 的时区、`[from,to)`、分母和聚合口径；实现组织审计、平台审计、审核指标和预警指标 4 个契约接口。`/metrics` 为内部部署端点，`include_in_schema=False`，不进入公网业务 API/OpenAPI；未新增审计修改、删除或导出接口。
- ORM / Migration: 审计模型增加全局 `(created_at, id)` 查询索引；新增线性 Migration `backend/migrations/versions/20260821_0018_phase14a_audit_observability.py`。独立 PostgreSQL `contract_phase14a_verify` 完成 `upgrade head -> downgrade -1 -> upgrade head`，最终 `20260821_0018 (head)`；未删除业务行或文件。
- Frontend / UI Page IDs: PLATFORM-004 `/platform/audit-logs`、ADMIN-001 `/audit-logs` 和 ADMIN-002 `/organizations/:organizationId/metrics` 覆盖 loading、empty、error、forbidden、retry、disabled/501、无效日期和 endpoint-local 指标错误状态；仅展示安全审计摘要和契约字段，无正文、Secret、Token、完整 prompt 或原始模型响应。
- Tests: 后端全量 `.venv\Scripts\python.exe -m pytest backend/tests -q --basetemp .pytest-phase14a-tmp` -> `226 passed`；Phase 14A 专项 `.venv\Scripts\python.exe -m pytest backend/tests/integration/operations backend/tests/unit/observability -q --basetemp .pytest-phase14a-tmp` -> `7 passed`，1 个 pytest cache permission warning；`.venv\Scripts\python.exe -m ruff check backend`、`.venv\Scripts\python.exe -m mypy backend/app` -> passed；前端 `npm --prefix frontend run test -- --run` -> `22 files / 81 tests passed`；`npm --prefix frontend run lint` -> exit 0，0 errors/386 warnings；`npm --prefix frontend run typecheck`、`npm --prefix frontend run build` -> exit 0，保留既有 Vite chunk-size warning；`npm --prefix frontend run e2e -- phase14a.spec.ts --workers=1` -> `4 passed`（Chromium 1440px/1280px）；`git diff --check` -> passed（仅 LF/CRLF 工作树提示）。
- Migration / OpenAPI: `.venv\Scripts\alembic.exe heads`/`history` 显示唯一 head `20260821_0018`；operations integration OpenAPI 投影确认 17.1-17.4 路由存在且 `/metrics` 不在 OpenAPI，内部 `/metrics` 返回 Prometheus 指标。
- Review / Re-review: 完成 entry review、contract/schema/index review、后端/观测/前端只读 diff review 和回归复核。重点检查 trusted tenant、Platform Admin 权限、审计不可变/敏感摘要、审计覆盖、指标事实来源、低基数 labels、代理暴露边界和三个 UI 的状态矩阵；发现并修复运营页使用全局组织而非路由组织参数的多组织 tenant 风险，修复后无剩余当前 Phase blocking finding。
- Regression / scope: 后端全量与前端全量门禁均通过；普通测试继续使用 Fake Model Gateway，未执行真实 Qwen、付费公网服务或 Grafana smoke。未进入 Phase 14B、15、16。
- Known Issues / Pending Decisions: `.pytest-phase10-tmp/` 历史权限目录保留且未删除；`.pytest-phase14a-tmp/` 和根目录 `test-results/` 为测试生成物，未纳入提交；pytest cache permission warning、Vue lint formatting warnings、Vite chunk-size warning 和 Windows Playwright/Vite 子进程收尾风险均非阻塞。提交前 `git fetch origin` 成功，基线 `HEAD...origin/main` 为 `0/0`。
- Git branch / HEAD / status / diff summary: `main`；Phase 14A 实现 snapshot 为 `102b50d`，包含后端审计/运营/可观测性、`0018` Migration、契约与测试、ADMIN-001/002 和 PLATFORM-004 前端实现；本台账更新作为紧随其后的文档 snapshot。`test-results/`、`.pytest-phase14a-tmp/` 和受保护的 `.pytest-phase10-tmp/` 均未纳入提交、覆盖或清理。
- Commit / Push: 用户已明确授权；`102b50d`（`feat(operations): add audit and observability`）已正常提交，本台账更新作为后续 docs snapshot 正常提交，并将两者推送到 `origin/main`；未执行 amend、force push 或历史重写。
- Next Phase and entry conditions: Phase 14B、Phase 15、Phase 16 仍为 `Not Started`；进入下一 Phase 前需获得新的明确授权并重新进行对应 entry review。

## Phase 14B: Retention and Compensation

- Status: `Completed`。
- Completed at: `2026-08-21`。
- Current completion boundary: 在不删除不可变数据库历史事实的前提下，完成 FileStore 内容保留期清理、文件写入孤儿恢复和站内通知失败补偿。`retention_days` 只控制 FileStore 内容；合同、文件、文档、审核、模型调用、结果、修订、预警/事件、反馈、报告快照和审计事实，以及 `FileObject` 元数据均保留。
- Entry / Pending Decision review: 完成 P-11 清理引用字段 Review、完整引用图和 P-13 决策 Review。已同步 `docs/requirements.md`、`docs/architecture.md`、`docs/api-contract.md` 和 `docs/development-plan.md`；审计 `365` 天明确为最低保留期，不授权删除不可变审计事实。P-13 已按用户确认关闭；P-12 批量审核继续为 `Future Work`。
- Changes: 新增 `file_cleanup_operations` 持久化 journal 和 `20260821_0019_phase14b_retention_compensation.py`；扩展 `FileObject.storage_status` 为 `quarantine|stored|deleting|deleted|failed`；合同上传、文档页图像和报告文件写入均记录 durable write journal。新增 retention service/worker，覆盖引用保护、活动任务/报告/通知补偿阻塞、`SKIP LOCKED`、lease、attempt、退避、final failure、worker 崩溃恢复、FileStore 幂等删除和数据库/FileStore 补偿；新增已有失败通知的有限补偿（最多 3 次，`1m/5m` 退避），不回滚 Warning，不增加手工重试 API。
- API Contract / OpenAPI: 仅同步既有 `storage_status` 投影的 `deleting|deleted` 状态和保留期/失败语义；未新增业务 API、浏览器清理命令、审计导出 API 或通知手工重试 API。OpenAPI 投影和现有前端类型同步通过。
- ORM / Migration: ORM 注册 `FileCleanupOperation`，增加 tenant 外键、状态/attempt/error 约束、claim 和组织查询索引；新增线性 Migration `20260821_0019`，不修改历史 revision。独立 PostgreSQL 完成 `upgrade -> downgrade -1 -> upgrade head`，最终唯一 Alembic head 为 `20260821_0019`。
- Frontend / UI Page IDs: 无新业务页面或假数据；仅更新 `frontend/src/api/types.ts` 的文件状态投影。
- Tests: `.venv\Scripts\python.exe -m pytest backend/tests/integration/retention -q` -> `8 passed`；独立 PostgreSQL 后端全量 `.venv\Scripts\python.exe -m pytest backend/tests -q --basetemp .pytest-phase14b-tmp` -> `234 passed in 92.73s`；`.venv\Scripts\python.exe -m ruff check backend`、`.venv\Scripts\python.exe -m mypy backend/app` -> passed；`npm --prefix frontend run test -- --run` -> `22 files / 81 tests passed`；`npm --prefix frontend run lint` -> exit 0，0 errors/386 existing warnings；`npm --prefix frontend run typecheck`、`npm --prefix frontend run build` -> exit 0，保留既有 Vite chunk-size warning；`git diff --check` -> passed（仅 LF/CRLF 工作树提示）。
- Failure injection / recovery coverage: 覆盖引用跳过、两个 scheduler 竞争只删除一次、FileStore 删除失败重试及最终失败、文件已删除但数据库状态提交失败后的幂等恢复、过期 lease/Worker 崩溃恢复、孤儿 write journal 回收和通知补偿失败不回滚 Warning。
- Review / Re-review: 完成 entry/P-11/P-13、Source of Truth、reference graph/schema、Migration、tenant/审计敏感字段、事务/锁顺序、lease/retry/idempotency、FileStore 安全边界和 scope 的独立只读复核；修复锁顺序和清理/写入恢复边界后，blocking findings 已关闭。清理、skip、retry、recovery 和 final failure 均写安全审计，审计和日志不记录合同正文、文件内容、邮箱、Token、Secret、完整 prompt 或原始模型响应。
- Regression / scope: 后端、前端、Migration 和 OpenAPI 回归均通过；普通自动化继续使用 Fake Model Gateway，未执行真实 Qwen、付费公网服务或对象存储迁移。未实现新业务 API、审计导出、对象存储迁移、批量审核、Grafana 强制部署或 Phase 15/16 功能。
- Known Issues / Pending Decisions: 默认 `contract_test` 仍有历史 `invited_at` Migration 污染，未修改；`.pytest-phase10-tmp/` 的历史权限目录未删除；`.pytest-phase14a-tmp/`、`.pytest-phase14b-tmp/` 和根目录 `test-results/` 为测试生成物，保留且不提交。pytest cache permission warning、Vue lint formatting warnings、Vite chunk-size warning 和 Windows Playwright/Vite 子进程收尾风险均非阻塞。P-12 仍为 `Future Work`。
- Git branch / HEAD / status / diff summary: `main`；Phase 14B 实现快照为 `3b83f77`，包含 retention/notification compensation、`0019` Migration、Source of Truth 同步、测试和前端类型；本台账更新作为紧随其后的文档快照。用户要求保留的测试生成物和历史权限目录未覆盖、删除或纳入提交。
- Commit / Push: 用户已明确授权；`3b83f77`（`feat(retention): add safe retention cleanup and compensation`）已正常提交，本台账快照作为后续提交并将两者正常推送到 `origin/main`；未执行 amend、force push 或历史重写。
- Next Phase and entry conditions: Phase 15、Phase 16 仍为 `Not Started`；本次在 Phase 14B 完成记录后停止，进入后续 Phase 需再次明确授权并重新进行对应 entry review。

## Phase 15: Independent CUAD v1 evaluation asset batch

- Status: `In Progress`（仅完成独立英文公开 Benchmark 资产批次，未完成 Phase 15）。
- Completed at: `2026-08-21`（本批次资产与离线验证完成；正式 Phase 15 仍未完成）。
- Current completion boundary: 接入固定版本 CUAD v1 下载器、供应链安全校验、SQuAD 适配器、合同级 split isolation、离线 span/classification metrics、`cuad-native` 与受限 `cuad-product-projection` CLI、mini fixture、schemas、归因和报告生成。未修改生产 API、数据库模型或 Migration，未改写官方 test，未启动完整 CUAD 正式评测。
- Source / license / integrity: Contract Understanding Atticus Dataset v1，仓库 `https://github.com/The-Atticus-Project/cuad`，固定 repository commit `67faa0e6023b04fcaae6cc09497ab00e5d63a2a2`，data.zip Git blob SHA `1ae94ff0a9b70b2e3b9b8d215737c8bfae460ddc`，实际下载 SHA-256 `f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a`，许可 CC BY 4.0，DOI `10.5281/zenodo.4595826`，语言 English。原始 ZIP、解压数据、真实模型输出和运行产物均由 `.gitignore` 排除，受保护的 raw/outputs 和用户测试生成物未删除、覆盖或纳入提交。
- Data structure / counts: 已核对固定归档实际包含 `test.json`、`train_separate_questions.json`、`CUADv1.json`；test 为 102 contracts / 4,182 samples / 1,244 answer samples / 2,938 no-answer samples / 41 official categories；train 为 408 contracts / 22,450 samples / 11,180 answer samples / 11,270 no-answer samples / 41 official categories。类别全部来自官方 question category；没有内部 `no_answer`、`other` 或汇总类别。适配器保留 contract/document ID、question ID、category、context、gold text/offset，校验 offset、ID、无答案和合同级 split isolation；不修改官方 test。
- Offline tests: `python -m pytest evaluation/tests` -> 13 passed；Qwen config/Gateway regression `.venv\Scripts\python.exe -m pytest backend/tests/test_config.py backend/tests/unit/model_gateway -q` -> 22 passed；`.venv\Scripts\python.exe -m ruff check evaluation backend` -> passed；`.venv\Scripts\python.exe -m mypy evaluation backend/app` -> `Success: no issues found in 137 source files`；`docker compose -f deploy/compose/compose.yml config --quiet` -> passed；`git diff --check` -> passed。pytest 仅有受控 duplicate ZIP fixture warning 和既有 Windows cache permission warning；Mypy 配置仅排除受保护 `evaluation/datasets/raw/` 与 `evaluation/outputs/`。
- Qwen configuration review: 官方 QwenCloud 文档确认模型 `qwen3.8-max`、国际 OpenAI-compatible base URL `https://dashscope-intl.aliyuncs.com/compatible-mode/v1`、Bearer 鉴权和 `response_format={"type":"json_object"}`；现有 prompt 含 `JSON`，未设置 `max_tokens`。发现 `.env` 的 `MODEL_BASE_URL` 原先被 Settings 忽略，Worker/evaluation 会回退到 `dashscope.aliyuncs.com`；已补齐 Settings、Worker、评测 runner、Compose 和 `.env.example` 的配置传递。此配置修正未新增真实调用。
- Controlled Qwen smoke: 已执行历史受控 smoke，1 contract、5 categories、最多 5 provider requests；run `evaluation/outputs/20260821T080216Z-46197ad3/`，模型 `qwen3.8-max`，历史 endpoint region `dashscope.aliyuncs.com`，5 requests / 4 provider request IDs，11,710 input tokens / 3,477 output tokens，费用因未配置 rate 不可用；5/5 provider failure（1 timeout、2 schema failure、1 request-budget exhaustion），provider failure rate 100%。该 smoke 发生在 endpoint 配置修正前，不能作为修正后连通性证据，也不是 Phase 15 通过/失败结论；修正后未追加真实 Qwen 请求。
- Full-run estimate / gate: 官方 test 预计 102 contracts、4,182 requests、约 49,985,087 input tokens、501,840 output tokens；未配置 `MODEL_COST_PER_1K_INPUT`/`MODEL_COST_PER_1K_OUTPUT`，金额不可估算。完整正式 CUAD 尚未运行；后续必须单独确认请求预算、价格、Prompt/Schema 并批准预期费用。
- Interpretation boundary: CUAD 是英文公开合同 Benchmark，存在大模型预训练污染风险；只能解除英文公开 Benchmark 资产缺口，不能证明六类中文合同分类、完整七字段或中国合同风险指标。`cuad-product-projection` 只报告显式 `exact`/`partial`/`unsupported` 映射支持范围，不输出虚假产品总 F1 或 Phase 15 通过结论。中文、授权、人工复核 gold set 仍是 Phase 15 正式指标必要条件。
- API / ORM / Migration / UI: 未新增或修改业务 API、OpenAPI、ORM、数据库 Migration、前端页面；为修正实际 Qwen 配置，仅更新非 API 的 Settings、Worker Gateway wiring、Compose/env example 和评测 runner。
- Review / regression / remaining: 已完成数据来源、许可、下载路径穿越/符号链接/重复路径/压缩比/解压大小、无答案/offset/ID/split、指标空集合和日志敏感信息边界复核；未执行完整 Phase 15 回归、中文产品 gold set、真实 Qwen 修正后 smoke 或正式 test。Phase 15 不得因 CUAD 接入标记 `Completed`。
- Git snapshot: branch `main`，开始核对时 HEAD 与 `origin/main` 均为 `db7c90dd22c926611bc0d48e661cac362b470708`，`HEAD...origin/main` 为 `0 0`；工作区保留用户已有 `.pytest-phase14a-tmp/`、权限警告目录和 `test-results/`，本批次未执行 Commit、Push、amend、force push 或历史重写。建议提交范围仅为本批次明确新增/修改的 evaluation 资产、文档、配置传递和最小测试/pyproject 排除规则。

### Phase 15 provider default update (2026-08-21)

- Status: `In Progress`；已完成默认 Provider 配置、离线接线和一次受控真实 smoke，不代表真实模型正式评测完成或 Phase 15 Completed。
- Changes: 新增 `DeepSeekModelGateway` 和统一 Provider factory；Settings 默认改为 `deepseek` / `deepseek-v4-flash` / `https://api.deepseek.com`，新增有界 `MODEL_MAX_TOKENS` 与 `MODEL_THINKING_MODE`；Worker、CUAD evaluation CLI、Compose 和 `.env.example` 使用同一配置链路；Qwen 实现和测试保留。
- DeepSeek request boundary: `/chat/completions`、Bearer、JSON Object、显式 disabled thinking、配置 max tokens；四类 capability prompt 含 JSON 示例、prompt/schema version；响应 ID、usage、cache hit token（若提供）和安全错误字段由 Gateway 解析。
- Tests / scope: `.venv\Scripts\python.exe -m pytest backend/tests/unit/model_gateway backend/tests/test_config.py -q` -> 51 passed；`.venv\Scripts\python.exe -m pytest evaluation/tests -q` -> 13 passed；`.venv\Scripts\python.exe -m ruff check backend evaluation`、`.venv\Scripts\python.exe -m mypy backend/app evaluation`、`docker compose -f deploy/compose/compose.yml config --quiet`、`git diff --check` -> passed；Fake mini CLI -> passed，manifest request_count=0。pytest 保留既有 Windows cache permission warning 和 duplicate ZIP fixture warning。本轮不修改业务 API、ORM、Migration 或前端，不运行完整 CUAD；真实 DeepSeek smoke 另见下条。
- Configuration note: 仓库 `.env` 未被修改或输出，当前 smoke 仅确认 API Key configured 状态为 yes；费用因未配置价格保持 `Not Calculated - Pricing Not Configured`。
- Controlled DeepSeek smoke: run `evaluation/outputs/smoke-deepseek-intl-20260821T000000Z/`，仅使用 Test 的 1 contract / 3 samples / 2 categories plus one no-answer sample，目标 `api.deepseek.com/chat/completions`，模型 `deepseek-v4-flash`；5/5 请求均在硬上限内（3 initial + 2 controlled repair，`max_retries=0`），2 samples completed、1 sample final `MODEL_EVIDENCE_MISSING`，provider failure rate 33.33%，14,218 input / 339 output / 14,557 total tokens。未观察到 authentication、DNS、TLS、429 或 5xx 错误，因此 endpoint connectivity passed，structured-output smoke partially passed。CLI 当前未持久化每次请求 latency 和逐次 JSON/schema counter，报告已明确标注该限制。
- Next gate: 完整 CUAD test、正式指标和中文产品 gold set 仍未完成；后续必须单独确认全量请求预算、价格、Prompt/Schema 和预期费用，再启动正式评测。

## Remaining Phases

正式 Phase 15 release evaluation 与 Phase 16 均为 `Not Started`。本批次仅完成 Phase 15 的独立 CUAD 资产准备，Phase 14B 已完成并停止于本状态记录；不得进入后续 Phase，范围、依赖和验收标准见 `docs/development-plan.md`，不得因原型已经存在而提前实现。

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
