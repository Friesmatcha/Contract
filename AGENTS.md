# AGENTS.md

本文件规定 Codex 在本仓库中的长期工程行为。业务与实现细节留在 `docs/`；此处只定义工作方式、边界和完成标准。

## Project Overview

- Frontend: Vue 3, TypeScript, Vite, Element Plus, Vue Router, Vitest, Vue Testing Library, Playwright.
- Backend: Python 3.12, FastAPI, Pydantic 2, SQLAlchemy 2, Alembic.
- Persistence: PostgreSQL 16+；所有环境统一使用 PostgreSQL。
- Async: Celery + Redis；PostgreSQL 保存业务事实，Redis 不作事实来源。
- Files: 本地持久卷、ClamAV、文档解析和 OCR，通过明确存储/解析边界访问。
- AI: Qwen 仅经 `ModelGateway`；普通自动化测试使用 Fake Model Gateway。
- Deployment: Docker Compose、反向代理、前后端同源部署。
- 不引入 `docs/architecture.md` 未采用的技术；详细设计见四份 Source of Truth 文档。

## Source of Truth

- `docs/requirements.md`: 业务需求、范围和验收目标，即“做什么”。
- `docs/architecture.md`: 技术架构、边界和实现约束，即“怎么设计”。
- `docs/api-contract.md`: 前后端 API 的唯一人工语义契约来源，即“如何通信”。
- `docs/development-plan.md`: Phase 顺序、依赖、测试和验收计划，即“何时开发”。
- `docs/phase-status.md`: 项目实际 Phase 进度和完成证据记录，即“当前完成到哪里”。
- `docs/ui/README.md`、`docs/ui/frontend-prd.md`、`docs/ui/design-system.md` 和 `docs/ui/stitch/`: 前端页面、视觉规范、原型资产和 UI 验收依据。
- 发现冲突时不得由代码暗中选择语义。执行：发现冲突 -> 判断是否阻塞当前 Phase -> 阻塞则报告 -> 更新对应规范文档 -> Review -> 再实现。
- 非阻塞冲突记录在完成报告、Known Issues、Future Work 或 issue；本 Phase 不擅自修复。

## Phase-Driven Development

- 严格按 `docs/development-plan.md` 的当前 Phase 工作，不提前实现未来 Phase。
- 每次任务依次检查：当前 Phase、相关需求、相关 API Contract、现有实现、相关测试、`git status` 和 `git diff`。
- 标准循环：Plan -> Implement -> Test -> Review -> Fix -> Regression -> Git Snapshot -> Next Phase。
- 进入下一 Phase 前，当前 Phase 的验收、阻塞 Review finding、必要回归和 diff review 必须完成。

## Scope Control

- 只修改完成当前任务所必需的文件和行为。
- 禁止顺便重构模块、统一全仓风格、升级依赖、改变架构、实现未来 Phase、创建推测性 abstraction 或批量格式化无关文件。
- 禁止修改无关 API、Migration 或 Bug；将其记录为 Known Issue/Future Work/issue。
- 仅当安全漏洞、数据损坏风险、API Contract 阻塞、当前 Phase 无法测试或现有架构无法正确承载当前修改时扩大范围，并在扩大前说明原因。

## Existing User Changes

- 修改前运行 `git status` 和 `git diff`；用户已有未提交修改均为受保护内容。
- 禁止 `git reset --hard`、强制 checkout、恢复/覆盖用户修改、删除未知文件、清理无关 untracked 文件、强制 push 或擅自 amend。
- 与任务交叉的用户修改应先理解，再围绕其继续工作；不得通过恢复仓库状态解决冲突。

## API Contract Rules

- 涉及 API 时逐项核对 Method、Path、Path/Query Params、Request、Response、Error、HTTP Status、Authentication、Authorization、Idempotency 和 State Transition。
- 固定流程：Update Contract -> Review Contract -> Backend Schema -> Service -> API -> Backend Tests -> OpenAPI Check -> Frontend Types -> API Client -> UI -> Integration -> Regression。
- 禁止前后端自行发明字段、采用不同 enum、先写代码后补契约，或用生成 OpenAPI 覆盖人工 Review 的 Markdown 契约。
- OpenAPI 是可执行投影，不是业务语义主来源；任何后端 API 变化都要检查全部调用方。

## Backend Architecture Rules

- Router/API 层保持薄；Pydantic Schema 定义接口输入输出；核心规则进入 Service/Domain 层。
- 外部依赖只经明确 Integration/Gateway 边界；不在 Router 堆复杂 ORM、事务和业务判断。
- SQLAlchemy Session 生命周期和业务事务边界必须明确；审计与对应业务变更按架构要求同事务提交。
- 受保护接口统一执行会话、Origin/CSRF、角色和资源范围校验；异常响应不得泄露内部细节。
- Celery task 只负责执行/编排，调用可测试的 service，不成为大型业务逻辑容器。
- 所有组织级查询显式 tenant scope；不信任客户端提交的 organization、role、permission 或资源归属。

## Tenant and Authorization Safety

- 前端隐藏按钮、客户端 `organization_id`/role 和 URL 可见性都不是授权边界；后端必须验证。
- 所有组织资源基于可信 tenant context 查询，并验证 membership、role/permission、资源归属和 viewer 资源级授权。
- 使用复合 tenant 外键等数据库约束阻止跨组织关联；防止跨组织 ID 枚举和越权下载。
- 平台临时支持访问须符合 API Contract：限时、默认只读、无未授权下载、每次访问可审计。

## Database Rules

- Schema 变更同时考虑 SQLAlchemy Model、Alembic Migration、外键、复合 tenant key、唯一/CHECK 约束、部分唯一索引、索引、事务、恢复和测试。
- 数据库承担必要完整性与并发约束；不得仅用 `SELECT first -> if absent -> INSERT` 保证唯一性。
- ORM 与 Migration 在同一 Phase 交付，并用真实 PostgreSQL 验证关键约束。

## Migration Rules

- Migration 只向前追加；不删除历史、不修改稳定/已发布 revision、不手工修改生产数据库。
- 每个适用 Phase 至少验证 `upgrade -> downgrade -> upgrade`；不可逆变更须说明恢复方案。
- 应用回滚不自动假设数据库 downgrade；生产破坏性变更采用 `expand -> data migrate -> contract`。
- 独立 branch/worktree 产生多个 Alembic head 时优先 `alembic merge`；禁止为线性历史重写已 Review 的 Migration。

## Async Processing

- 异步任务必须设计 idempotency、retry、duplicate delivery、lease、heartbeat、crash recovery、stage state、事务边界、补偿和并发限制。
- 不得假设 Celery task 只执行一次；Worker 崩溃和消息重投后系统仍须一致。
- 成功阶段不得因无意义重试重复产生费用、AI 调用、文件、Result 或 Warning。

## External Integrations

- Qwen、OCR、SMTP、ClamAV、File Store、HTML/PDF renderer 均通过明确 Adapter/Gateway；业务代码不得散布 SDK/HTTP 调用。
- 普通自动化测试不得依赖真实付费 Qwen、真实 SMTP 或不稳定公网服务；提供可控 Fake/fixture。
- 真实服务仅用于明确的 integration smoke 或受保护环境测试。

## Model Output Safety

- 模型输出一律视为 untrusted structured input，执行 JSON/schema、enum、evidence 和业务校验，并设置有限 retry 与失败边界。
- 不因模型结论直接写入“已确认”状态；要求证据的结果没有合法 SourceSpan/Evidence 时不得伪造证据。
- 日志不得保存完整合同正文、API Key、Token、Secret、完整敏感模型输入或未过滤的完整模型响应。

## File Security

- 不信任 filename、extension 或 MIME header；按架构/契约执行流式、大小、签名、配额和病毒校验。
- 使用安全随机存储键、隔离区、扫描后安全原子移动；用户文件名只作元数据，不作文件系统路径。
- 每次下载重新验证资源、tenant 和授权；不得公开静态业务文件目录。

## Frontend Rules

- 使用 Vue 3 + TypeScript；无明确理由不用 `any`。
- API 调用集中于 API Client/feature service；类型与 OpenAPI 投影一致，语义回查 `docs/api-contract.md`。
- 前端任务开始前必须读取 `docs/phase-status.md`、`docs/ui/README.md`、`docs/ui/frontend-prd.md`、`docs/ui/design-system.md`、目标 Page ID 对应的 `docs/ui/stitch/` 原型和相关 `docs/api-contract.md` 条目。
- API 的 Method、Path、参数、权限、错误和状态只能来自 `docs/api-contract.md`；Vue Page URL 必须在 `frontend-prd.md` 中记录为 API 资源/动作的明确映射，不得自行发明接口路径。
- HTML/PNG 原型是视觉、布局和交互状态的参考/验收资产，不是生产代码；不得复制原型中的 CDN、Tailwind、外部字体、Material Symbols、静态假数据或模拟业务逻辑。
- 页面实现必须覆盖适用的 loading、empty、error、forbidden、conflict、disabled、processing 和 retry 状态，并在 1440px 与 1280px 下验证。
- 页面不堆复杂请求或状态机；公共逻辑按真实复用需要抽为 composable/service，避免过度抽象。
- 权限 UI 只改善体验；主要页面覆盖 loading、empty、error、forbidden、conflict、disabled 和 retry 状态。

## Phase Status Recording

- 每个 Phase 完成后，必须先更新 `docs/phase-status.md`，记录完成边界、测试命令和结果、Review、Migration、API/UI 状态、Known Issues、下一步和 Git Snapshot，再进入下一 Phase。
- 未完成当前 Phase 的验收、必要回归、独立 Review 或阻塞 Pending Decision 时，不得标记为 `Completed`。
- 每次会话开始以 `docs/phase-status.md` 判断实际开发位置，不以 README、Git commit 名称或旧文档中的 Current Project State 推测 Phase。

## Testing Rules

- Backend 常用门禁：`python -m pytest backend/tests`、`python -m ruff check backend`、`python -m mypy backend/app`。
- Frontend 常用门禁：`npm --prefix frontend run lint`、`npm --prefix frontend run typecheck`、`npm --prefix frontend run test`、`npm --prefix frontend run build`。
- 关键用户路径运行对应 Playwright E2E；先跑当前 Phase 测试，再跑直接相关历史回归。
- Authentication、Authorization、Tenant Context、API Client、共享 Model/Migration、Worker 或 State Machine 变化必须扩大 Regression。
- 禁止删除失败测试、弱化 assertion、用 fixture 掩盖 Bug，或 mock 掉本应验证的业务规则。
- 只报告实际执行结果；未运行测试必须说明原因。

## Review Rules

- 重要 Phase 由未主导实现者或独立 Codex Review；不得只依赖实现者自评。
- Review 检查 requirements、API Contract、tenant/RBAC、状态机、事务/并发/幂等、Migration、安全、文件、AI 校验、前后端一致、测试覆盖和无关修改。
- 流程：Review -> Fix -> Regression -> Re-review blocking findings -> Git Snapshot；阻塞 finding 未关闭不得进入下一 Phase。

## Git Rules

- 每个 Phase 目标是一个可独立理解的 Git Snapshot：Stable Baseline -> Development -> Test -> Review -> Fix -> Regression -> Diff Review -> Commit -> Next Phase。
- 未经用户明确要求不得 Commit 或 Push；完成后可建议 commit message。
- 禁止 force push、`reset --hard`、修改历史 commit、删除未知 branch、覆盖用户修改，或提交 `.env`/Secret。

## Pending Decisions

- 读取 `docs/development-plan.md` 的 Pending Decisions，并采用 Just-in-Time Decision。
- 仅在待决事项即将影响当前 Phase 或阻塞 API、数据模型、测试、安全规则时，于编码前解决并更新规范。
- 远期 Phase 的待决事项不阻塞早期 Phase；不得擅自决定未确认的产品语义。

## Secrets

- 禁止提交 `.env`、Qwen API key、数据库/SMTP/Redis 密码、私有证书或 session secret。
- Secret 仅通过 environment 或部署 Secret injection；`.env.example` 只含变量名、安全占位值和必要说明。

## Completion Report

- **Changes**: 列出修改文件、实现内容和明确未做内容。
- **Tests**: 列出真实命令及 passed/failed/skipped/warnings；未运行时说明原因，不写笼统的 “Tests look good”。
- **Contract / Database**: 说明 API Contract、ORM、Migration、OpenAPI 是否变化。
- **Risks / Known Issues**: 说明已知问题、未覆盖场景和 Future Work。
- **Git**: 报告 branch、HEAD、`git status`、diff summary、用户原有修改、当前任务修改，以及是否 Commit/Push。
- 未经用户要求，最终报告必须明确未执行 Commit/Push。
