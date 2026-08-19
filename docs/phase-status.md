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

- Last updated: `2026-08-19`
- Branch: `main`
- Verification baseline: `5687770` (`docs(phase): record Phase 6 snapshot`).
- Working tree at verification start: clean at the published Phase 6 baseline; Phase 7 implementation and verification changes remain uncommitted in the working tree.
- Current boundary: Phase 0 through Phase 7 are `Completed` with migration, integration, frontend quality and review evidence recorded below. Phase 8A/8B and later phases remain `Not Started`.
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
- Git branch / HEAD / status / diff summary: `main` / `5687770`；工作区保留本 Phase 未提交修改，包含文档契约/规范、后端解析/OCR/模型/Migration/测试、前端 CONTRACT-005/API/Vitest/Playwright；未包含 Secret、`.env`、原始合同、模型缓存或生成报告；用户已有 Phase 7 修改未被覆盖。
- Commit / Push: 未执行 Commit、Push、amend 或 force push，遵守用户约束。
- Next Phase and entry conditions: Phase 8A/8B 保持 `Not Started`；进入前按 `docs/development-plan.md` 重新 Review P-04/P-05、规则/模板版本契约和并行 Migration merge 计划。

## Remaining Phases

Phase 8A、Phase 8B 及 Phase 9A-16 均为 `Not Started`。范围、依赖和验收标准见 `docs/development-plan.md`；不得因原型已经存在而提前实现。

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
