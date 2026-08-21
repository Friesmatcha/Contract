# Development Plan

## 1. Document Purpose

本文档把 `docs/requirements.md`、`docs/architecture.md` 和 `docs/api-contract.md` 转换为可直接执行的全栈开发顺序。每个 Phase 以可验证的业务能力为边界，必须能够独立开发、测试、Review、修复、回归并形成 Git Snapshot。

本计划不修改业务需求。`docs/api-contract.md` 是前后端接口的唯一契约来源；架构文档提供实现约束，需求文档提供业务目标和验收依据。若三者冲突，必须先按本文“待确认事项”处理，不允许代码自行选择另一种语义。

本文件定义 Phase 顺序、范围、依赖和验收标准；仓库实际完成到哪里以 `docs/phase-status.md` 为唯一人工记录。每次会话开始先读取 Phase Status，每个 Phase 完成后先更新该记录，再进入下一 Phase。

## 2. Current Project State

- 当前仓库已进入正式编码阶段，包含 `backend/`、`frontend/`、Alembic Migration、自动化测试、Docker Compose 和 UI 原型资产。
- Git 历史已有 Phase 0 工程骨架、Phase 1 共享持久化/API 基础和 Phase 2 认证实现快照；这些历史 Phase 的正式完成状态以 `docs/phase-status.md` 中归档的测试、Review 和回归证据为准，不只依据 commit 名称判断。
- 技术基线已明确为 Vue 3 + TypeScript + Vite + Element Plus、Python 3.12 + FastAPI + Pydantic 2 + SQLAlchemy 2 + Alembic、PostgreSQL 16+、Celery + Redis、ClamAV、本地持久卷和单机 Docker Compose。
- API 契约共 75 个接口，覆盖认证、组织、合同、审核、规则、模板、预警、通知、报告、反馈、审计、运营和健康检查。
- 前端 PRD、设计系统和 Stitch HTML/PNG 原型位于 `docs/ui/`；原型已经存在不代表对应实现 Phase 已开始或完成。

### 2.1 一致性检查结论

| 检查项 | 发现 | 处理方式 |
| --- | --- | --- |
| 核心流程 | 需求流程写成“创建审核任务 -> 上传合同”，架构和 API 要求“合同 -> 文件 -> 审核任务” | 采用 API 契约三步资源流程；不提供聚合上传接口 |
| 数据库 | 需求允许开发环境 MySQL，架构和 API 统一 PostgreSQL | 全环境使用 PostgreSQL，不建立 MySQL 分支 |
| 并发默认值 | 架构第 18 节建议每组织 2 个，API 已确认 3 个 | 采用 API 已确认值 3 |
| 报告交付 | 旧分期文字把 PDF 放在第二阶段，API 已确认首期同时交付 HTML/PDF | Phase 13 同时实现 HTML/PDF |
| 审核员范围 | 架构权限表一处写“本组织业务范围”，API 明确本组织全部合同 | 采用 API：审核员可查看和处理本组织全部合同 |
| 模型配置 | 架构数据模型允许组织配置/覆盖，API 明确组织不得覆盖，模型名和密钥来自环境 | 采用 API；只保留平台非秘密运行参数配置 |
| OpenAPI 定位 | 架构称 OpenAPI 为契约来源，API 文档称自身为唯一契约来源 | Markdown 契约先行；OpenAPI 是后端 Schema 生成的可执行投影，CI 校验二者一致 |
| 抽取状态 | 公共 `result_status` 已统一使用 `detected`；旧结果示例和字段修订接口曾使用 `found` | P-03 已关闭；按 API Contract 使用 `detected`，缺失值使用 `not_found|needs_confirmation` |
| 组织上下文 | API Contract 2.2.1 已定义 `X-Organization-ID`、单组织自动选择、多组织 409 和 membership 校验；实现仍需在 Phase 3 组织接口中验证 | P-01 已关闭；按契约实现并测试 |
| 默认版本选择 | 创建审核可省略规则/模板版本，但多规则集/多模板时默认选择规则未定义 | P-04/P-05 已关闭；以 API 11.4/12.4 的显式默认切换、数据库唯一约束和 10.1 的 409 配置错误为准 |
| 报告恢复 | 需求要求报告失败后可重新生成，API 未完整定义报告状态和失败后的再次 POST 语义 | 在 Phase 13 前确认并修订契约 |
| 任务归档/取消 | 架构状态机提到取消且含 `archived`，API 没有审核任务取消/归档接口 | 本计划不实现未定义命令；在进入 Phase 9A 前确认归档来源 |
| 批量审核 | 需求和架构第三阶段提到批量审核，API 无批量接口 | 记录为 Future Work；契约补齐前不实现 |
| 数据模型 | API 需要临时支持授权、邀请投递信息、通知标题正文、资源乐观锁版本等字段，架构表未完整列出 | 以契约行为补齐最小数据模型，并在首次 Migration Review 时留痕 |

### 2.2 设计假设

以下是可由最小工程实现解决、不改变业务目标的假设：

- 使用标准 `pyproject.toml` 管理 Python 项目，使用 `npm` 管理前端；若 Phase 0 决定更换工具，只能改变命令，不得改变门禁。
- 所有业务 Migration 按 Phase 增量创建；Phase 0 只初始化 Alembic，不能预建全部业务表。
- `audit_logs.organization_id` 对平台级事件允许为空；组织级业务事件必须非空。审计摘要不保存合同正文、令牌、密钥或完整模型响应。
- 待邀请成员允许暂时没有 `user_id`；邀请令牌引用待邀请成员记录，接受后在同一事务中绑定或创建用户。
- 站内通知的已读状态与异步投递状态分列保存，避免一个 `status` 同时承担两种状态机；API 仍只返回契约定义的字段。
- API 返回资源使用递增 `version` 的，数据库必须有对应乐观锁字段；不可变事实表不增加无意义的更新版本。
- 普通 CI 使用 Fake Model Gateway、固定 OCR/模型样本，不调用付费千问 API；真实千问仅在受保护环境手工冒烟。
- Phase 8A 和 8B 可以在隔离分支/工作树并行。单一 Codex 顺序执行时按 8A 后 8B 处理，以减少合并成本。

## 3. Development Principles

每个 Phase 严格执行：

```text
Plan
-> Implement
-> Test
-> Review
-> Fix
-> Regression
-> Git Snapshot
-> Next Phase
```

通用规则：

1. 只实现当前 Phase 必须完成的内容，不顺便重构、升级依赖、改变架构、开发未来 Phase 或格式化无关文件。
2. 涉及 API 时，先核对 Method、Path、Request、Response、Error、权限、状态码；契约不完整时先修改并 Review `docs/api-contract.md`，再写后端和前端。
3. 涉及数据库时，同时交付 ORM Model、Migration、约束、索引、事务边界、回滚验证和数据完整性测试。
4. 前后端功能遵循：契约 -> 数据模型 -> Backend Schema -> Service -> API -> Backend Test -> Frontend Type -> API Client -> UI -> Integration -> Regression。
5. 不以 UI 隐藏代替后端权限；不信任客户端组织、角色、风险等级、存储键或报告内容。
6. 每个 Phase 完成前检查 Git diff；发现跨 Phase 问题只记录到 Known Issues / Future Work。

Pending Decision 应在其最早影响 Phase 开始前关闭。除非问题影响当前 Phase 的架构、数据模型或接口，否则不得阻止更早 Phase 开发；远期业务语义不提前替用户决定。

## 4. Overall Roadmap

```text
Phase 0 -> Phase 1 -> Phase 2 -> Phase 3
                              |
                              +-> Phase 4 -> Phase 5 -> Phase 6 -> Phase 7 ----+
                              |                                                |
                              +-> Phase 8A -----------------------------------+
                              |                                                |
                              +-> Phase 8B -----------------------------------+
                                                                               |
                                                                               v
                                                                         Phase 9A
                                                                               |
                                                                               v
                                                                         Phase 9B
                                                                               |
                                                                               v
                                                                         Phase 9C
                                                                               |
                                                                               v
Phase 16 <- Phase 15 <- Phase 14B <- Phase 14A <- Phase 13 <- Phase 12 <- Phase 11 <- Phase 10 <-+
```

- 串行主链：Phase 0-3、Phase 9A-16 必须串行。
- 可并行分支：Phase 4-7（成员/合同/文件/解析）、Phase 8A（风险规则）和 Phase 8B（条款模板）只依赖 Phase 3，可在隔离分支并行。
- 并行边界：8A 只改 `risks` 模块及其 Migration/UI；8B 只改 `clauses` 模块及其 Migration/UI；Phase 4-7 不修改规则和模板表。
- 合并条件：三条功能分支均从相同 Phase 3 基线开始，分别通过 Migration upgrade/downgrade、测试和 Review；8A/8B 先通过显式 merge revision 汇合，如 Phase 4-7 也形成独立 head，再通过第二个无 schema change 的 merge revision 形成 Unified Head，之后进入 Phase 9A。

### 4.1 API 覆盖映射

| API 模块 | 数量 | 实现 Phase |
| --- | ---: | --- |
| Authentication | 6 | Phase 2 |
| Organization and User | 18 | Phase 3（9）、Phase 4（7）、Phase 5（2） |
| Contract and File | 9 | Phase 5（6）、Phase 6（2）、Phase 7（1） |
| Review Task and Result | 9 | Phase 9A（3）、Phase 9C（1）、Phase 12（5） |
| Risk Rule | 8 | Phase 8A |
| Clause Template | 8 | Phase 8B |
| Warning | 3 | Phase 11 |
| Notification | 3 | Phase 11 |
| Report | 3 | Phase 13 |
| Feedback | 2 | Phase 12 |
| Audit, Operations and Health | 6 | Phase 0（2）、Phase 14A（4） |
| **总计** | **75** | 全部已安排 |

### 4.2 需求覆盖映射

| 需求组 | 主要 Phase |
| --- | --- |
| FR-A 认证、组织、权限、审计 | 1-5、14、15 |
| FR-D 合同上传、解析、OCR、预览、重试 | 5-7、9A、9C、15 |
| FR-E 分类与要素抽取 | 9B、9C、12、15 |
| FR-R 风险识别与分级 | 8A、9B、10、12、15 |
| FR-W 预警、通知、分派、处置 | 11、12、15 |
| FR-C 标准条款与比对 | 8B、9B、10、12、15 |
| FR-RP 结果页和 HTML/PDF 报告 | 10、12、13、15 |
| FR-F 反馈与标注 | 12、14、15 |
| FR-O 配置、指标、成本、保留期 | 3、9B、14A-16 |
| 准确性、安全、性能、部署 | 15-16；安全和可解释性门禁贯穿所有 Phase |

## 5. Milestones

| Milestone | 包含 Phase | 完成结果 |
| --- | --- | --- |
| M1 Engineering Baseline | 0-1 | 工程可启动、构建、测试，数据库和公共约定可验证 |
| M2 Identity and Content Foundation | 2-8B | 身份、组织、合同、文件、解析、规则和模板管理可用 |
| M3 Review MVP | 9A-11 | 异步审核、模型边界、分类抽取、结果、预警和站内通知形成机器初审闭环 |
| M4 Integrated MVP | 12-13 | 人工复核、反馈、完成审核和 HTML/PDF 报告形成完整用户闭环 |
| M5 Production Ready | 14A-16 | 审计运营、保留清理、评测、安全性能回归、Compose 部署和 Release 完成 |

## Phase 0：Project Bootstrap / 工程骨架初始化

### 目标

建立一个可以启动、测试、构建、继续开发的稳定工程基线，不实现任何正式业务功能。

### 实现范围

- 做：创建建议目录；初始化 FastAPI、Vue Router、API Client 基础层、PostgreSQL 连接框架、Alembic、Celery/Redis 入口、日志、同源 CORS/Origin 基础配置、环境变量模板、README、`.gitignore`、lint/typecheck/test/build、基础 Docker Compose 和健康检查。
- 不做：登录、业务表、业务 CRUD、权限策略、正式页面、OCR/千问调用、业务种子数据或任何后续 Phase。

### 前置依赖

- 三份基线文档已存在；Python 3.12、Node LTS、Docker/Compose 可由开发环境提供。
- Phase 0 不依赖真实千问、SMTP、OCR 模型或业务测试数据。

### 预计涉及模块

```text
backend/app/{main.py,config.py,db.py,logging.py}
backend/app/api/health.py
backend/app/worker/
backend/migrations/
backend/tests/
frontend/src/{api,router,pages}
frontend/tests/
deploy/compose/
.env.example
.gitignore
README.md
```

### 后端任务

- 初始化 FastAPI、Pydantic Settings、SQLAlchemy Session、Alembic、Celery app 和结构化日志。
- 实现统一配置加载失败、Request ID 和最小错误响应基础层。
- 实现 live/ready；ready 只检查数据库和关键配置，不检查千问瞬时可用性。
- 初始化 pytest、ruff、类型检查和测试数据库配置；不创建业务 Model/Migration。

### 前端任务

- 初始化 Vue 3 + TypeScript + Vite + Element Plus、Router、Vitest + Vue Testing Library。
- 建立薄 `fetch` Client、Cookie credentials 和错误解析骨架；只做占位路由/启动页，不做业务页面。
- 建立 lint、typecheck、test、build 脚本。

### API Contract

- `GET /api/v1/health/live`
- `GET /api/v1/health/ready`
- 如健康响应或暴露范围需改变，必须先改契约。

### 数据库变更

- 无业务表；只初始化连接和 Alembic 目录。
- 不允许生成包含业务实体的初始 Migration。

### 测试要求

```bash
python -m pytest backend/tests
python -m ruff check backend
python -m mypy backend/app
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
docker compose -f deploy/compose/compose.yml config
```

### 验收标准

- API、Worker 和前端均能启动；live 返回 200，数据库可用时 ready 返回 200，配置/数据库不可用时返回安全的 503。
- 空数据库可以执行 `alembic upgrade head`；前后端测试、lint、typecheck、build 全部通过。
- `.env.example` 不包含真实秘密；日志和错误不泄露连接串。
- Compose 配置可解析，服务名与架构一致，但无需完成生产加固。

### 完成条件

- 本阶段功能、测试、lint、typecheck、build、README 和环境模板完成。
- 无业务代码或业务数据；Git diff 已检查，无无关修改和已知阻塞错误。

### Git Snapshot

```text
chore(bootstrap): initialize full-stack project baseline
```

## Phase 1：Shared Persistence and API Invariants / 数据与接口公共基线

### 目标

建立后续模块共同依赖的租户数据根、事务、游标、幂等、审计写入和错误约定，并通过真实 PostgreSQL 约束测试。

### 实现范围

- 做：`organizations`、`users`、`organization_memberships` 最小根模型；UUID/UTC/version 约定；事务 Unit of Work；游标分页；幂等记录；审计追加写；通用错误映射。
- 不做：认证接口、组织 CRUD、角色业务策略、合同或审核表。

### 前置依赖

- Phase 0；API 全局约定第 2、4、6、7 节；架构数据库通用约定。
- P-02 已关闭：组织级使用服务端可信 Tenant Context 生成 `organization:<organization_id>`，无组织上下文的平台级写接口使用已认证平台操作主体生成 `platform:<authenticated_user_id>`；详见 API Contract 2.3。

### 预计涉及模块

```text
backend/app/shared/{db,errors,pagination,idempotency,tenant,audit}
backend/app/modules/identity/models.py
backend/migrations/versions/
backend/tests/{unit,integration}/shared/
```

### 后端任务

- 建立根实体、复合租户键、邮箱规范化唯一约束和基础索引。
- 实现事务内幂等记录与请求摘要校验、稳定游标、审计 append 服务、公共错误结构。
- 为后续服务提供显式 tenant context；禁止隐式全组织查询。

### 前端任务

- 定义通用 `ApiError`、`CursorPage<T>`、Request ID 捕获和安全错误展示类型。
- 无正式页面。

### API Contract

- 不新增业务接口；落实全局约定 2.1-2.5、分页第 7 节和权限校验顺序。

### 数据库变更

- 新增 `organizations`、`users`、`organization_memberships`、`idempotency_records`、`audit_logs`。
- `idempotency_records` 使用服务端生成的 scope，并以 `(scope, idempotency_key)` 建立数据库唯一约束；不得采用客户端 scope 或仅支持 organization 的结构。
- 增加规范化邮箱唯一约束、租户复合唯一约束、游标排序索引和追加写限制。
- Migration 必须验证 upgrade/downgrade；测试数据只在测试 fixture 中创建。

### 测试要求

```bash
python -m pytest backend/tests/unit/shared backend/tests/integration/shared
python -m alembic upgrade head
python -m alembic downgrade -1
python -m alembic upgrade head
python -m ruff check backend
python -m mypy backend/app
npm --prefix frontend run typecheck
```

### 验收标准

- 跨组织复合关联失败；规范化重复邮箱失败；审计写入与业务事务共同提交/回滚。
- 同一组织或平台主体作用域内，相同幂等键同请求可重放，不同请求返回 409；不同组织和不同平台主体可独立复用相同键；游标排序稳定且未知筛选返回 422。
- 错误响应符合契约且不包含 SQL、路径、堆栈或秘密。

### 完成条件

- Migration、约束、事务、幂等、分页和审计基础测试通过；lint/typecheck/build 相关门禁通过。
- 文档同步且 Git diff 已检查，无后续业务实现。

### Git Snapshot

```text
feat(core): add tenant persistence and API invariants
```

## Phase 2：Authentication and Session Security / 认证与会话安全

### 目标

用户可安全登录、查询会话、退出、重置密码和接受邀请；所有受保护接口具备统一会话、Origin 和 CSRF 基线。

### 实现范围

- 做：不透明 Cookie、Argon2id、CSRF、会话撤销、一次性令牌、限流、SMTP 身份邮件适配、登录/重置/邀请前端流程。
- 不做：组织管理页面、成员邀请发起、合同权限或业务 CRUD。

### 前置依赖

- Phase 1；确认当前组织选择机制、密码策略、令牌 TTL、SMTP 发件人与前端链接基址。
- SMTP 可在测试中使用 Fake，不要求真实服务。

### 预计涉及模块

```text
backend/app/modules/identity/
backend/app/integrations/notifications/smtp.py
backend/migrations/versions/
backend/tests/{unit,integration}/auth/
frontend/src/features/auth/
frontend/src/pages/auth/
frontend/tests/auth/
```

### 后端任务

- 新增会话和一次性令牌 Model/Migration；仅存令牌哈希。
- 实现 6 个认证接口、Cookie 属性、CSRF 轮换、Origin 校验、账号枚举防护、用户停用/密码重置会话撤销。
- 邀请接受事务支持新用户与已有用户，写入必要审计。

### 前端任务

- 登录、密码重置请求/确认、邀请接受页面；会话 Store；路由守卫。
- API Client 自动携带 Cookie，在非安全方法附加 CSRF；处理过期会话、字段错误、loading 和重复提交。

### API Contract

- Authentication 3.2-3.7，共 6 个接口。
- 实现前必须补齐当前组织选择和密码策略的契约说明。

### 数据库变更

- 新增 `auth_sessions`、`auth_one_time_tokens`；为待邀请成员补充最小邀请关联字段。
- 会话令牌哈希唯一；一次性令牌用途/过期/消费约束；相关查询索引。

### 测试要求

```bash
python -m pytest backend/tests/unit/auth backend/tests/integration/auth
npm --prefix frontend run test -- auth
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

### 验收标准

- 正确凭据返回 200 并设置安全 Cookie；错误密码返回 401；禁用用户返回 403；响应不含会话令牌。
- 未登录访问受保护资源返回 401；缺失/错误 CSRF 或 Origin 的写请求被拒绝。
- 密码重置不泄露邮箱是否存在；令牌只能使用一次，成功后撤销既有会话。
- 新/已有用户均可接受有效邀请；过期、已用和错误令牌按契约失败。
- 前端完成上述流程并展示安全、可读错误；相关审计和测试通过。

### 完成条件

- 功能、Migration、单元/集成/前端测试、lint、typecheck、build、Review 和回归完成。
- 契约及安全配置文档同步，Git diff 已检查。

### Git Snapshot

```text
feat(auth): implement secure session authentication
```

## Phase 3：Platform and Organization Configuration / 平台与组织配置

### 目标

平台管理员可管理组织和非秘密模型运行参数，组织成员可读取组织资料，组织管理员可维护非秘密组织设置。

### 实现范围

- 做：平台组织列表/创建/详情/更新、组织资料与设置、平台模型配置、权限和审计、对应管理 UI。
- 不做：成员邀请、合同、组织级模型覆盖、通过 API 修改模型名或密钥。

### 前置依赖

- Phase 2；API 已确认模型名/密钥来自环境、组织不能覆盖。

### 预计涉及模块

```text
backend/app/modules/identity/{organization,model_configuration}/
backend/migrations/versions/
backend/tests/{api,authorization}/organizations/
frontend/src/features/admin/{organizations,settings,model}/
```

### 后端任务

- 实现平台/组织授权、设置 Schema 白名单、版本冲突、组织停用带来的会话和访问处理。
- 模型配置只保存可 API 修改的非秘密字段；密钥和模型名读取环境且只返回配置状态。
- 创建组织事务只建立初始管理员的待邀请记录及基线配置引用；邀请令牌签发和 SMTP 投递由 Phase 4 完成，Phase 3 不调用未来阶段服务。

### 前端任务

- 平台组织列表/详情/编辑、组织设置页、平台模型配置页。
- 根据后端 `permissions` 控制入口；处理游标、空态、冲突、禁用和秘密未配置状态。

### API Contract

- 8.1-8.9，共 9 个接口。

### 数据库变更

- 扩展 `organizations` 设置/version 字段；新增平台模型非秘密配置或等价单例配置表。
- 增加组织名称冲突策略、状态/版本约束和必要索引；Migration 可回滚。

### 测试要求

```bash
python -m pytest backend/tests/api/organizations backend/tests/authorization/organizations
npm --prefix frontend run test -- organizations settings model
python -m alembic upgrade head
python -m ruff check backend
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

### 验收标准

- 平台管理员完成 8.1-8.4、8.8-8.9；非平台用户均被拒绝。
- 组织成员只能读取所属组织资料；仅组织管理员可读写设置。
- 模型密钥、`secret_ref` 和会话信息不出现在响应/日志；组织不能覆盖平台模型。
- 版本冲突返回 409，组织设置默认值与 API 第 20 节一致。

### 完成条件

- 9 个接口、UI、Migration、权限/契约测试和通用质量门禁通过。
- Review、Fix、Regression、文档同步和 Git diff 检查完成。

### Git Snapshot

```text
feat(organizations): add platform and tenant configuration
```

## Phase 4：Membership, Invitation and Support Access / 成员与临时支持授权

### 目标

组织管理员可管理成员、邀请与受时限约束的平台只读支持授权，且全程可审计。

### 实现范围

- 做：成员列表、邀请/重发、角色和状态修改、支持授权查询/创建/撤销、SMTP 投递状态与会话撤销。
- 不做：合同 viewer 授权（Phase 5）、平台管理员业务下载、任何支持授权写操作。

### 前置依赖

- Phase 3；有效平台管理员、SMTP Fake/配置、审计写入基础。

### 预计涉及模块

```text
backend/app/modules/identity/{memberships,invitations,support_access}/
backend/migrations/versions/
backend/tests/{api,authorization}/memberships/
frontend/src/features/admin/{members,support-access}/
```

### 后端任务

- 实现成员角色/状态规则、最后一个组织管理员保护、邀请重发作废旧令牌。
- 新增临时支持授权 Model/Service；最长 4 小时、只读 JSON、即时撤销、访问逐次审计。
- 权限变化或停用成员时撤销相关会话。

### 前端任务

- 成员列表、邀请、角色/状态编辑、投递状态和支持授权管理页面。
- 支持到期时间校验、危险操作确认、loading/error/empty/conflict 状态。

### API Contract

- 8.10-8.13、8.16-8.18，共 7 个接口。

### 数据库变更

- 扩展成员邀请/投递/version 字段；新增 `support_access_grants`。
- 增加同组织成员唯一约束、活动支持授权冲突约束、过期查询索引和审计关联。

### 测试要求

```bash
python -m pytest backend/tests/api/memberships backend/tests/authorization/support_access
npm --prefix frontend run test -- members support-access
python -m alembic upgrade head
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

### 验收标准

- 组织管理员可邀请、重发、修改同组织成员；不能授予平台管理员或停用最后一个组织管理员。
- 重发使旧邀请令牌失效；SMTP 失败可见且不泄露令牌。
- 支持授权最长 4 小时、撤销立即生效；平台管理员无授权不能看业务 JSON，有授权仍不能写或下载。
- 授权创建/撤销/每次使用都产生不含正文的审计记录。

### 完成条件

- 7 个接口及 UI、Migration、SMTP Fake、权限和回归测试通过。
- lint/typecheck/build、Review、文档和 Git diff 检查完成。

### Git Snapshot

```text
feat(identity): add membership and support access workflows
```

## Phase 5：Contract Catalog and Viewer Access / 合同目录与查看授权

### 目标

组织管理员和审核员可管理合同元数据，viewer 只能访问明确授权合同，归档语义可验证。

### 实现范围

- 做：合同创建/列表/详情/编辑/归档/恢复、viewer 授权/撤销、游标筛选和权限隐藏。
- 不做：文件上传、解析、审核任务或物理删除。

### 前置依赖

- Phase 4；组织/成员权限稳定。本阶段不依赖 ReviewTask 抽象，也不预建审核仓储或临时业务接口。

### 预计涉及模块

```text
backend/app/modules/contracts/
backend/migrations/versions/
backend/tests/{api,authorization}/contracts/
frontend/src/features/contracts/
frontend/src/pages/contracts/
```

### 后端任务

- 实现 Contract Model/Schema/Service/API、展示编号、乐观锁、归档/恢复命令；归档 guard 只检查合同自身状态和已存在的合同数据。
- 实现 `contract_access_grants` 和 viewer 精确授权；越权资源使用 404 防枚举。
- 所有写操作与审计同事务。

### 前端任务

- 合同列表、创建、详情、元数据编辑、归档/恢复和 viewer 授权 UI。
- 支持筛选、游标分页、权限按钮、空态、冲突和归档只读状态。

### API Contract

- 9.1-9.6，共 6 个合同接口。
- 8.14-8.15，共 2 个合同查看授权接口。

### 数据库变更

- 新增 `contracts`、`contract_access_grants`。
- 组织内 `display_no` 唯一；复合外键阻止跨组织授权；viewer 授权唯一；常用列表索引。

### 测试要求

```bash
python -m pytest backend/tests/api/contracts backend/tests/authorization/contracts
npm --prefix frontend run test -- contracts
python -m alembic downgrade -1
python -m alembic upgrade head
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

### 验收标准

- 组织管理员/审核员可创建、读取和编辑本组织合同；viewer 只看到授权合同且不能写。
- 客户端提交组织 ID 不能越权；跨组织 ID 被隐藏或拒绝。
- 归档合同不可编辑；仅组织管理员可恢复。本阶段不判断 active ReviewTask；该 guard 在 Phase 9A 建立 ReviewTask 后补充。
- 授权/撤销幂等语义、版本冲突、筛选和稳定分页符合契约。

### 完成条件

- 8 个接口、UI、Migration、权限/约束/回归测试和质量门禁通过。
- Review、文档同步、Git diff 检查完成。

### Git Snapshot

```text
feat(contracts): add contract catalog and viewer access
```

## Phase 6：Secure File Lifecycle / 安全文件生命周期

### 目标

合同文件可被流式校验、病毒扫描、安全存储和授权下载，并记录外部模型告知确认。

### 实现范围

- 做：FileStore 最小边界、本地卷实现、隔离区、SHA-256、扩展名/MIME/签名/大小校验、ClamAV、文件版本和安全下载。
- 不做：文档解析/OCR、审核任务、对象存储实现或文件物理清理。

### 前置依赖

- Phase 5；ClamAV 和持久卷本地配置；API 已确认 20 MiB/100 页默认值及告知文案。

### 预计涉及模块

```text
backend/app/modules/contracts/files/
backend/app/integrations/{storage,antivirus}/
backend/migrations/versions/
backend/tests/{api,integration,golden}/files/
frontend/src/features/contracts/upload/
```

### 后端任务

- 新增文件对象/合同文件版本模型；上传流式计算大小和哈希，不一次读入内存。
- 扫描通过后原子移动到随机存储键；失败清理隔离临时文件并记录安全错误。
- 下载时重新加载合同并授权；安全设置 Content-Type/Length/Disposition 和限流。

### 前端任务

- 上传控件、进度、类型/大小错误、外部模型授权告知与强制确认。
- 文件版本列表和授权下载；处理中/失败/重复提交状态不改变页面布局。

### API Contract

- 9.7 上传合同文件。
- 9.8 下载原文件。

### 数据库变更

- 新增 `file_objects`、`contract_files`；告知确认时间/用户；scan/storage 状态字段。
- `storage_key` 全局唯一，合同文件版本在合同内唯一，current 版本唯一约束，组织复合外键和 SHA 索引。

### 测试要求

```bash
python -m pytest backend/tests/api/files backend/tests/integration/files
npm --prefix frontend run test -- upload
python -m alembic upgrade head
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

### 验收标准

- 合法 DOCX/PDF/PNG/JPG/JPEG 返回 201；超限 413；伪装/不支持 415；损坏文件 422；ClamAV 不可用 503。
- 未确认外部模型告知不能上传；确认时间可审计。
- 文件名不能控制存储路径；越权下载返回 404；平台支持授权不能下载。
- 重复幂等请求不产生重复文件版本；临时文件和失败事务可回收。

### 完成条件

- 2 个接口、UI、Migration、文件安全/权限/失败清理测试通过。
- lint/typecheck/build、Review、回归、文档和 Git diff 检查完成。

### Git Snapshot

```text
feat(files): implement secure contract file lifecycle
```

## Phase 7：Document Parsing, OCR and Evidence / 文档解析、OCR 与证据定位

### 目标

上传文件可解析为统一文档结构，PDF/图片和 DOCX 均可准确定位，OCR 低置信度与失败不会被静默忽略。

### 实现范围

- 做：DOCX、文本 PDF、扫描 PDF、PNG/JPEG 解析；页面/块/SourceSpan；OCR；解析指纹和幂等；页面/逻辑块预览。
- 不做：千问、风险判断、条款比对或正式审核编排。

### 前置依赖

- Phase 6；固定脱敏/生成金样；PaddleOCR CPU 模型和解析库版本；OCR 阈值 0.80。

### 预计涉及模块

```text
backend/app/modules/documents/
backend/app/integrations/ocr/
backend/migrations/versions/
backend/tests/{golden,integration}/documents/
frontend/src/features/documents/preview/
```

### 后端任务

- 实现 `DocumentVersion -> Page -> Block -> SourceSpan` 模型和解析服务。
- DOCX 保留段落/表格/顺序且不伪造页码；PDF/图片保留页码、坐标和字符区间。
- 低置信度/空白/单页失败写入页面状态；相同文件和解析配置复用成功结果。
- 实现页面/逻辑块读取 API 和访问授权。

### 前端任务

- 文档预览和 Locator 跳转：PDF/图片页码+bbox，DOCX 段落/表格+字符区间。
- 展示解析中、低置信度、局部失败、无物理页和无权限状态。

### API Contract

- 9.9 获取 PDF/图片物理页面；9.10 获取 DOCX 逻辑块。
- 解析/OCR 为内部边界，不新增浏览器供应商接口。

### 数据库变更

- 新增 `document_versions`、`document_pages`、`document_blocks`、`source_spans`。
- 增加解析指纹唯一约束、块顺序/页码唯一约束、组织复合外键和预览索引。

### 测试要求

```bash
python -m pytest backend/tests/golden/documents backend/tests/integration/documents
npm --prefix frontend run test -- document-preview
python -m alembic downgrade -1
python -m alembic upgrade head
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

### 验收标准

- 四类文件样本保持文本顺序和定位；损坏/加密/空白/低置信度样本产生明确状态。
- DOCX 不返回伪造页码；PDF/图片可跳页并高亮；越权预览失败。
- 相同输入和解析配置不重复解析；失败原因可用于后续重试。
- 金样测试覆盖段落、表格、OCR bbox、字符区间和空页。

### 完成条件

- Parser/OCR/预览、Migration、金样/集成/前端测试和质量门禁通过。
- Review、回归、文档、Git diff 检查完成。

### Git Snapshot

```text
feat(documents): add parsing OCR and evidence mapping
```

## Phase 8A：Versioned Risk Rules / 风险规则版本管理

### 目标

组织管理员可安全维护、复制、发布和停用风险规则版本，审核员只能读取已发布版本。

### 实现范围

- 做：规则集/草稿/发布/停用全流程；白名单规则 DSL；至少 11 类内置演示基线。
- 不做：执行千问分析、生成具体风险、任意 Python/SQL/表达式执行。

### 前置依赖

- Phase 3；P-04 已确认组织默认规则集选择规则；内置基线仅作为受控 seed/Migration 数据。

### 预计涉及模块

```text
backend/app/modules/risks/rules/
backend/migrations/versions/
backend/tests/{api,unit}/risk_rules/
frontend/src/features/admin/risk-rules/
```

### 后端任务

- 实现 Risk Rule Model/Schema/Service/API、草稿乐观锁和发布不可变约束。
- 实现关键词、正则、金额/日期阈值、字段存在性和逻辑组合的 Schema 校验器。
- 发布切换 current version、首次发布默认项/默认切换与审计同事务；默认唯一性由数据库约束保证，历史版本不可编辑/删除。

### 前端任务

- 规则集列表、版本历史、草稿表单、复制、发布和停用 UI。
- 白名单条件编辑/校验；审核员只读；冲突和已发布状态明确。

### API Contract

- 11.1-11.8，共 8 个接口。

### 数据库变更

- 新增 `risk_rule_bundles`、`risk_rule_bundle_versions`、`risk_rules`。
- 版本号/规则键唯一、发布不可变、current version 复合外键、每组织默认部分唯一索引、列表索引。

### 测试要求

```bash
python -m pytest backend/tests/integration/risks backend/tests/unit/risks
npm --prefix frontend run test -- risk-rules
python -m alembic upgrade head
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

### 验收标准

- 组织管理员完成 8 个接口；审核员仅看到已发布版本；viewer/跨组织访问失败。
- 发布后 PATCH 返回冲突；新草稿不改变历史发布版；任意代码型条件被 422 拒绝。
- 11 类基线可重复安装且不重复创建；首次发布自动设默认、显式切换、默认停用冲突、版本切换和审计原子提交。

### 完成条件

- API、UI、Migration、DSL/权限/不可变测试和质量门禁通过。
- P-04 契约默认选择规则已关闭；Review、回归和 Git diff 检查完成。

### Git Snapshot

```text
feat(risk-rules): add versioned rule management
```

## Phase 8B：Versioned Clause Templates / 标准条款模板版本管理

### 目标

组织管理员可维护五类合同标准条款模板并发布不可变版本，审核员可读取已发布基线。

### 实现范围

- 做：模板/版本/条款表单管理、复制、发布、停用、五类演示基线。
- 不做：Word/Excel 导入、条款比对执行或自动法律意见。

### 前置依赖

- Phase 3；P-05 已确认同合同类型/规范化业务场景的默认模板选择规则；单一工作流必须在 Phase 8A 全部完成后进入本 Phase。

### 预计涉及模块

```text
backend/app/modules/clauses/templates/
backend/migrations/versions/
backend/tests/{api,unit}/clause_templates/
frontend/src/features/admin/clause-templates/
```

### 后端任务

- 实现 Clause Template/Version/StandardClause Model、Schema、Service、API。
- 强制发布不可变、草稿 version 冲突、change_note、适用条件 Schema 和历史引用安全。
- 初始化五类合同演示模板，每类覆盖需求列出的常见条款。

### 前端任务

- 模板列表/版本/条款表单/复制/发布/停用 UI；合同类型和业务场景筛选。
- 展示草稿/发布/停用、校验、冲突、只读和空态。

### API Contract

- 12.1-12.8，共 8 个接口。

### 数据库变更

- 新增 `clause_templates`、`clause_template_versions`、`standard_clauses`。
- 版本号/条款键唯一、发布不可变、current version 复合外键和筛选索引。

### 测试要求

```bash
python -m pytest backend/tests/api/clause_templates backend/tests/unit/clause_templates
npm --prefix frontend run test -- clause-templates
python -m alembic upgrade head
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

### 验收标准

- 组织管理员完成 8 个接口；审核员只读发布版；viewer/跨组织访问失败。
- 发布版本不可编辑，复制/新草稿不改历史；change_note 和条款 Schema 强制校验。
- 五类基线可开箱使用且不被表述为具体企业法律意见。

### 完成条件

- API、UI、Migration、权限/不可变/Schema 测试和质量门禁通过。
- 默认模板规则已确认，Review、合并回归和 Git diff 检查完成。

### Git Snapshot

```text
feat(clauses): add versioned clause templates
```

## Phase 9A：Review Task and Async Orchestration / 审核任务与异步编排

### 目标

在没有真实 AI 能力的情况下，建立可验证的审核任务状态机和异步执行框架：

```text
Create Review -> Queue -> Worker -> Stage Transition -> Success/Failure -> Retry/Recovery
```

### 实现范围

- 做：`ReviewTask`、`ReviewStageRun`、审核任务创建/查询/重试、Celery 编排、Worker 基础结构、stage 状态机、lease、heartbeat、crash recovery、compensation、并发限制、幂等、重试边界和 Fake Stage Executor。
- 不做：Qwen 调用、`ModelGateway`、分类、字段抽取、风险分析、条款比对、通知、报告和真实业务结果。
- 9A 的任务 retry 上限固定为每个 `ReviewTask` 最多 3 次；租约超时的 stage 进入 `retryable`，补偿后由新 attempt 恢复。该边界不复用平台模型调用的 `max_retries`。

### 前置依赖

- Phase 7、8A、8B；并行分支必须先完成 Alembic merge revision、空 PostgreSQL 全量升级和相关测试。
- P-01、P-02、P-04、P-05、P-07 中影响任务创建/归档的部分必须在本 Phase 开始前关闭。

### 预计涉及模块

```text
backend/app/modules/reviews/{models,schemas,service,api}
backend/app/worker/{celery_app,review_tasks,compensation}
backend/migrations/versions/
backend/tests/{api,integration,unit}/reviews_async/
frontend/src/features/reviews/{create,status}
frontend/tests/reviews_async/
```

### 后端任务

- 新增 `review_tasks`、`review_stage_runs`；创建时锁定文件、文档、规则、模板、prompt 和模型配置快照，但不调用模型。
- 实现 10.1-10.3、状态条件更新、阶段 attempt、租约/心跳、失败公开错误、幂等和组织并发 3。
- 实现 Fake Stage Executor；测试中驱动成功、失败、重试、Worker 崩溃、Redis 丢消息和补偿恢复，不生成分类或字段结论。
- 在 ReviewTask 已存在后补充合同归档 guard：存在 active `pending|parsing|reviewing|pending_review` 任务时归档返回 409；增加事务、授权和并发保护。

### 前端任务

- 创建审核任务、版本选择、任务状态页、2 秒起始轮询/退避、页面隐藏降频、终态停止、失败状态和重试 UI。
- 仅展示任务与 stage 状态，不展示模型结果或风险结论。

### API Contract

- 10.1 创建审核任务。
- 10.2 获取审核任务。
- 10.3 重试失败审核。
- 合同归档 guard 复用 9.5，不新增浏览器 API；冲突语义必须覆盖 `ACTIVE_REVIEW_EXISTS`。

### 数据库变更

- 新增 `review_tasks`、`review_stage_runs`。
- 添加活动任务/阶段 attempt 唯一约束、租约和状态索引、组织复合外键、输入版本快照和幂等关联。
- 不创建 `model_calls`、分类、字段、风险或条款结果表。

### 测试要求

```bash
python -m pytest backend/tests/api/reviews_async backend/tests/integration/reviews_async backend/tests/unit/reviews_async
npm --prefix frontend run test -- reviews-async
python -m alembic downgrade -1
python -m alembic upgrade head
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

重点覆盖 state machine、Celery、retry、lease、heartbeat、concurrency、crash recovery、fake worker、幂等、合同归档 guard 和并发归档。

### 验收标准

- 创建返回 202/pending 并锁定输入版本；无文件、未发布版本、未确认告知、并发超限按契约失败。
- Fake Stage Executor 可验证 Queue、Worker、stage success/failure、retry、lease 超时和 compensation，不调用真实或 Fake Model Gateway。
- Redis 消息丢失、Worker 崩溃和重复投递不会产生重复活动任务或跳过阶段；失败有可读错误。
- 每个任务最多 3 次显式 retry；租约超时保留 `retryable` 阶段事实并创建新的 attempt，超过上限返回 `RETRY_LIMIT_EXCEEDED`。
- active ReviewTask 存在时归档合同返回 409；无 active 任务时合同自身归档行为保持 Phase 5 语义。
- 前端轮询、退避、失败、重试和终态处理可独立验证。

### 完成条件

- 3 个接口、Worker 框架、Fake Stage Executor、Migration、合同 guard、前端和异步恢复测试通过。
- lint/typecheck/build、独立 Review、Fix、Regression、文档和 Git diff 检查完成。

### Git Snapshot

```text
feat(reviews): add review task and async orchestration
```

## Phase 9B：Model Gateway / 外部模型访问边界

### 目标

建立可独立测试的外部模型访问边界，不实现正式分类或字段抽取业务。

### 实现范围

- 做：`ModelGateway` abstraction、Qwen adapter、Fake Model Gateway、请求/响应 Schema、timeout、429/5xx、invalid JSON、Schema validation、bounded retry、model fingerprint、prompt/model version、token/cost/latency 记录、安全日志和 Secret handling。
- 不做：正式合同分类、字段抽取、风险分析、条款比对或新的浏览器业务 API。

### 前置依赖

- Phase 9A 的 ReviewTask/StageRun；Phase 3 的平台模型配置；P-08、P-09 和 P-10 中影响模型调用安全边界的配置必须关闭或冻结为部署配置。

### 预计涉及模块

```text
backend/app/integrations/model/{gateway,qwen,fake,schemas}
backend/app/shared/model_telemetry.py
backend/migrations/versions/
backend/tests/{unit,contract,integration}/model_gateway/
```

### 后端任务

- 定义与供应商 SDK 无关的版本化请求/响应对象和四类能力方法边界。
- 统一超时、429/5xx 映射、一次修复重试与有限重试、指纹、provider request ID、token、费用、延迟和错误码记录。
- 仅从环境/部署 Secret 读取密钥；日志禁止合同正文、完整 prompt、完整响应、Cookie 和密钥。
- 为 9C 提供 Fake fixtures 和 deterministic error injection；普通 CI 不访问付费千问。

### 前端任务

- 无正式业务页面或浏览器 API；仅保留未来由 OpenAPI/共享类型使用的错误类型，不暴露供应商字段。

### API Contract

- 无新增浏览器 API；严格复用 `docs/api-contract.md` 的错误、状态码和异步边界。

### 数据库变更

- 新增 `model_calls` 及必要的 prompt/model version、request fingerprint、token/cost/latency、错误和 stage 关联字段。
- 不新增分类、字段、风险、条款或模型供应商管理接口；模型名/密钥仍由 Phase 3 配置边界控制。

### 测试要求

```bash
python -m pytest backend/tests/unit/model_gateway backend/tests/contract/model_gateway backend/tests/integration/model_gateway
python -m ruff check backend
python -m mypy backend/app
```

重点覆盖 model contract、timeout、429、5xx、invalid JSON、schema failure、bounded retry、safe logging、Secret handling、fingerprint、prompt/model version 和 cost/token recording。

### 验收标准

- Fake Gateway 可按固定 fixture 返回成功、超时、429、5xx、非法 JSON、Schema 不符和无证据响应。
- 错误映射、重试上限、请求指纹、模型/prompt 版本、token、费用、延迟均可断言。
- 日志和数据库记录不泄露密钥、合同全文、完整 prompt 或完整模型响应；真实千问不是 CI 前置条件。
- 没有新增浏览器业务接口，供应商协议仅存在于 integrations 边界。

### 完成条件

- Gateway、Qwen adapter、Fake、Migration、契约/安全测试和质量门禁通过。
- 独立 Review、回归、文档和 Git diff 检查完成。

### Git Snapshot

```text
feat(model): add provider-neutral model gateway
```

## Phase 9C：Classification and Extraction / 分类与字段抽取

### 目标

在 9A 异步框架和 9B 模型边界稳定后，连接文档证据、模型结果和审核持久化，完成合同分类与 7 个核心字段抽取。

### 实现范围

- 做：合同分类、7 个核心字段、Extraction Result、Evidence/SourceSpan 关联、结果持久化、模型结果校验、null/missing 语义、fingerprint/reuse 和结果展示。
- 不做：风险分析、条款比对、预警、人工修订、反馈、完成审核或报告。

### 前置依赖

- Phase 7、8A、8B、9A、9B；P-03、P-04、P-05 等影响结果枚举和版本选择的契约问题必须先关闭。

### 预计涉及模块

```text
backend/app/modules/{reviews/results,extraction}/
backend/migrations/versions/
backend/tests/{api,integration,contract,golden}/classification_extraction/
frontend/src/features/reviews/results/
```

### 后端任务

- 新增 `contract_classifications`、`extracted_fields` 及各结果的证据关联；复用 Phase 7 SourceSpan。
- 通过 9B Fake/真实 adapter 执行分类和结构化抽取，严格 Schema、未知字段、证据和版本校验。
- 缺失字段保存 JSON `null` 和明确状态；相同输入/版本复用成功结果，变更输入产生新指纹。
- 实现 10.5 结果读取和筛选；任务仍由 9A 编排，不在本阶段引入风险/条款阶段。

### 前端任务

- 结果展示页的分类、字段、置信度、证据跳转、null/missing/needs_confirmation 状态。
- 不提供 Phase 12 的编辑入口；处理结果未就绪、失败、无权限和空结果。

### API Contract

- 10.5 获取审核结果。
- 10.5 的初始读取边界在本阶段建立；Phase 10 通过同一 DTO/路由补充风险和条款字段，不重复定义结果 API。
- 不新增 Model Gateway 浏览器 API；结果状态严格使用 API Contract 的 `detected|not_found|needs_confirmation|confirmed|corrected`。

### 数据库变更

- 新增 `contract_classifications`、`extracted_fields` 及多证据关联表。
- `(review_task_id, field_key)` 唯一、结果 version、证据完整性、组织复合外键、指纹和筛选索引。

### 测试要求

```bash
python -m pytest backend/tests/api/classification_extraction backend/tests/integration/classification_extraction backend/tests/contract/classification_extraction backend/tests/golden/classification_extraction
npm --prefix frontend run test -- classification-extraction
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

重点覆盖 classification、extraction、evidence、persistence、null/missing、fingerprint/reuse 和 Fake Model Gateway end-to-end。

### 验收标准

- Fake 模型可完成分类和 7 个字段，缺失值为 null 且状态符合已修订契约；每个可确认结论具备合法证据。
- 非法 JSON、Schema 错误、无证据和低置信度结果不会生成伪造确认结论，并按任务阶段写入安全错误/人工状态。
- 相同输入、文档、prompt、模型版本复用成功结果；输入变化产生新的结果指纹。
- 10.5 返回的结果、证据、状态和筛选符合 API Contract；前端可跳转 PDF/图片/DOCX 定位。

### 完成条件

- 分类/抽取、结果 API、Migration、Fake E2E、金样、前端和质量门禁通过。
- 独立 Review、回归、文档和 Git diff 检查完成。

### Git Snapshot

```text
feat(extraction): add classification and structured extraction
```

## Phase 10：Risk Analysis, Clause Comparison and Result Aggregation / 风险与条款结果

### 目标

审核任务可产生可解释的规则/模型风险、标准条款比对和统一结果视图，所有结论可追踪版本和原文证据。

### 实现范围

- 做：确定性规则执行、千问语义风险/条款比对、去重、证据验证、四类比对状态、结果聚合和结果页。
- 不做：人工修订、预警处置、报告生成或自动训练。

### 前置依赖

- Phase 9A、9B、9C；Phase 8A/8B 已发布基线；P-03 已关闭，结果状态统一为 `detected` 及其余公共状态。

### 预计涉及模块

```text
backend/app/modules/{risks,clauses,reviews/results}/
backend/migrations/versions/
backend/tests/{unit,integration,contract}/review_results/
frontend/src/features/reviews/results/
```

### 后端任务

- 新增 RiskFinding、ClauseComparison 和多证据关联；执行白名单规则与 ModelGateway 风险/比对方法。
- 无证据风险不可确认；缺失条款可无定位；uncertain 保持人工复核。
- 使用任务锁定版本和稳定指纹去重；聚合分类、字段、风险、比对和 summary。

### 前端任务

- 结果页展示基本信息、分类、字段、风险统计/筛选、条款偏差/缺失、证据跳转和各种空/失败状态。
- 不提供尚未进入 Phase 12 的编辑入口。

### API Contract

- 不新增浏览器接口；10.5 的风险/条款结果字段在此阶段接入已由 Phase 9C 建立的结果读取边界。
- 结果状态与公共 `result_status` 已一致；不得重复定义 10.5 路由或另建结果 DTO。

### 数据库变更

- 新增 `risk_findings`、`clause_comparisons` 和对应多证据关联表。
- 风险指纹唯一、组织复合外键、状态/等级/任务筛选索引和证据完整性约束。

### 测试要求

```bash
python -m pytest backend/tests/unit/risk_engine backend/tests/integration/review_results backend/tests/contract/model
npm --prefix frontend run test -- review-results
python -m alembic upgrade head
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

### 验收标准

- 11 类以上风险正负例、关键词/阈值/缺失/跨句样本得到预期结果且无重复。
- 比对严格区分 matched/deviated/missing/uncertain；历史任务继续引用原规则/模板版本。
- 所有非缺失结论含合法 Source Locator；无证据模型结果不能进入确认态。
- 结果接口筛选和 summary 正确；结果页能跳转对应原文。

### 完成条件

- 结果接口、处理服务、Migration、模型契约/金样/前端测试和质量门禁通过。
- Review、回归、文档、Git diff 检查完成。

### Git Snapshot

```text
feat(review-results): add risk and clause analysis
```

## Phase 11：Warnings and In-App Notifications / 预警与站内通知

### 目标

高风险和配置的人工复核项可生成去重预警、站内通知和完整处置时间线，审核任务可进入 `pending_review`。

### 实现范围

- 做：预警触发/去重/列表/详情/事件状态机、分派、截止时间、站内通知/未读数、投递失败状态记录、前端预警中心。
- 不做：邮件/企业微信风险通知、履约日期提醒或人工结果修订。

### 前置依赖

- Phase 10；预警默认高风险、组织设置控制中风险/复核项；审核员名单来自 Phase 4。

### 预计涉及模块

```text
backend/app/modules/warnings/
backend/app/integrations/notifications/in_app.py
backend/migrations/versions/
backend/tests/{unit,api,integration}/warnings/
frontend/src/features/{warnings,notifications}/
```

### 后端任务

- 新增 Warning/WarningEvent/Notification；活动预警数据库部分唯一索引。
- 实现合法状态迁移、动作必填字段、同组织责任人校验、false_positive 联动。
- 预警创建与事件/通知事实原子提交；通知失败不回滚预警，保留安全的 retryable 状态。自动补偿和调度重试由 Phase 14B 负责。
- 完成预警生成阶段后把任务推进到 `pending_review`。

### 前端任务

- 预警列表/详情/筛选/统计、证据跳转、事件时间线、分派/说明/解决/关闭/重新打开表单。
- 通知列表、未读计数、标记已读和轮询；viewer 只读。

### API Contract

- 13.1-13.3 Warning，共 3 个接口。
- 14.1-14.3 Notification，共 3 个接口。

### 数据库变更

- 新增 `warnings`、`warning_events`、`notifications`。
- 活动 `dedupe_key` 部分唯一；事件追加写；状态/责任人/时间索引；通知 read/delivery 状态分离。

### 测试要求

```bash
python -m pytest backend/tests/unit/warning_state backend/tests/api/warnings backend/tests/integration/warnings
npm --prefix frontend run test -- warnings notifications
python -m alembic upgrade head
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

### 验收标准

- 高风险自动生成预警；配置开启时中风险/低置信度/uncertain 可触发；并发重复执行只生成一个活动预警。
- confirm/false_positive/ignore/assign/note/resolve/close/reopen 严格遵守状态机；关闭有结论或修订引用。
- viewer 仅查看授权合同预警且不能写；平台支持授权只读 JSON。
- 站内通知失败不回滚预警，失败状态和重试所需信息被可靠保存；未读数和重复 read 幂等。自动补偿不在本 Phase 验收。
- 任务只在机器结果和预警阶段成功后进入 pending_review。

### 完成条件

- 6 个接口、预警 Worker、UI、Migration、状态机/并发/权限/通知失败记录测试和质量门禁通过。
- Review、回归、文档和 Git diff 检查完成。

### Git Snapshot

```text
feat(warnings): add warning and notification workflow
```

## Phase 12：Human Review, Feedback and Completion / 人工复核与反馈

### 目标

审核员可乐观锁修订机器结果、提交反馈并确认审核完成；原始值、当前值、修订、预警和审计均可追溯。

### 实现范围

- 做：分类/字段/风险/条款修订、不可变修订记录、反馈与统计、完成审核命令、结果页编辑 UI。
- 不做：直接改风险严重度、覆盖模型原值、自动训练或报告排版。

### 前置依赖

- Phase 11；`detected` 状态已确认；完成命令的“必须人工项”判定规则可由契约测试定义。

### 预计涉及模块

```text
backend/app/modules/{reviews/revisions,feedback}/
backend/migrations/versions/
backend/tests/{api,integration}/human_review/
frontend/src/features/reviews/{edit,feedback,complete}/
```

### 后端任务

- 新增 ResultRevision/Feedback；每次修改同事务保存 before/after、actor、reason、version 和审计。
- 实现四类修订 Schema/证据规则、反馈 subject 组织一致性和聚合统计。
- 完成前拒绝无证据确认风险和未处理强制人工项；成功记录完成者/时间。

### 前端任务

- 在结果页增加分类、字段、风险、条款编辑和反馈表单；显示 model/current 值和修订历史。
- 处理 409 冲突并刷新资源，不覆盖他人修改；完成审核前展示阻塞项。

### API Contract

- 10.4、10.6-10.9，共 5 个 Review/Result 接口。
- 16.1-16.2，共 2 个 Feedback 接口。

### 数据库变更

- 新增 `result_revisions`、`feedback`；结果资源补齐 version/edited 字段。
- 修订/反馈追加写、subject 查询索引、组织一致性服务校验和统计索引。

### 测试要求

```bash
python -m pytest backend/tests/api/human_review backend/tests/integration/human_review
npm --prefix frontend run test -- review-edit feedback
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

### 验收标准

- 四类资源正确 version 修改返回 200 并递增；旧 version 返回 409；模型原值保持不变。
- 风险 confirmed 必须有证据；严重度和来源不能被任意请求改写；uncertain 不被静默通过。
- 反馈 subject 与任务/组织不一致被拒绝；聚合按契约过滤。
- pending_review 只有在强制项处理后可完成；相关报告前数据、预警时间线和审计可追溯修订。

### 完成条件

- 7 个接口、UI、Migration、并发/证据/权限/聚合测试和质量门禁通过。
- Review、回归、文档、Git diff 检查完成。

### Git Snapshot

```text
feat(human-review): add revisions feedback and completion
```

## Phase 13：Immutable HTML and PDF Reports / HTML 与 PDF 报告

### 目标

待复核或已完成审核可生成同源不可变 HTML/PDF 报告，授权用户可安全预览/下载，失败可恢复且不损坏审核数据。

### 实现范围

- 做：snapshot_json、版本化 Jinja2、固定 Chromium PDF、异步生成、状态/失败恢复、报告 UI 和下载。
- 不做：修改历史报告、把模型 HTML 当可信内容或平台支持授权下载。

### 前置依赖

- Phase 12；确认报告完整状态机、失败后重新 POST/重试语义和过期规则，并先更新 API 契约。

### 预计涉及模块

```text
backend/app/modules/reports/
backend/app/worker/reports.py
backend/migrations/versions/
backend/tests/{api,integration,snapshot}/reports/
frontend/src/features/reports/
```

### 后端任务

- 新增 Report；事务创建完整快照，异步渲染 HTML/PDF，新生成记录不覆盖旧版本。
- 默认转义所有用户/模型文本，设置 CSP、Content-Type/Disposition 和每次下载授权。
- 失败只更新报告状态/error，审核结果保持；实现确认后的可恢复语义。

### 前端任务

- 格式选择、生成状态轮询、失败后用新幂等键再次 POST、HTML inline 预览、PDF/HTML 下载；不实现报告历史列表（当前契约没有历史列表 API）。
- 展示免责声明、版本、人工修订、失败/过期/无权限状态。

### API Contract

- 15.1-15.3，共 3 个接口。

### 数据库变更

- 新增 `reports`，关联不可变 `snapshot_json` 和 `file_object_id`。
- 同任务/格式生成中唯一约束、状态/时间索引、组织复合外键和保留期字段。

### 测试要求

```bash
python -m pytest backend/tests/api/reports backend/tests/integration/reports backend/tests/snapshot/reports
npm --prefix frontend run test -- reports
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

### 验收标准

- pending_review/completed 可返回 202；不合法状态、重复生成和并发超限按契约失败。
- HTML/PDF 来自同一快照，包含编号、文件、版本、结果、证据、人工记录和免责声明。
- 修改审核结果后旧报告不变，新报告生成新记录；恶意文本被转义且 CSP 生效。
- viewer 只下载授权合同报告；平台支持授权不能下载；生成失败不丢审核结果并可恢复。

### 完成条件

- 3 个接口、两种格式、Worker、UI、Migration、安全/快照/权限测试和质量门禁通过。
- Review、回归、契约/部署文档和 Git diff 检查完成。

### Git Snapshot

```text
feat(reports): add immutable HTML and PDF reports
```

## Phase 14A：Audit and Observability / 审计与可观测性

### 目标

管理员可查询组织/平台审计和运营指标，系统可观测任务、预警、模型成本与失败；本阶段不执行物理数据清理。

### 实现范围

- 做：organization audit query、platform audit query、review/warning metrics、model cost metrics、Prometheus internal metrics、admin operations UI、audit coverage review 和 sensitive log filtering。
- 不做：数据库/文件物理清理、保留期调度、通知补偿、对象存储迁移、批量审核、Grafana 强制部署或未定义的审计导出接口。

### 前置依赖

- Phase 13；此前各 Phase 已写关键审计和模型/任务/预警事实；审计 365 天、合同/报告 180 天、日志 30/7 天规则已冻结为查询与指标口径。

### 预计涉及模块

```text
backend/app/modules/{audit,operations}/
backend/app/observability/{metrics,log_filters}/
backend/tests/{api,integration}/operations/
frontend/src/features/admin/{audit,metrics}/
deploy/compose/observability/
```

### 后端任务

- 实现组织/平台审计过滤和权限；审计只读、敏感摘要过滤和覆盖率检查。
- 实现 review/warning 聚合指标、模型 token/cost/latency 指标和内部 `/metrics`，不对公网公开。
- 核对登录、上传/下载、审核、修订、预警、规则/模板、报告和归档操作的审计覆盖；不执行删除。

### 前端任务

- 组织/平台审计列表和筛选；运营指标页；无权限/未启用/空数据状态。
- 不显示合同正文、秘密、完整 prompt 或供应商原始响应。

### API Contract

- 17.1-17.4，共 4 个接口。
- `/metrics` 是内部部署端点，不加入公网业务 API。

### 数据库变更

- 按实测查询补充审计、任务、模型调用、预警和反馈索引；不新增清理删除逻辑。
- 不物理删除不可变历史事实；任何索引/分区 Migration 仍需 upgrade/downgrade 和恢复验证。

### 测试要求

```bash
python -m pytest backend/tests/api/operations backend/tests/integration/operations backend/tests/unit/observability
npm --prefix frontend run test -- audit metrics
python -m alembic upgrade head
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

重点覆盖 organization/platform audit query、review/warning/model metrics、Prometheus 暴露边界、audit coverage 和 sensitive log filtering。

### 验收标准

- 组织管理员只查本组织审计；平台管理员查全局；其他角色被拒绝。
- review/warning/model cost 指标与固定数据集人工计算一致；未启用返回 501。
- `/metrics` 不经公网代理暴露且不含秘密/正文；关键请求、任务、OCR、模型、预警和报告指标存在。
- 本阶段不删除任何数据库行或文件，所有审计查询和指标均可回归验证。

### 完成条件

- 4 个接口、管理 UI、指标/日志过滤/权限测试和质量门禁通过。
- 独立 Review、回归、运维文档和 Git diff 检查完成。

### Git Snapshot

```text
feat(operations): add audit and observability
```

## Phase 14B：Retention and Compensation / 保留清理与补偿

### 目标

在独立 Review 和失败注入保护下，安全执行保留期清理、通知补偿以及数据库/文件一致性恢复；不得误删仍被不可变历史事实引用的数据。

### 实现范围

- 做：retention policy、cleanup scheduler、database cleanup、file cleanup、DB/file consistency、notification compensation、cleanup retry、cleanup audit、recovery 和 retention safety tests。
- 不做：新的业务 API、批量审核、未定义的审计导出、对象存储迁移或改变不可变历史事实语义。

### 前置依赖

- Phase 14A；Phase 11 已保存通知失败和 retryable 状态；保留期配置和 P-11 数据模型缺口已在本阶段前关闭或形成明确 Migration。

### 预计涉及模块

```text
backend/app/worker/{retention,compensation}.py
backend/app/modules/{retention,notifications/compensation}/
backend/migrations/versions/
backend/tests/{integration,security,recovery}/retention/
deploy/compose/scheduler/
```

### 后端任务

- 定时扫描超过组织保留期且无引用的合同、页面、报告、临时文件和可删除业务记录。
- 删除前检查不可变审核、报告、修订、预警事件、反馈和审计引用；数据库与 FileStore 操作具备补偿状态。
- 处理通知 retryable 记录的退避补偿、上限和最终失败；重复 scheduler 执行必须幂等。
- 清理、补偿、跳过和恢复均写入安全审计；失败注入后可从中间状态恢复。

### 前端任务

- 无新增业务页面；Phase 14A 的运营 UI 只读取清理/补偿安全统计（若契约已有字段），不增加删除 API。

### API Contract

- 无新增浏览器业务 API；复用既有通知、审计和运营事实，不暴露物理清理命令。

### 数据库变更

- 仅在需要时新增 cleanup/compensation lease、attempt、retryable 状态和引用检查索引。
- 不修改已稳定 revision；不得删除不可变历史事实。任何清理 Migration 必须可验证升级、回滚策略和恢复点。

### 测试要求

```bash
python -m pytest backend/tests/integration/retention backend/tests/security/retention backend/tests/recovery/retention
python -m pytest backend/tests/integration/notifications_compensation
python -m alembic upgrade head
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run build
```

重点覆盖 retention、deletion safety、reference protection、DB/file consistency、duplicate scheduler execution、notification compensation、failure injection、recovery 和误删保护。

### 验收标准

- 超过保留期且无历史引用的资源才会进入物理清理；仍被不可变历史事实引用的数据始终保留。
- 数据库删除和文件删除中途失败时不会产生不可追踪孤儿；补偿任务可恢复且重复执行幂等。
- 通知失败按退避和上限自动补偿，最终失败可审计且不回滚预警事实。
- 误删保护、两个并发 scheduler、断电/Worker 崩溃和恢复演练均通过。

### 完成条件

- 清理/补偿任务、失败注入、引用完整性、DB/file 一致性和恢复测试全部通过。
- 单独 Review、Fix、Regression、运维文档和 Git diff 检查完成。

### Git Snapshot

```text
feat(retention): add safe retention cleanup and compensation
```

## Phase 15：System Verification and Release Candidate / 全量验证与候选发布

### 目标

以固定评测集和真实依赖环境验证 75 个接口、核心用户路径、准确性、安全性、性能和恢复能力，产出可发布候选版本。

### 实现范围

- 做：全量回归、E2E、安全测试、文档金样、离线评测、性能基线、Migration 全链路、依赖/镜像扫描和缺陷修复。
- 不做：新增业务功能、为达指标临时改写评测集或在普通 CI 调用付费模型。

### 前置依赖

- Phase 14A、14B；授权脱敏/公开评测集；两组织四角色数据；所有 Pending Decisions 已关闭或明确不阻塞 Release。

### 预计涉及模块

```text
backend/tests/
frontend/tests/
tests/e2e/
evaluation/{datasets,scripts}/
docs/{test-plan,security,performance}/
```

### 后端任务

- 补齐跨模块集成、状态机、事务、并发、幂等、权限和失败注入覆盖。
- 完成独立评测 CLI，输出含数据集/模型/prompt/规则/模板版本的 JSON/CSV。
- 修复 Review 发现的问题，只改根因和相关测试，不做无关重构。

### 前端任务

- Playwright 覆盖登录、上传、审核、定位、预警、人工修订、报告和管理路径。
- 验证 desktop 响应、loading/empty/error/forbidden/conflict 状态、XSS 和下载授权。

### API Contract

- 全量 75 个接口做契约覆盖审计；生成 OpenAPI 与 `docs/api-contract.md` 对照。
- 发现差异必须先修契约并 Review，再修实现和测试。

### 数据库变更

- 原则上无；仅允许为缺陷修复新增向前 Migration。
- 从空库执行全部 upgrade，从上一候选版本验证向前升级；验证允许回滚的开发 Migration，不自动回滚生产数据。

### 测试要求

```bash
python -m pytest backend/tests
npm --prefix frontend run lint
npm --prefix frontend run typecheck
npm --prefix frontend run test
npm --prefix frontend run build
npm --prefix frontend run e2e
python evaluation/scripts/evaluate.py
docker compose -f deploy/compose/compose.yml build
```

另需执行：依赖/镜像扫描、跨组织/CSRF/文件伪装/路径穿越/XSS/越权下载、Worker 崩溃、Redis 丢消息、千问超时/429/5xx/非法 JSON、OCR/通知/报告失败、备份恢复预演和 10 页合同 3 分钟目标测试。

### 验收标准

- 五类合同和 other 样例、四类文件格式完成端到端闭环；所有 75 个接口有契约或权限测试。
- 分类准确率 >= 85%；五项必备字段 F1 >= 80%；预置风险 precision/recall 均 >= 75%，且评测数据与调优数据隔离。
- 10 页内文本合同在已记录环境下目标 <= 3 分钟；状态/预警前端感知 <= 5 秒。
- 四角色、两组织、viewer 部分授权、平台临时支持的越权测试全部正确拒绝。
- 所有失败注入可恢复或产生安全、可读终态；完整回归无阻塞缺陷。

### 完成条件

- 全量功能、测试、lint、typecheck、build、Migration、Review、Fix、Regression、文档和 Git diff 检查完成。
- Release blocker 为 0；其余问题有负责人、优先级和明确 Future Work 记录。

### Git Snapshot

```text
test(system): complete release candidate verification
```

## Phase 16：Docker Deployment and Release / 部署与正式发布

### 目标

在企业私有服务器使用单机 Docker Compose 可重复部署、升级、健康检查、备份和恢复，并形成正式 Release。

### 实现范围

- 做：生产镜像、反向代理/TLS 边界、Compose、持久卷、Secret 注入、备份恢复、升级/回滚 Runbook、SBOM 和冒烟。
- 不做：Kubernetes、微服务拆分、S3 迁移、SSO、外部风险通知或自动数据库向后回滚。

### 前置依赖

- Phase 15 候选版本通过；部署域名/TLS/Secret/SMTP/千问/备份位置和 RPO/RTO 由部署方提供。

### 预计涉及模块

```text
deploy/compose/
deploy/images/
deploy/scripts/
docs/{deployment,operations,backup-restore,release}.md
```

### 后端任务

- 固化 API/Worker/Scheduler 镜像、启动配置校验、健康检查、Migration 前向升级和优雅停止。
- 建立数据库备份、文件卷同恢复点说明、恢复演练和失败告警。

### 前端任务

- 生成不可变静态产物，由反向代理同域提供；API、下载、CSP 和路由回退正确。
- 不在构建产物中写入任何 Secret。

### API Contract

- 不新增业务接口；部署必须保持 `/api/v1`、Cookie/Origin/CSRF、health 和下载行为不变。

### 数据库变更

- 无新业务表；部署前备份并运行已 Review 的向前 Migration。
- 应用镜像回滚不自动执行数据库 downgrade；破坏性变更遵循 expand/migrate/contract。

### 测试要求

```bash
docker compose -f deploy/compose/compose.yml config
docker compose -f deploy/compose/compose.yml build
docker compose -f deploy/compose/compose.yml up -d
```

随后执行 live/ready、登录、上传、任务创建/Worker、预警、HTML/PDF 报告和授权下载冒烟；执行一次备份恢复演练和镜像/依赖扫描。

### 验收标准

- reverse-proxy、api、worker、scheduler、postgres、redis、clamav 和 file-volume 按架构启动，前端同域访问。
- ready 只受数据库/关键配置影响；千问瞬时故障进入任务错误而不使 API 失去就绪。
- Secret 不进入镜像、仓库、前端或日志；内部 metrics/ready 暴露范围符合部署规则。
- 从备份可恢复数据库和文件一致恢复点；升级/应用回滚 Runbook 经演练。

### 完成条件

- 镜像、Compose、冒烟、扫描、备份恢复、文档、Review、Regression 和 Git diff 检查全部完成。
- 发布版本号、变更说明和已知限制明确，正式 Release 可被重复部署。

### Git Snapshot

```text
chore(release): prepare production Docker release
```

## Testing Strategy

### Unit Tests

- Service、Utility、Schema Validation、状态机、权限策略、规则 DSL、指纹/游标、证据校验、错误映射。
- 外部模型、OCR、SMTP、ClamAV、文件存储使用可控 Fake；单元测试不依赖付费或不稳定网络。

### Integration Tests

- FastAPI + 真实 PostgreSQL/Redis；验证 API、认证、授权、复合外键、部分唯一索引、事务、幂等、并发、Worker 重试和 Migration。
- 每个涉及 Migration 的 Phase 执行 upgrade -> downgrade -> upgrade；不可逆生产 Migration 必须说明原因和恢复方案。

### Frontend Tests

- Vitest + Vue Testing Library 覆盖组件、表单、API interaction、权限、loading/empty/error/forbidden/conflict 和轮询终止。
- TypeScript 类型来自后端 OpenAPI 投影，但接口语义必须回查 `docs/api-contract.md`。

### Contract and Golden Tests

- 固定千问响应覆盖正常、超时、429/5xx、非法 JSON、Schema 不符、重复风险和无证据结果。
- 脱敏/生成 DOCX、文本 PDF、扫描 PDF、PNG/JPEG 覆盖结构、定位、OCR 低置信度、损坏/加密/MIME 伪装。
- 每个 API 的 Method、Path、Request、Response、Error、权限和状态码至少有一项自动化断言。

### E2E Tests

- Playwright 覆盖登录、合同创建、告知确认、上传、审核轮询、结果定位、预警闭环、人工修订、反馈、完成和报告下载。
- 覆盖平台管理员、组织管理员、审核员、viewer，以及两个组织和 viewer 部分合同授权。

### Security and Performance Tests

- 跨组织/ID 枚举、CSRF/Origin、文件伪装/路径穿越、XSS、越权下载、支持授权越权、日志/构建产物密钥泄漏。
- 在记录硬件、模型套餐、文件类型和页数的环境中验证 3 分钟/5 秒目标；不以未记录环境的单次结果作为结论。

### Evaluation Tests

- 评测 CLI 输出分类准确率、字段 F1、风险 precision/recall，记录数据集、prompt、model、rule 和 template 版本。
- 评测集和调优集隔离；只使用已授权脱敏合同、公开合同或生成样本。

### Regression Rules

- 每个 Phase 至少运行当前 Phase 全部测试和直接相关历史测试。
- 跨模块共享行为、权限、状态机、Migration 或 API Client 改动必须扩大回归范围。
- Phase 15 和 Release 前执行全量后端、前端、E2E、Migration、金样、评测、安全和镜像测试。

### Phase 9A Test Boundary

- 重点验证 ReviewTask/StageRun state machine、Celery queue/worker、retry、lease、heartbeat、concurrency、crash recovery、compensation、idempotency 和 Fake Stage Executor。
- 必须包含 Worker 重复领取、Redis 消息丢失、租约过期、失败阶段恢复、并发创建和 active ReviewTask 阻止合同归档的 integration/authorization/concurrency tests。

### Phase 9B Test Boundary

- 重点验证 model contract、request/response Schema、timeout、429、5xx、invalid JSON、Schema failure、bounded retry、safe logging、Secret handling、fingerprint、prompt/model version、token/cost/latency recording。
- 固定 Fake/fixture 是 CI 唯一模型依赖；真实付费模型只在受保护环境执行手工冒烟。

### Phase 9C Test Boundary

- 重点验证 classification、extraction、evidence、SourceSpan、result persistence、null/missing semantics、fingerprint/reuse 和 Fake Model Gateway end-to-end。
- 必须验证模型原始值与当前值边界、无证据结果、非法结构化输出和结果读取 API，不提前测试 Phase 12 的人工修订。

### Phase 14B Test Boundary

- 重点验证 retention、deletion safety、reference protection、DB/file consistency、duplicate scheduler execution、notification compensation、failure injection、recovery 和清理幂等。
- 必须证明仍被不可变历史事实引用的数据不会被删除，并覆盖数据库删除成功/文件删除失败及反向失败的补偿路径。

## Review Strategy

每个重要 Phase 由未主导该实现的人或独立 Codex Review。Review 先列阻塞问题，再列建议；至少检查：

- 功能正确性和需求覆盖；API Contract 的字段、错误、权限、状态码一致性。
- 组织隔离、RBAC、viewer 授权、平台临时支持、CSRF、Secret 和日志数据安全。
- 状态迁移、幂等、乐观锁、并发、事务、Rollback、Worker 重试和补偿。
- Migration 约束/索引/外键、历史版本不可变、数据保留和文件/数据库一致性。
- 前后端类型和 UI 状态一致；可访问性、错误/loading/empty/conflict 状态完整。
- 测试是否真正验证验收标准，是否遗漏失败/越权路径。
- 无关修改、重复代码、未请求抽象、依赖升级和大范围格式化。

发现问题后必须执行：

```text
Review -> Fix -> Regression -> Re-review (阻塞项) -> Git Snapshot
```

未关闭阻塞 Review finding 不得进入下一 Phase。

## API Contract Strategy

`docs/api-contract.md` 是唯一规范来源。进入任何涉及 API 的 Phase 前必须逐项确认 Request、Response、Error、Authentication、Authorization、状态码、幂等和状态机。

修改流程固定为：

```text
Update docs/api-contract.md
-> Review contract
-> Update backend Schema/Service/API
-> Regenerate/check OpenAPI and frontend types
-> Update frontend Client/UI
-> Update tests
-> Regression
```

禁止后端或前端先实现未定义字段；禁止以生成 OpenAPI 覆盖尚未 Review 的 Markdown 契约。CI 应保存 OpenAPI 快照或执行差异检查，确保可执行 Schema 不偏离契约。

## Database Migration Strategy

- 所有环境统一 PostgreSQL；ORM Model 和 Alembic Migration 同 Phase 提交。
- 使用复合租户外键、唯一约束、部分唯一索引和 CHECK 约束保护数据完整性，不能只靠 Service 先查后写。
- Migration 只向前追加，不删除历史，不修改已稳定发布的 Migration；禁止手工修改生产数据库。
- 每个 Migration 在真实 PostgreSQL 验证 upgrade/downgrade/upgrade、约束和事务；生产破坏性变更采用 expand -> data migrate -> contract。
- 业务写入和审计同事务；阶段性 Worker 结果原子提交；外部文件操作必须有补偿和可恢复状态。
- 回滚应用镜像不自动回滚数据库。备份与文件快照必须属于同一恢复点并定期演练。

### Parallel Migration Merge: Phase 8A / Phase 8B

```text
Phase 3 baseline
     |
     +---- Phase 8A Migration Head
     |
     +---- Phase 8B Migration Head
                |
                v
       Alembic Merge Revision
                |
                v
          Unified Head
```

1. 两个并行 Phase 产生多个 Alembic head 时，优先创建显式 Alembic merge revision。
2. 不为了得到线性 Migration 历史随意修改已经 Review 或形成 Git Snapshot 的 Migration；不删除历史 Migration，不重写稳定 revision ID。
3. merge revision 只合并依赖关系，不包含无关 schema change。
4. 合并后从空 PostgreSQL 数据库执行 `upgrade head`、schema verification 和相关 integration tests。
5. 必须验证从 Phase 3 baseline 分别经过 8A、8B branch 后的最终结构一致，再验证统一 head。
6. 如果 Migration 尚未形成稳定 Git Snapshot，可在明确 Review 后重新生成，但必须重新运行完整 Migration 测试。

功能分支和 Migration 图可以分开处理：Phase 4-7 的功能开发可以与 8A/8B 并行，但如果其 Migration 也从 Phase 3 产生独立 head，则先形成 `Phase 8AB Merge`（父 revision 为 8A、8B），再形成不含 schema change 的 `Unified Head Merge`（父 revision 为 `Phase 8AB Merge` 和 Phase 7 head）。两个 merge revision 都必须单独 Review；不得以重写 revision 的方式消除第三个 head。

## Git Strategy

```text
Stable Baseline
-> Phase Development
-> Test
-> Review
-> Fix
-> Regression
-> Git Diff Review
-> Git Commit
-> Next Phase
```

- 每个 Phase 尽量形成一个独立 Commit；8A/8B 并行时各自一个 Commit，Alembic merge revision 另做一个集成 Snapshot，随后才进入 9A。
- Commit 只包含当前 Phase；契约修订可与对应 Phase 同 Commit，但必须在代码变更之前完成 Review。
- 禁止 `reset --hard`、force push、覆盖用户已有修改、删除未知文件、重写已发布 Migration 或提交 Secret。
- 当前计划只建议 Commit message，不实际执行 Commit。

## Scope Control

每个 Phase 只实现当前验收所需内容。以下行为禁止：顺便重构整个系统、升级无关依赖、改变架构、实现未来 Phase、添加推测性抽象、批量格式化无关文件。

新发现但不阻塞当前 Phase 的问题记录到本文件的 Known Issues / Future Work 或独立 issue。只有安全、数据损坏、契约阻塞或当前测试无法定义的问题可以扩大当前 Phase 范围，并需先说明原因。

## Definition of Done

一个 Phase 只有在所有适用条件满足后才完成：

- 当前需求和验收标准完成，明确的“不做”项未被偷偷引入。
- API Contract 已先行 Review，后端、OpenAPI、前端类型和 UI 一致。
- 代码、错误处理、权限、审计和必要日志完成。
- 单元、集成、前端及适用 E2E/金样/安全测试通过。
- lint、typecheck、build 通过。
- ORM 与 Migration 同步，upgrade/downgrade/约束验证通过。
- 独立 Review 完成；阻塞项修复并完成相关 Regression。
- 文档、环境模板、运行/恢复说明按需同步。
- 适用前端页面已按 `docs/ui/frontend-prd.md` 的 Page ID、API 映射和状态要求实现，并在 1440px/1280px 下完成原型对照；组件测试和适用 Playwright 已通过。
- 无当前 Phase 引入的已知阻塞错误；Git diff 已检查且无无关修改。
- 已准备独立 Git Snapshot；用户明确要求前不执行 Commit。
- `docs/phase-status.md` 已记录本 Phase 的完成边界、实际测试结果、Review、回归、Migration、API/UI 状态、Known Issues、Git Snapshot 和下一步。

## Risks and Technical Debt

| 风险 | 依据 | 控制措施 |
| --- | --- | --- |
| 外部模型不稳定/输出漂移 | 千问存在超时、429/5xx、非法 JSON 和模型版本变化 | Gateway、Schema 二次校验、版本快照、有限重试、Fake 契约测试、禁止伪造结论 |
| OCR CPU 性能和准确率 | 扫描合同、低配置单机、0.80 阈值 | 逐页状态、低置信度人工提示、金样/性能基线、Worker 隔离 |
| 合同敏感数据外发 | 合同正文发送千问商用 API | 上传前告知确认、最小日志、Secret 注入、授权数据集和调用审计 |
| 多租户越权 | 所有业务数据按组织隔离且 viewer 是细粒度授权 | 显式 tenant context、复合外键、后端 RBAC、两组织越权自动化测试 |
| 支持授权被滥用 | 平台管理员可临时查看组织 JSON | 最长 4 小时、组织管理员主动授权、禁止写/下载、逐次审计 |
| 状态机/并发竞争 | Worker 重试、人工编辑、预警去重和发布切换均可并发 | 条件更新、version、部分唯一索引、事务、租约和并发测试 |
| 数据库迁移/文件不一致 | 数据库与本地卷共同构成业务事实 | 向前 Migration、补偿状态、同恢复点备份、恢复演练 |
| 前后端契约漂移 | Markdown 契约与生成 OpenAPI 双重表现 | 契约先行、OpenAPI 投影检查、生成类型和契约测试 |
| 报告 XSS/内容漂移 | 模型/用户文本进入 HTML/PDF | 不可变快照、默认转义、CSP、同源模板和恶意样本测试 |
| 指标无法达标 | 准确率/F1/precision/recall 依赖授权样本与模型 | 独立版本化评测集、调优集隔离、RC 前硬门禁 |
| 单机资源瓶颈 | PostgreSQL、Redis、ClamAV、OCR、Chromium 共机 | 队列并发限制、磁盘/队列指标、实测后优化，不提前拆微服务 |
| SMTP/ClamAV/Chromium 运行依赖 | 身份邮件、上传和 PDF 均依赖外部进程 | ready/错误边界、Fake 测试、Compose 健康检查和失败恢复 |

## Known Issues / Future Work

- 批量审核在需求/架构第三阶段出现，但没有 API 契约；补齐契约后另建 Phase。
- 履约到期/续期/付款节点提醒、邮件/企业微信风险通知、OIDC SSO、Word/Excel 模板导入、对象存储、知识图谱、多轮改约和本地模型均不在当前计划。
- 审核任务取消命令和独立归档/恢复命令仅在架构文字出现，契约未定义，不实现。
- 审计导出、手工通知重试、报告专用 retry 接口未在契约定义；当前只实现查询/自动重试/确认后的报告恢复语义。
- 只有在单机实测成为瓶颈后才考虑对象存储、Worker 分队列扩容、只读副本或服务拆分。

## 待确认事项

| ID | 问题 | 影响 Phase | 建议的最小决策 |
| --- | --- | --- | --- |
| P-01（已关闭） | 多组织用户如何选择当前组织？ | Phase 2，已决策 | 采用 API Contract 2.2.1：有组织路径时从资源建立 Tenant Context；无组织路径时使用 `X-Organization-ID`，服务端校验有效 membership；单组织可自动选择，多组织缺失 Header 返回 `409 ORGANIZATION_CONTEXT_REQUIRED`。 |
| P-02（已关闭） | 平台创建组织等没有组织上下文的写接口，`Idempotency-Key` 如何确定作用域？ | Phase 1/3，已决策 | 组织级使用 `organization:<organization_id>`；平台级使用 `platform:<authenticated_user_id>`；均由服务端可信上下文生成，唯一性为 `(scope, idempotency_key)` |
| P-03（已关闭） | `result_status` 缺少 `found`，但 10.5 示例和 10.7 请求使用 `found` | Phase 9C，已决策 | 保留公共 `detected`；10.5 示例和 10.7 请求统一使用 `detected`，不新增并列状态。 |
| P-04（已关闭） | 多个已发布规则集时，省略 `rule_bundle_version_id` 如何选默认？ | Phase 8A/9A，已决策 | 每组织一个默认规则集；首个成功发布自动成为默认；后续由组织管理员通过 11.4 `is_default: true` 显式切换；默认发布新版本自动跟随；当前默认先切换后停用；缺少默认返回 `409 DEFAULT_RISK_RULE_BUNDLE_NOT_CONFIGURED`。 |
| P-05（已关闭） | 同合同类型/业务场景存在多个模板时，省略 `clause_template_version_id` 如何选默认？ | Phase 8B/9A，已决策 | 每组织+合同类型+规范化场景一个默认模板；缺省场景为 `standard`；首个成功发布自动成为默认；后续由组织管理员通过 12.4 `is_default: true` 显式切换；默认发布新版本自动跟随；当前默认先切换后停用；缺少默认返回 `409 DEFAULT_CLAUSE_TEMPLATE_NOT_CONFIGURED`。 |
| P-06 | 报告完整状态枚举、失败后再次生成、`REPORT_EXPIRED` 的时间条件和“重新生成”是否创建新记录未定义 | Phase 13，已关闭（2026-08-21） | 采用 `generating|ready|failed|expired`；相同幂等键同 fingerprint 重放同一记录；同任务/格式已有 generating 时新键返回 `REPORT_ALREADY_GENERATING`；ready/failed/expired 使用新键创建新不可变记录；`now >= expires_at` 时 ready 转 expired，`expires_at = generated_at + retention_days`；无专用 retry API |
| P-07（9A 已关闭） | review `archived` 如何进入/恢复？合同归档是否级联；架构提到 cancel 但无 API | Phase 9A，已决策 | active `pending|parsing|reviewing|pending_review` 任务阻止合同归档并返回 `409 ACTIVE_REVIEW_EXISTS`；合同归档不级联任务状态；terminal/history 任务保持只读和可追溯；未有契约依据不实现 cancel、任务归档/恢复接口或新的状态迁移 |
| P-08（已关闭） | 密码最小长度/复杂度/历史限制，以及邀请和重置令牌 TTL 未定义 | Phase 2，已决策 | 采用 API Contract 3.1：密码 12-128 字符、不强制字符类别；密码重置 Token 30 分钟、邀请 Token 7 天；Token 至少 256 位随机值且数据库只保存哈希。历史密码限制首期不做。 |
| P-09（已关闭） | SMTP 发件人、公开前端基址、投递失败可观测性和重试上限未完整冻结 | Phase 2/4，已决策 | 采用 API Contract 3.5：配置由环境注入；缺配置时在账号查询前统一返回 `503 SMTP_NOT_CONFIGURED`；首期后台投递只尝试 1 次且自动重试上限为 0，失败写不含邮箱/Token/完整 URL 的安全结构化日志/指标。当前实现仍须补失败捕获和测试，P-09 关闭不等于 Phase 2 完成。 |
| P-10（已关闭） | 架构 `model_configurations`/prompt 版本按组织设计，但 API 已确认组织不能覆盖且无 prompt 管理接口 | Phase 3/9B，已决策 | 以 API 为准：平台/部署级模型与基线 prompt 版本，组织无覆盖；架构说明已同步 |
| P-11 | API 要求的 `support_access_grants`、邀请投递字段、通知 title/body、多个资源 version 等未完整出现在架构表 | Phase 1-14 | 批准按 API 最小补齐模型，并在每个首次 Migration 中 Review；Phase 11 补齐 Warning/WarningEvent/Notification；Phase 12 补齐结果 `edited_by/edited_at`、ReviewTask `completed_by/completed_at`、ResultRevision/Feedback 及其租户/版本约束；Phase 13 补齐 Report 生命周期时间、过期和错误字段，报告历史列表继续由 UI-P11 排除 |
| P-12 | 需求/架构提到批量审核，但 API 无入口、请求/响应/权限/幂等定义 | Future Work | 当前 Release 排除；产品需要时先新增 API Contract 和独立 Phase |
| P-13（已关闭） | `retention_days`、审计 365 天与历史事实不可删除的边界，以及清理是否物理删除数据库行未冻结 | Phase 14B entry review，已决策（2026-08-21） | `retention_days` 只控制 FileStore 内容；永久保留不可变审核/结果/报告快照/修订/预警事件/反馈/模型调用/审计和 FileObject 元数据，只清理经引用与活动状态检查通过的 blob/临时文件；Phase 14B 不物理删除历史数据库行。 |

### Decision Record: P-06 Report Lifecycle and Regeneration（2026-08-21）

- `reports.status` 只允许 `generating|ready|failed|expired`；创建后先为 `generating`，成功写入同一快照生成的文件后为 `ready`，渲染/Worker 失败为 `failed`，`now >= expires_at` 时由查询或下载事务投影为 `expired`。
- 同一组织、同一幂等键和同一 fingerprint 重放原 `report_id`，仍返回 `202`；同键不同请求返回 `409 IDEMPOTENCY_KEY_REUSED`。同任务同格式已有 `generating` 时，新幂等键返回 `409 REPORT_ALREADY_GENERATING`。
- `ready`、`failed` 或 `expired` 不阻止使用新幂等键创建新不可变报告；失败恢复不新增报告专用 retry API，调用方使用新的幂等键再次 POST；“重新生成”永远不修改旧记录。
- `expires_at = generated_at + retention_days`，其中 `retention_days` 来自创建时冻结的组织报告设置；报告历史列表不实现，因为当前 API Contract 没有列表接口（UI-P11）。

### Decision Record: P-03 Result Status Canonical Value（2026-08-20）

- **Status**：Closed。
- **Decision**：公共结果状态统一使用 `detected`；10.5 示例和 10.7 字段修订请求中的 `found` 改为 `detected`，不新增同义状态。
- **Semantics**：模型识别到非空结果使用 `detected`；缺失值保存 JSON `null`，状态使用 `not_found` 或 `needs_confirmation`；人工确认/修订继续使用 `confirmed`/`corrected`。
- **Contract update**：`docs/api-contract.md` 6.1、10.5 和 10.7 的语义已核对并同步；Phase 9C 以该状态集合实现。

### Decision Record: P-02 Idempotency Scope（2026-08-17）

- **Status**：Closed。该决策解除 Phase 1/3 的幂等作用域阻塞，规范来源为 API Contract 2.3。
- **Organization scope**：服务端在完成会话、membership、角色、Tenant Context 和资源归属校验后生成 `organization:<organization_id>`；客户端路径或请求字段不能直接成为可信 scope。
- **Platform scope**：没有 organization context 的平台写接口在有效会话和 Platform Admin 校验后生成 `platform:<authenticated_user_id>`；不同平台操作主体彼此隔离。
- **Uniqueness and conflict**：逻辑及数据库唯一性为 `(scope, idempotency_key)`。相同 fingerprint 重放已提交成功结果，不同 fingerprint 返回 `409 IDEMPOTENCY_KEY_REUSED`；错误详情不得泄露原请求或其他 scope 信息。
- **Fingerprint and transaction**：fingerprint 包含 canonical operation 和 Schema 规范化后的关键请求内容，只持久化摘要并排除 Cookie、Authorization、会话/CSRF、密码、令牌和 Secret。幂等记录、业务写入和对应审计同事务提交/回滚，并由数据库唯一约束处理并发。
- **Boundary with P-01**：本决策不选择多组织用户的当前组织交互方案。Phase 1 可以实现 scope 表示、约束和基于可信上下文的接口；Phase 2 仍须关闭 P-01 后才能把具体会话/Header 选择机制接入组织业务请求。

### Decision Record: P-01 Organization Context（2026-08-18）

- **Status**：Closed。规范来源为 API Contract 2.2.1。
- **Decision**：组织路径或已验证资源归属优先建立 Tenant Context；无组织路径的组织级接口使用 `X-Organization-ID`。服务端必须校验会话用户的有效 membership，客户端 Header 不构成授权依据。
- **Fallback**：用户只有一个有效组织时允许服务端自动选择；多个有效组织且缺少 Header 返回 `409 ORGANIZATION_CONTEXT_REQUIRED`。
- **Frontend boundary**：前端可以记住用户选择并发送 Header，但不能用 Header 改变资源归属或跳过后端校验。

### Decision Record: P-08 Authentication Policy（2026-08-18）

- **Status**：Closed。规范来源为 API Contract 3.1、认证 Schema 和密码策略常量。
- **Decision**：密码长度为 12-128 字符，不强制字符类别；密码重置 Token 有效期 30 分钟；邀请 Token 有效期 7 天；一次性 Token 使用至少 256 位随机值，数据库只保存哈希。
- **Not included**：首期不实现密码历史限制；密码策略和 TTL 必须有边界/过期测试，不能只依赖文档常量。

### Decision Record: P-09 SMTP Boundary（2026-08-18）

- **Status**：Closed。规范来源为 API Contract 3.5；决策采用独立 Review 建议的 Phase 2 最小可靠性边界。
- **Configuration**：`SMTP_HOST`、`SMTP_PORT`、`SMTP_FROM`、`FRONTEND_BASE_URL` 通过环境配置；普通自动化测试使用 Fake Mailer，不调用真实 SMTP。
- **Unavailable configuration**：缺少配置时必须在查询账号前统一返回 `503 SMTP_NOT_CONFIGURED`，避免通过错误响应推断账号存在性。
- **Delivery and retry**：首期使用后台 SMTP 投递，每个请求最多尝试 1 次，自动重试上限为 0；已返回的 `202` 不因后台失败改变。
- **Observability and safety**：投递失败必须捕获并写安全结构化日志/指标，只允许 `request_id`、错误类别和投递阶段；禁止记录邮箱、Token 或完整链接。当前代码尚未满足此项，属于 Phase 2 implementation blocker，不再属于 Pending Decision。
- **Future extension**：Phase 4 如增加持久化 delivery 状态/重试，必须先扩展契约、数据模型、幂等和失败恢复测试。

### Decision Record: P-10 Model Configuration Boundary（2026-08-18）

- **Status**：Closed。规范来源为 API Contract 8.8、8.9 和第 20 节。
- **Decision**：模型 provider、模型名和密钥均为平台/部署环境配置；Phase 3 仅持久化可由平台管理员更新的非秘密运行参数。组织不能通过任何 API、设置或数据模型覆盖模型配置。
- **Prompt boundary**：提示词仅允许平台基线版本；本 Phase 不增加 prompt 管理 API，也不在创建组织时复制组织级 prompt 版本。Phase 9B 读取冻结的平台基线并将其写入审核任务快照。
- **Safety**：模型密钥和 `secret_ref` 不写入普通配置表、响应、审计摘要或日志。环境配置缺失时按 API Contract 返回 `503 MODEL_ENVIRONMENT_NOT_CONFIGURED`。

### Decision Record: P-04 Default Risk Rule Bundle（2026-08-19）

- **Status**：Closed。规范来源为 API Contract 10.1、11.1-11.8；产品语义由用户于 2026-08-19 确认。
- **Decision**：每组织最多一个默认风险规则集；首个成功发布的有效规则集自动成为默认，后续发布不自动替换。发布默认规则集的新版本更新该集的 `current_published_version_id`。
- **Switching and safety**：组织管理员在 11.4 PATCH 提交 `is_default: true` 显式切换；当前默认不能直接取消或停用，必须先切换到另一个 active 且已有发布版本的规则集。数据库唯一约束、服务事务和审计共同保证并发安全。
- **Review fallback**：创建审核省略规则版本时使用默认规则集当前发布版本；没有可用默认返回 `409 DEFAULT_RISK_RULE_BUNDLE_NOT_CONFIGURED`。

### Decision Record: P-05 Default Clause Template（2026-08-19）

- **Status**：Closed。规范来源为 API Contract 10.1、12.1-12.8；产品语义由用户于 2026-08-19 确认。
- **Decision**：每组织、合同类型和规范化场景最多一个默认模板；缺省或空白场景规范为 `standard`，只做精确匹配。每个组合首个成功发布的有效模板自动成为默认，后续发布不自动替换。发布默认模板的新版本更新该模板的 `current_published_version_id`。
- **Switching and safety**：组织管理员在 12.4 PATCH 提交 `is_default: true` 显式切换；当前默认不能直接取消或停用，必须先切换到同组合另一个 active 且已有发布版本的模板。数据库唯一约束、场景规范化、服务事务和审计共同保证并发安全。
- **Review fallback**：创建审核省略模板版本时按合同类型和规范化场景使用默认模板当前发布版本；没有对应默认返回 `409 DEFAULT_CLAUSE_TEMPLATE_NOT_CONFIGURED`。

### Decision Record: P-07 Review Task and Contract Archive（2026-08-20）

- **Status**：Closed for Phase 9A。规范来源为 API Contract 9.5、10.1-10.3 及本 Phase 的 Contract Review。
- **Archive guard**：合同归档事务锁定合同后，检查同组织同合同的 active `ReviewTask`；`pending`、`parsing`、
  `reviewing`、`pending_review` 任一存在即返回 `409 ACTIVE_REVIEW_EXISTS`，不写入归档状态。
- **History boundary**：合同归档不级联改变 `ReviewTask` 或 `ReviewStageRun`。`completed`、`failed`、`archived` 任务及其输入快照保持原状态、只读和可追溯。
- **Command boundary**：API 没有定义 cancel、任务归档或恢复接口；Phase 9A 不实现这些命令，也不自行增加状态迁移。

### Decision Record: P-11 Phase 11 Warning and Notification Minimum Model（2026-08-20）

- **Status**：Closed for Phase 11 model review; later phases may add fields only through their own contract review.
- **Warning minimum**：`warnings` 保存组织、审核任务、合同、至少一个风险/条款/字段/分类关联、触发类型/时间、稳定去重键、优先级、状态、责任人、截止时间和解决/关闭事实；活动去重由数据库部分唯一索引保证。责任人通过组织复合关联和服务层 active reviewer 校验。
- **Event minimum**：`warning_events` 追加保存组织、预警、事件类型、from/to 状态、操作者、说明、受控 metadata 和时间；首个 created 事件保存触发条件与规则版本摘要，不保存合同正文或模型原始响应。
- **Notification minimum**：`notifications` 保存组织、当前用户、预警、`in_app` channel、API 所需 `title/body`、独立 `delivery_status`、attempts、next attempt、read_at 和安全 error_code。API 的 `read/unread` 由 `read_at` 投影，投递失败事实不改变预警事务。
- **Boundary**：Phase 11 不新增外部通知、自动补偿、手工重试接口、履约提醒、结果人工修订或新的资源 version；Phase 14B 只能在后续 contract/migration review 后使用已有 retry facts 实现补偿。

### Decision Record: P-13 Retention and Compensation Boundary（2026-08-21）

- **Status**：Closed and implemented in Phase 14B after user confirmation; Phase 14B completed implementation, verification and Git Snapshot on 2026-08-21。
- **P-11 review**：现有 `FileObject` 只有 `quarantine|stored|failed`，没有内容清理状态、持久化 cleanup lease/attempt/retry 或恢复事实；现有 `Notification` 有 `delivery_status/attempts/next_attempt_at/error_code`，但创建路径没有冻结 retryable、退避、上限和最终失败语义。两者不能在未更新模型/契约边界前直接编码。
- **Reference review**：除复合外键外，`audit_logs.resource_id`、`ResultRevision.subject_id`、`Feedback.subject_id`、`Warning.revision_id` 和报告 `snapshot_json` 是隐式历史引用；解析页图像、报告二进制和原合同通过 `FileObject` 关联。所有清理实现必须同时检查直接 FK、这些隐式引用、活动任务/报告/通知补偿和租约状态。
- **Failure boundary**：现有解析页图像和报告 worker 先写 FileStore、后提交数据库，进程在中间退出可能产生孤儿；Phase 14B 实现前必须补持久化 cleanup journal 或先持久化可恢复 FileObject 事实，并覆盖重复 scheduler、lease recovery、DB 状态提交失败和 FileStore 操作失败。
- **Retention interpretation**：需求/API 的 `retention_days` 与审计不可变语义存在张力；已确认采用保守边界：保留历史数据库事实和 FileObject 元数据，只清理通过引用保护的 FileStore 内容；审计 365 天解释为最低保留期，不授权删除审计事实。
- **Notification compensation**：只处理已有 `delivery_status=failed` 的投递事实；最多 3 次（含首次），第 2/3 次分别在前次失败后 1 分钟/5 分钟执行；达到上限后保持 `failed`、清空 `next_attempt_at` 并写最终失败审计；补偿不回滚 Warning，不提供手工重试 API。
- **P-12**：保持 `Future Work`，批量审核不进入 Phase 14B，也不阻塞本 entry review 之外的规范整理。

### Just-in-Time Closing Order

- Phase 1 前：关闭 P-02；P-11 只需确认当前 Phase 使用的最小数据字段，不要求一次性解决全部后续模型缺口。
- Phase 2 前：P-01、P-08、P-09 已关闭；Phase 2 仍须实现并测试这些决策，关闭 Pending Decision 不替代完成验收。
- Phase 3 前：P-10 已关闭；使用平台模型配置/架构同步边界，但不恢复组织级模型覆盖。
- Phase 8A/8B 与 9A 前：P-04、P-05 已关闭；9A 同时关闭 P-07。
- Phase 9B 前：冻结 P-09、P-10 对模型 Secret、prompt 和供应商配置的影响；Phase 9C 前关闭 P-03。
- Phase 13 前关闭 P-06；Phase 14B 前完成 P-11 涉及的清理引用字段 Review；P-12 保持 Future Work，不阻塞当前 Release。

## Plan Self-Check

1. FR-A/FR-D/FR-E/FR-R/FR-W/FR-C/FR-RP/FR-F/FR-O 和全部非功能目标均已映射到 Phase。
2. API 75 个接口按模块计数全部覆盖，没有未分配核心 API。
3. 批量审核等没有契约的能力已明确移至 Future Work，没有被静默遗漏或擅自实现。
4. Roadmap 无循环依赖；8A/8B 与 4-7 的并行边界、Alembic merge revision 和 Phase 9A 合并点明确。
5. 文件解析、规则、模板、异步审核、模型边界、分类抽取、风险、预警、人工复核、报告、审计、清理分别拆分，避免单一不可验收大 Phase。
6. 每个 Phase 都有目标、做/不做、依赖、模块、前后端任务、API、数据库、测试、验收、完成和 Git Snapshot。
7. 验收标准均可由指定单元/集成/前端/E2E/金样/评测测试验证。
8. 每个 Phase 都有独立 Git Snapshot 建议，且本轮不执行 Commit。
9. Phase 15 是正式 Release 前完整回归，Phase 16 才执行部署发布准备。
10. Phase 0 严格限于工程骨架、健康检查和基础工具，不包含登录、业务 CRUD、业务表或正式页面。
11. 9A 只包含异步任务框架，9B 只包含 Model Gateway，9C 才包含分类/抽取和结果持久化；三者无职责重复。
12. Phase 5 不依赖尚不存在的 ReviewTask；active ReviewTask 归档 guard、integration/authorization/concurrency tests 已移至 9A。
13. 14A 只做审计/指标/可观测性，14B 独立承担保留清理、通知补偿、失败注入和恢复；14A 不执行物理删除。
14. 8A/8B 多 Alembic head 通过 merge revision 汇合，不重写或删除已 Review 的 revision；合并后从空 PostgreSQL 验证 unified head。
15. JIT Pending Decision 规则已写明：Phase 1/2 阻塞项提前关闭，远期 Phase 决策不阻塞 Phase 0 启动。
