# Frontend Product Requirements Document

## 1. Document Purpose

本文档定义企业合同智能审核与风险预警系统的前端产品结构、页面清单、用户操作、页面状态和原型交付方式。它是后续 AI 页面原型、Figma Frame、交互设计、Vue 前端实现和 UI Review 的共同输入，不重新设计后端，也不替代已有 Source of Truth。

规范职责如下：

```text
docs/requirements.md       -> 整个系统做什么
docs/architecture.md       -> 系统如何实现
docs/api-contract.md       -> 前后端如何通信
docs/development-plan.md   -> 系统按照什么顺序开发
docs/phase-status.md       -> 系统实际完成到哪里
docs/ui/README.md          -> 前端实现如何读取和使用 UI 资产
docs/ui/frontend-prd.md    -> 前端有哪些页面、页面如何组织、用户如何操作
docs/ui/design-system.md   -> 前端使用什么稳定视觉语言
```

### 1.1 Conflict Priority

发生冲突时按以下优先级处理：

```text
Business Requirements
>
API Contract
>
Architecture
>
Development Plan / Current Phase
>
Frontend PRD
>
Visual Prototype
```

上述优先级用于业务语义、接口、权限和状态机。纯视觉、布局和交互呈现由 `docs/ui/design-system.md` 与 approved 原型约束；视觉原型不得改变更高层语义。发现冲突时必须先报告并判断是否阻塞当前 Phase，不得自行选择。

API Route 与 Vue Page URL 是不同边界：Method、`/api/v1` Path、参数和动作只以 `docs/api-contract.md` 为准；浏览器页面 URL 在本 PRD 中维护其到 API 资源/动作的显式映射，不得反向修改或发明 API 路径。

### 1.2 Scope and Non-Goals

本文档覆盖浏览器中的认证、平台管理、组织配置、合同、文件、文档预览、审核、结果、人工复核、预警、通知、报告、规则、模板、反馈、审计和运营页面。

本文档不增加自动签署、原合同改写、最终法律意见、印章鉴定、知识图谱、多轮改约、OIDC SSO、外部风险预警通知、履约提醒、批量审核、Word/Excel 模板导入、审计导出、手工通知重试或物理清理入口。健康检查和内部 `/metrics` 是部署接口，不设计为业务页面。

### 1.3 UI Requirement Language

- `Confirmed`：已有需求、架构或 API Contract 明确支持。
- `Frontend Page URL`：Vue Router 的浏览器导航地址，必须在本 PRD 中与 API Route 建立映射。
- `Recommended UI Decision`：不改变业务语义的推荐设计选择。
- `Pending UI Decision`：需要后续人工确认的纯 UI 决策或上游契约待决项。
- 所有写操作仍由后端执行认证、CSRF、角色、组织、资源范围、状态和版本校验；前端隐藏入口只改善体验，不是权限边界。

## 2. Product Overview

### 2.1 Product Statement

本产品是面向企业法务、风控和合同审核团队的桌面优先企业级 Web 应用。它把合同审核组织为“机器初审 + 人工复核 + 风险预警 + 不可变报告”的可追溯工作流，并让每条结果能够返回原文证据。

### 2.2 Frontend Outcomes

前端应使用户能够：

1. 按权限进入平台或组织工作区。
2. 按 `合同 -> 文件 -> 审核任务` 的顺序发起审核。
3. 在异步处理中理解真实任务状态、当前阶段、失败原因和可用恢复动作。
4. 在结果页比较机器原值与当前值，跳转原文证据，并完成人工复核。
5. 在预警中心按合法状态机分派、确认、忽略、解决、关闭或重新打开预警。
6. 生成并安全预览/下载使用不可变快照的 HTML/PDF 报告。
7. 让管理员在不改代码的前提下管理组织、成员、设置、规则、模板、审计和运营指标。

### 2.3 Frontend Acceptance Baseline

- 所有核心业务流程均有明确页面承载，且不改变 API Contract 的操作顺序。
- 主要页面覆盖 loading、empty、error、forbidden、conflict、disabled、processing 和 retry（适用时）。
- `viewer` 只看到显式授权合同及关联只读信息；平台管理员默认不进入组织业务数据。
- PDF/图片证据按页与坐标定位；DOCX 只按段落/表格/字符区间定位，不伪造页码。
- 审核任务和报告状态仅展示服务端事实；前端不得伪造进度、风险分数或 AI 结论。
- 1440px 为首要设计宽度，1280px 可完整操作；不要求独立移动端产品。

## 3. Users and Roles

### 3.1 Role Matrix

| Role | 身份与主要目标 | 可访问模块 | 关键操作 | 明确禁止 |
| --- | --- | --- | --- | --- |
| Platform Admin / 平台管理员 | 维护平台组织和非秘密模型运行参数，查询全局审计 | 平台组织、平台模型配置、平台审计；持有效支持授权时临时读取组织业务 JSON | 创建/更新组织，更新非秘密模型参数，查询全局审计 | 默认访问组织业务数据；创建合同或审核；修改组织业务；下载合同/报告；通过 UI 修改模型名、密钥或授予平台管理员角色 |
| Organization Admin / 组织管理员 | 管理本组织配置、人员、合同审核和运营闭环 | 本组织全部业务与管理模块 | 管理成员、设置、支持授权、合同、viewer 授权、审核、结果、预警、规则、模板、报告、反馈、审计、指标 | 跨组织访问；授予平台管理员；停用最后一个有效组织管理员；编辑已发布版本；修改模型密钥 |
| Reviewer / 审核员/法务 | 执行合同审核、人工复核和预警处置 | 本组织合同、文件、审核、结果、预警、通知、报告；已发布规则/模板只读 | 创建合同、上传、创建/重试审核、修订结果、反馈、完成审核、处置预警、生成/下载报告 | 管理组织/成员/设置/支持授权；编辑规则或模板；查看审计/运营管理；直接改风险严重度或来源 |
| Viewer / 业务查看者 | 查看被明确授权的合同、结果、预警和报告 | 显式授权合同及其文件、审核结果、预警、通知、报告 | 只读查看；下载被授权合同原文件和报告；标记自己的通知已读 | 创建/编辑/归档合同；上传；创建或重试审核；修订结果；反馈；处置预警；查看规则、模板、组织管理或审计 |

### 3.2 Permission Presentation Rules

- 导航、按钮、菜单和编辑控件根据 `GET /auth/session`、组织资料的 `permissions`、资源状态和返回数据呈现。
- 无权限入口通常隐藏；用户通过书签或状态变化进入不可访问页面时，展示 forbidden/not found 页面，不泄露资源是否存在。
- 只读用户仍能看到状态、证据和允许的下载入口，但所有写控件不渲染或明确只读。
- 平台临时支持访问必须显示“只读支持访问”上下文；所有写操作与文件/报告下载入口隐藏。后端仍必须拒绝越权请求。
- 同一账号可能同时具有平台管理员标记和组织成员关系；工作区选择遵循 API Contract 2.2.1，前端可记住选择并发送 `X-Organization-ID`，但不得将其视为可信授权依据。

## 4. Information Architecture

```text
Application
|
+-- Public Authentication
|   +-- AUTH-001 Login
|   +-- AUTH-002 Forgot Password
|   +-- AUTH-003 Reset Password
|   +-- AUTH-004 Accept Invitation
|
+-- LAYOUT-001 Authenticated Application Shell
    |
    +-- Platform Workspace (Platform Admin)
    |   +-- PLATFORM-001 Organization List
    |   +-- PLATFORM-002 Organization Detail
    |   +-- PLATFORM-003 Model Configuration
    |   +-- PLATFORM-004 Platform Audit Log
    |
    +-- Organization Workspace
        +-- Contracts
        |   +-- CONTRACT-001 Contract List
        |   +-- CONTRACT-002 Create Contract
        |   +-- CONTRACT-003 Contract Detail
        |   +-- CONTRACT-004 File Upload and Versions
        |   +-- CONTRACT-005 Document Preview
        |
        +-- Reviews
        |   +-- REVIEW-001 Create Review
        |   +-- REVIEW-002 Review Progress
        |   +-- REVIEW-003 Review Result and Human Review
        |   +-- REPORT-001 Report Status and Viewer
        |
        +-- Warnings
        |   +-- WARNING-001 Warning List
        |   +-- WARNING-002 Warning Detail
        |
        +-- Header Utilities
        |   +-- NOTIFY-001 Notification Center
        |
        +-- Knowledge Configuration
        |   +-- RULE-001 Risk Rule Bundle List
        |   +-- RULE-002 Risk Rule Bundle Detail
        |   +-- RULE-003 Risk Rule Draft Editor
        |   +-- CLAUSE-001 Clause Template List
        |   +-- CLAUSE-002 Clause Template Detail
        |   +-- CLAUSE-003 Clause Template Draft Editor
        |
        +-- Organization Administration (Org Admin)
            +-- ORG-001 Organization Settings
            +-- ORG-002 Member Management
            +-- ORG-003 Support Access Management
            +-- ADMIN-001 Organization Audit Log
            +-- ADMIN-002 Operations Metrics
            +-- ADMIN-003 Feedback Summary
```

`Dashboard` 当前没有专用 API 或已确认内容模型，因此不作为已确认页面。默认登录落点见 Pending UI Decisions。

## 5. Application Shell

### 5.1 Shell Structure

```text
Viewport
+-- Sidebar
|   +-- Product Identity
|   +-- Workspace/Organization Context
|   +-- Primary Navigation
|   +-- Administration Navigation (permission-based)
|   +-- Collapse Control
|
+-- Main Area
    +-- Top Header
    |   +-- Breadcrumb / Current Location
    |   +-- Notification Entry
    |   +-- User Menu
    +-- Global Feedback Region
    +-- Page Header
    +-- Main Content Area
```

### 5.2 Sidebar Navigation

| Navigation | Platform Admin workspace | Org Admin | Reviewer | Viewer |
| --- | --- | --- | --- | --- |
| Organizations | Visible/write | Hidden | Hidden | Hidden |
| Model Configuration | Visible/write non-secret fields | Hidden | Hidden | Hidden |
| Platform Audit | Visible/read | Hidden | Hidden | Hidden |
| Contracts | Hidden unless valid support context, then read-only JSON view only | Visible/write | Visible/write | Visible/authorized read-only |
| Warnings | Hidden unless valid support context, then read-only | Visible/write | Visible/write | Visible/authorized read-only |
| Risk Rules | Hidden | Visible/write | Visible/published read-only | Hidden |
| Clause Templates | Hidden | Visible/write | Visible/published read-only | Hidden |
| Organization Settings | Hidden | Visible/write | Hidden | Hidden |
| Members | Hidden | Visible/write | Hidden | Hidden |
| Support Access | Hidden | Visible/write | Hidden | Hidden |
| Organization Audit | Hidden | Visible/read | Hidden | Hidden |
| Operations Metrics | Hidden | Visible/read when enabled | Hidden | Hidden |
| Feedback Summary | Hidden | Visible/read | Hidden | Hidden |

Recommended UI Decision：将“规则”和“条款模板”归入“知识配置”，将组织设置、成员、支持授权、审计、指标和反馈统计归入“组织管理”，避免一级导航过长。

### 5.3 Top Header

- 显示当前页面位置和用户 `display_name`；用户菜单包含邮箱、当前角色语境和退出登录。
- 组织工作区显示当前组织名称；组织选择/切换控件必须遵循 API Contract 2.2.1，服务端负责 membership 和 Tenant Context 校验。
- 通知入口显示 `unread_count`，打开 `NOTIFY-001`；仅展示当前用户通知。
- 使用面包屑表达“模块 / 资源 / 子视图”，详情页和编辑页必须有返回入口。
- 不加入全局搜索、AI 助手、主题切换、语言切换或帮助中心等未定义功能。

### 5.4 Main Content and Page Header

- 主内容区用于数据密集型后台，不将每个 section 包装成浮动卡片。
- Page Header 包含页面标题、必要的资源状态、简短上下文和至多一个主操作；次要操作进入按钮组或 Dropdown。
- 列表筛选、批量操作和分页保持稳定位置。当前 API 没有批量业务操作，UI 不设计批量修改。
- 详情页优先使用 Descriptions、Tabs、Table、Timeline 和固定操作区表达层级。

### 5.5 Global Loading and Error Boundary

- 首次会话恢复使用应用级 loading，不短暂显示错误角色导航。
- 页面加载使用 Skeleton/Table skeleton；局部刷新保留已显示内容并标记 refreshing。
- 未捕获页面错误由 Error Boundary 展示安全文案、`request_id` 和重试/返回入口，不展示堆栈。
- `401` 清理本地会话状态并引导登录；`403/404` 不暴露跨组织资源；`409` 在原页面保留用户上下文并给出刷新动作。

## 6. Page Inventory

`Frontend Page URL` 是 Vue Router 的浏览器导航地址，不是 API Route。API Method/Path 由 6.1 节逐项映射到 `docs/api-contract.md`；`/api/v1` 前缀不得直接挂载为 Vue 页面。Dialog/Drawer 型设计面不声明独立 Page URL。

| ID | 页面/设计面 | Frontend Page URL | 用户角色 | 所属模块 | 重要度 | 对应 Phase |
| --- | --- | --- | --- | --- | --- | --- |
| LAYOUT-001 | Authenticated Application Shell | N/A | All authenticated | Layout | P0 | Phase 2-3 |
| AUTH-001 | Login / 登录 | `/login` | Public | Authentication | P0 | Phase 2 |
| AUTH-002 | Forgot Password / 忘记密码 | `/password-reset` | Public | Authentication | P1 | Phase 2 |
| AUTH-003 | Reset Password / 重置密码 | `/password-reset/confirm` | Public | Authentication | P1 | Phase 2 |
| AUTH-004 | Accept Invitation / 接受邀请 | `/invitations/accept` | Public | Authentication | P1 | Phase 2 |
| PLATFORM-001 | Organization List / 平台组织列表 | `/platform/organizations` | Platform Admin | Platform | P1 | Phase 3 |
| PLATFORM-002 | Organization Detail / 平台组织详情 | `/platform/organizations/:organizationId` | Platform Admin | Platform | P1 | Phase 3 |
| PLATFORM-003 | Model Configuration / 模型配置 | `/platform/model-configuration` | Platform Admin | Platform | P1 | Phase 3 |
| PLATFORM-004 | Platform Audit Log / 平台审计 | `/platform/audit-logs` | Platform Admin | Platform | P2 | Phase 14A |
| ORG-001 | Organization Settings / 组织设置 | `/organizations/:organizationId/settings` | Org Admin | Organization Admin | P1 | Phase 3 |
| ORG-002 | Member Management / 成员管理 | `/organizations/:organizationId/members` | Org Admin | Organization Admin | P1 | Phase 4 |
| ORG-003 | Support Access Management / 支持授权 | `/organizations/:organizationId/support-access-grants` | Org Admin | Organization Admin | P2 | Phase 4 |
| CONTRACT-001 | Contract List / 合同列表 | `/contracts` | Org Admin, Reviewer, Viewer | Contracts | P0 | Phase 5 |
| CONTRACT-002 | Create Contract / 创建合同 | `/contracts/new` | Org Admin, Reviewer | Contracts | P0 | Phase 5 |
| CONTRACT-003 | Contract Detail / 合同详情 | `/contracts/:contractId` | Org Admin, Reviewer, authorized Viewer | Contracts | P0 | Phase 5-6, 9A |
| CONTRACT-004 | File Upload and Versions / 文件上传与版本 | `/contracts/:contractId/files` | Org Admin, Reviewer; Viewer read-only versions | Contracts | P0 | Phase 6 |
| CONTRACT-005 | Document Preview / 文档预览 | `/documents/:documentVersionId` | Contract-visible users | Documents | P0 | Phase 7 |
| REVIEW-001 | Create Review / 创建审核 | `/contracts/:contractId/reviews/new` | Org Admin, Reviewer | Reviews | P0 | Phase 9A |
| REVIEW-002 | Review Progress / 审核进度 | `/reviews/:reviewTaskId` | Contract-visible users | Reviews | P0 | Phase 9A |
| REVIEW-003 | Review Result and Human Review / 审核结果与人工复核 | `/reviews/:reviewTaskId/results` | Contract-visible users; write for Org Admin/Reviewer | Reviews | P0 | Phase 9C-12 |
| WARNING-001 | Warning List / 预警中心 | `/warnings` | Org Admin, Reviewer, authorized Viewer | Warnings | P0 | Phase 11 |
| WARNING-002 | Warning Detail / 预警详情 | `/warnings/:warningId` | Contract-visible users; write for Org Admin/Reviewer | Warnings | P0 | Phase 11-12 |
| NOTIFY-001 | Notification Center / 通知中心 | N/A, recommended Drawer | Authenticated User | Notifications | P1 | Phase 11 |
| REPORT-001 | Report Status and Viewer / 报告状态与预览 | `/reports/:reportId` | Contract-visible users | Reports | P1 | Phase 13 |
| RULE-001 | Risk Rule Bundle List / 风险规则集 | `/risk-rule-bundles` | Org Admin; Reviewer read-only | Risk Rules | P1 | Phase 8A |
| RULE-002 | Risk Rule Bundle Detail / 规则集详情与版本 | `/risk-rule-bundles/:bundleId` | Org Admin; Reviewer published read-only | Risk Rules | P1 | Phase 8A |
| RULE-003 | Risk Rule Draft Editor / 规则草稿编辑 | `/risk-rule-bundle-versions/:versionId` | Org Admin | Risk Rules | P1 | Phase 8A |
| CLAUSE-001 | Clause Template List / 条款模板列表 | `/clause-templates` | Org Admin; Reviewer read-only | Clause Templates | P1 | Phase 8B |
| CLAUSE-002 | Clause Template Detail / 模板详情与版本 | `/clause-templates/:templateId` | Org Admin; Reviewer published read-only | Clause Templates | P1 | Phase 8B |
| CLAUSE-003 | Clause Template Draft Editor / 模板草稿编辑 | `/clause-templates/:templateId/versions/:versionId` | Org Admin | Clause Templates | P1 | Phase 8B |
| ADMIN-001 | Organization Audit Log / 组织审计 | `/audit-logs` | Org Admin | Administration | P2 | Phase 14A |
| ADMIN-002 | Operations Metrics / 运营指标 | `/organizations/:organizationId/metrics` | Org Admin | Administration | P2 | Phase 14A |
| ADMIN-003 | Feedback Summary / 反馈统计 | `/feedback/summary` | Org Admin | Administration | P2 | Phase 12 |

共识别 33 个设计面：1 个全局 Shell、4 个认证页面、4 个平台页面、3 个组织管理页面、5 个合同/文档页面、3 个审核页面、2 个预警页面、1 个通知设计面、1 个报告页面、3 个规则页面、3 个条款模板页面、3 个审计/运营页面。

### 6.1 Page to API Route Mapping

下表只列页面直接使用的 API Route。字段、Query、Body、错误、权限和状态码必须回查 `docs/api-contract.md`；本表不复制 Schema，也不得作为另一份接口契约。

| Page ID | Related API Routes |
| --- | --- |
| LAYOUT-001 | `GET /api/v1/auth/session`; `GET /api/v1/organizations/{organization_id}`; `GET /api/v1/notifications/unread-count` |
| AUTH-001 | `POST /api/v1/auth/login`; `GET /api/v1/auth/session`; `POST /api/v1/auth/logout` |
| AUTH-002 | `POST /api/v1/auth/password-reset/request` |
| AUTH-003 | `POST /api/v1/auth/password-reset/confirm` |
| AUTH-004 | `POST /api/v1/auth/invitations/accept` |
| PLATFORM-001 | `GET /api/v1/platform/organizations`; `POST /api/v1/platform/organizations` |
| PLATFORM-002 | `GET /api/v1/platform/organizations/{organization_id}`; `PATCH /api/v1/platform/organizations/{organization_id}` |
| PLATFORM-003 | `GET /api/v1/platform/model-configuration`; `PATCH /api/v1/platform/model-configuration` |
| PLATFORM-004 | `GET /api/v1/platform/audit-logs` |
| ORG-001 | `GET /api/v1/organizations/{organization_id}`; `GET /api/v1/organizations/{organization_id}/settings`; `PATCH /api/v1/organizations/{organization_id}/settings` |
| ORG-002 | `GET /api/v1/organizations/{organization_id}/members`; `POST /api/v1/organizations/{organization_id}/members`; `POST /api/v1/members/{member_id}/resend-invitation`; `PATCH /api/v1/members/{member_id}` |
| ORG-003 | `GET /api/v1/organizations/{organization_id}/support-access-grants`; `POST /api/v1/organizations/{organization_id}/support-access-grants`; `DELETE /api/v1/organizations/{organization_id}/support-access-grants/{grant_id}` |
| CONTRACT-001 | `GET /api/v1/contracts` |
| CONTRACT-002 | `POST /api/v1/contracts` |
| CONTRACT-003 | `GET /api/v1/contracts/{contract_id}`; `PATCH /api/v1/contracts/{contract_id}`; `POST /api/v1/contracts/{contract_id}/archive`; `POST /api/v1/contracts/{contract_id}/restore`; `PUT /api/v1/contracts/{contract_id}/access-grants/{user_id}`; `DELETE /api/v1/contracts/{contract_id}/access-grants/{user_id}` |
| CONTRACT-004 | `GET /api/v1/contracts/{contract_id}`; `POST /api/v1/contracts/{contract_id}/files`; `GET /api/v1/files/{file_id}/download` |
| CONTRACT-005 | `GET /api/v1/documents/{document_version_id}/pages/{page_no}`; `GET /api/v1/documents/{document_version_id}/blocks`; `GET /api/v1/files/{file_id}/download` |
| REVIEW-001 | `GET /api/v1/contracts/{contract_id}`; `POST /api/v1/contracts/{contract_id}/reviews` |
| REVIEW-002 | `GET /api/v1/review-tasks/{review_task_id}`; `POST /api/v1/review-tasks/{review_task_id}/retry` |
| REVIEW-003 | `GET /api/v1/review-tasks/{review_task_id}/results`; `PATCH /api/v1/contract-classifications/{classification_id}`; `PATCH /api/v1/extracted-fields/{field_id}`; `PATCH /api/v1/risk-findings/{finding_id}`; `PATCH /api/v1/clause-comparisons/{comparison_id}`; `POST /api/v1/review-tasks/{review_task_id}/complete`; `POST /api/v1/feedback`; `POST /api/v1/review-tasks/{review_task_id}/reports` |
| WARNING-001 | `GET /api/v1/warnings` |
| WARNING-002 | `GET /api/v1/warnings/{warning_id}`; `POST /api/v1/warnings/{warning_id}/events` |
| NOTIFY-001 | `GET /api/v1/notifications`; `POST /api/v1/notifications/{notification_id}/read`; `GET /api/v1/notifications/unread-count` |
| REPORT-001 | `GET /api/v1/reports/{report_id}`; `GET /api/v1/reports/{report_id}/download`; `POST /api/v1/review-tasks/{review_task_id}/reports` |
| RULE-001 | `GET /api/v1/risk-rule-bundles`; `POST /api/v1/risk-rule-bundles` |
| RULE-002 | `GET /api/v1/risk-rule-bundles/{bundle_id}`; `PATCH /api/v1/risk-rule-bundles/{bundle_id}`; `POST /api/v1/risk-rule-bundles/{bundle_id}/versions`; `POST /api/v1/risk-rule-bundle-versions/{version_id}/publish` |
| RULE-003 | `GET /api/v1/risk-rule-bundle-versions/{version_id}`; `PATCH /api/v1/risk-rule-bundle-versions/{version_id}`; `POST /api/v1/risk-rule-bundle-versions/{version_id}/publish` |
| CLAUSE-001 | `GET /api/v1/clause-templates`; `POST /api/v1/clause-templates` |
| CLAUSE-002 | `GET /api/v1/clause-templates/{template_id}`; `PATCH /api/v1/clause-templates/{template_id}`; `POST /api/v1/clause-templates/{template_id}/versions`; `POST /api/v1/clause-template-versions/{version_id}/publish` |
| CLAUSE-003 | `GET /api/v1/clause-template-versions/{version_id}`; `PATCH /api/v1/clause-template-versions/{version_id}`; `POST /api/v1/clause-template-versions/{version_id}/publish` |
| ADMIN-001 | `GET /api/v1/audit-logs` |
| ADMIN-002 | `GET /api/v1/organizations/{organization_id}/metrics/reviews`; `GET /api/v1/organizations/{organization_id}/metrics/warnings` |
| ADMIN-003 | `GET /api/v1/feedback/summary` |

### 6.2 Prototype Association

每个 Page ID 的原型使用 `docs/ui/stitch/<PAGE-ID>-*.html` 和对应 `.png`。状态 suffix 表示同一页面的不同状态，不创建新 Page ID；`.stitch/metadata.json` 标记为 `deprecated` 的文件不作为最终实现依据。当前 `REVIEW-003-review-result-and-human-review.*` 是历史基准，最终实现应使用 default、evidence-open、human-edit、version-conflict、blocking-pending 和 viewer-readonly 状态资产。

## 7. Core User Flows

### 7.1 Authentication Flow

```text
Login
-> POST /auth/login
-> Session Established
-> Resolve platform/organization context (API Contract 2.2.1)
-> Role-appropriate default landing page
```

辅助流程：

```text
Forgot Password
-> POST /auth/password-reset/request
-> Generic accepted message (never reveal account existence)
-> Reset link
-> POST /auth/password-reset/confirm
-> Login
```

```text
Invitation link
-> Accept Invitation
-> Existing user: activate membership
-> New user: provide display_name and password
-> Login
```

### 7.2 Contract Review Flow

API Contract 已固定真实顺序，UI 必须保持：

```text
Contract List
-> Create Contract
-> Contract Detail
-> Upload one file + acknowledge external model notice
-> Create Review using a validated file version
-> Review Progress (poll task state)
-> Review Result (when ready)
-> Warning review and Human Review
-> Complete Review
-> Generate HTML or PDF Report
-> Poll Report Status
-> Inline Preview or Download
```

上传只创建文件版本，不自动创建审核；审核创建只返回任务，不同步生成结果；重新审核创建新的 `review_task`，不是把已完成任务改回 processing。

### 7.3 Warning Flow

```text
Warning List
-> Warning Detail
-> Evidence jump to document/review context
-> confirm: pending_confirmation -> in_progress
-> resolve: in_progress -> resolved
-> close: resolved -> closed (resolution or revision_id required)
```

允许分支：

```text
pending_confirmation/in_progress -> false_positive or ignore -> ignored
ignored/closed -> reopen by Org Admin only -> in_progress
assign/note -> append event, main status unchanged
```

### 7.4 Human Review Flow

```text
Review Result
-> Inspect model value/current value/evidence
-> Edit classification, extracted field, risk, or clause comparison
-> Submit current version
-> Optional feedback label and note
-> Resolve mandatory review items
-> Complete Review
```

`409 RESOURCE_VERSION_CONFLICT` 时不得覆盖他人结果；前端刷新服务端最新资源，展示差异并要求用户重新应用修改。

### 7.5 Administration Flows

```text
Platform Organizations
-> Create Organization
-> Organization Detail
-> Update name/status/retention with version
```

```text
Members
-> Invite member
-> Observe invitation delivery state
-> Resend pending invitation
-> Change role/status with version
```

```text
Support Access
-> Create max-4-hour read-only grant with reason
-> Audit each use
-> Revoke immediately
```

```text
Risk Rule/Clause Template List
-> Detail and version history
-> Create draft from source or supplied content
-> Edit draft with version
-> Publish after validation
-> Published version becomes immutable
```

### 7.6 Report Flow

```text
Review Result (pending_review or completed)
-> Select html or pdf
-> POST report (202/generating)
-> GET report polling
-> ready
-> inline HTML preview or authorized download
```

失败后的再次生成、过期条件和完整报告状态仍受 Pending Decision `P-06` 约束；当前 UI 不发明专用 retry API。

## 8. Page Specifications

以下页面均使用同一规格：Purpose、Users、Route、Entry/Exit、Primary Goal、Layout、Components、Displayed Data、Actions、Form、Page States、Confirmation 和 Traceability。表格中的 API 字段名保持 `snake_case`；展示名称可本地化为中文。

### LAYOUT-001 Authenticated Application Shell / 登录后应用框架

#### Purpose

为所有受保护页面提供稳定导航、组织/平台语境、通知和用户会话操作。

#### Users

所有已认证用户；导航按平台管理员、组织角色和后端权限集合变化。

#### Route

N/A，共享布局组件；不是独立业务 Route。

#### Entry Points / Exit

- Entry：成功登录或恢复有效会话。
- Exit：退出登录后回到 `AUTH-001`；导航到 Inventory 中的受保护页面。

#### Primary User Goal

始终理解自己所处的工作区、组织和页面，并快速进入被授权模块。

#### Page Layout

```text
Sidebar
+-- Product Identity
+-- Workspace Context
+-- Permission-based Navigation

Top Header
+-- Breadcrumb
+-- Notification Entry
+-- User Menu

Main Content
+-- Page Header
+-- Page Content
```

#### Components

Menu、Breadcrumb、Badge、Dropdown、Avatar、Skeleton、Alert、Result、Tooltip。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `user.display_name` | 当前用户 | Session API | Text/Avatar fallback |
| `user.email` | 邮箱 | Session API | User menu text |
| `user.is_platform_admin` | 平台身份 | Session API | Workspace/navigation decision |
| `memberships[].organization_name` | 组织 | Session API | Context label; selection follows API Contract 2.2.1 |
| `memberships[].role` | 组织角色 | Session API | Role label |
| `unread_count` | 未读通知 | Notification API | Badge |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Navigate | Authorized user | Sidebar item | Open allowed module |
| Open notifications | Authenticated user | Header bell | Open `NOTIFY-001` |
| Logout | Authenticated user | User menu | Confirm optional, POST logout, return login |

#### Form

N/A。

#### Page States

| State | UI behaviour |
| --- | --- |
| Loading | Full-shell skeleton while session is restored; do not flash unauthorized navigation |
| Empty | N/A |
| Error | Safe application error with retry and request ID |
| Forbidden | Replace content with access result; keep only valid navigation |
| Conflict | Delegated to current page |
| Disabled | Disabled organization shows visible context and blocks business navigation per server response |
| Processing | Notification badge and page refresh do not shift layout |

#### Confirmation / Destructive Actions

退出可直接执行或使用轻量确认；不得加入“退出所有设备”等未定义能力。

#### Traceability

- Related Requirements：FR-A01、FR-A03、FR-W 通知；NFR 8.4。
- Related APIs：`GET /auth/session`, `POST /auth/logout`, `GET /notifications/unread-count`。
- Related Phase：Phase 2、Phase 3、Phase 11。

### AUTH-001 Login / 登录

#### Purpose

建立安全会话，并进入与用户身份相符的应用工作区。

#### Users

Public；已有有效会话的用户应被引导到默认落点。

#### Route

Frontend Page URL：`/login`。

#### Entry Points / Exit

- Entry：未认证访问、会话过期、用户主动退出。
- Exit：成功后进入角色默认落点；可进入忘记密码。

#### Primary User Goal

使用邮箱和密码登录，不泄露凭据或会话令牌。

#### Page Layout

```text
Product Identity
Login Form
+-- Email
+-- Password
+-- Submit
+-- Forgot Password Link
Safe Error Region
```

#### Components

Form、Input、Password Input、Button、Alert。

#### Displayed Data

登录前没有业务数据；错误仅展示 API 的安全 `message` 与可选 `request_id`。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Login | Public | Submit valid form | Establish Cookie session; route by context |
| Forgot password | Public | Text link | Open `AUTH-002` |

#### Form

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| 邮箱 | Email Input | Yes | Valid email shape; server normalizes | `email` |
| 密码 | Password Input | Yes | Non-empty; exact policy server-controlled | `password` |

Submit behaviour：一次只允许一个进行中的提交；按钮 loading 并禁用重复点击。`401` 使用统一“账号或密码错误”，`403 USER_DISABLED` 使用账户不可用提示，`429` 显示限流信息，不保存密码。

#### Page States

| State | UI behaviour |
| --- | --- |
| Loading | Submit button loading; fields remain visible |
| Empty | N/A |
| Error | Inline safe alert; credentials never echoed |
| Forbidden | Disabled user message without organization data |
| Conflict | N/A |
| Disabled | Submit disabled until required fields valid or while submitting |
| Processing | Session establishment indicated without fake progress |

#### Confirmation / Destructive Actions

N/A。

#### Traceability

- Related Requirements：FR-A01、FR-A03。
- Related APIs：`POST /api/v1/auth/login`, `GET /api/v1/auth/session`。
- Related Phase：Phase 2。

### AUTH-002 Forgot Password / 忘记密码

#### Purpose

发起不泄露账号是否存在的密码重置请求。

#### Users

Public。

#### Route

Frontend Page URL：`/password-reset`。

#### Entry Points / Exit

- Entry：Login 的“忘记密码”。
- Exit：返回登录；提交成功后停留在通用受理结果。

#### Primary User Goal

提交邮箱并得到一致的受理反馈。

#### Page Layout

Page title、Email Form、Primary Button、generic accepted Result、Back to Login。

#### Components

Form、Input、Button、Result、Alert。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `accepted` | 已受理 | API | Result state |
| `message` | 处理说明 | API | Text;不得改写为“邮箱存在” |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Request reset | Public | Submit | Show generic accepted result |
| Return to login | Public | Link | Open `AUTH-001` |

#### Form

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| 邮箱 | Email Input | Yes | Valid email shape | `email` |

按钮提交中禁用；无论邮箱是否存在均使用相同成功 UI。`429` 显示稍后重试，不能改变账号枚举保护。

#### Page States

Loading：表单内 loading；Empty：N/A；Error：字段或限流错误；Forbidden：N/A；Conflict：N/A；Disabled：无有效邮箱或提交中；Processing：accepted 结果，不展示邮件投递内部状态。

#### Confirmation / Destructive Actions

N/A。

#### Traceability

- Related Requirements：FR-A01。
- Related APIs：`POST /api/v1/auth/password-reset/request`。
- Related Phase：Phase 2。

### AUTH-003 Reset Password / 重置密码

#### Purpose

使用一次性令牌设置新密码并撤销该用户既有会话。

#### Users

Public，持有效重置令牌的用户。

#### Route

Frontend Page URL：`/password-reset/confirm?token=...`；令牌仅用于提交，不在页面正文回显。

#### Entry Points / Exit

- Entry：SMTP 重置链接。
- Exit：成功后返回 Login；失败时可重新发起请求。

#### Primary User Goal

安全设置符合服务端策略的新密码。

#### Page Layout

Password Form、confirmation input（仅前端确认，不进入 API）、password policy area（12-128 个字符）、Submit、success Result。

#### Components

Form、Password Input、Button、Alert、Result。

#### Displayed Data

仅展示服务端验证错误和成功结果，不展示令牌。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Reset password | Token holder | Submit | `204`, show success and login CTA |
| Request new link | Public | Expired/used result link | Open `AUTH-002` |

#### Form

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| Token | Hidden route value | Yes | Non-empty | `token` |
| 新密码 | Password Input | Yes | 12-128 个字符；不强制字符类别 | `new_password` |
| 确认新密码 | Password Input | Yes | Must equal new password | Frontend-only |

提交中禁用；`TOKEN_INVALID/EXPIRED/ALREADY_USED` 转为明确不可继续状态；`422` 映射字段错误。

#### Page States

Loading：提交 loading；Empty：缺 token 显示无效链接；Error：安全错误；Forbidden：N/A；Conflict：令牌已使用；Disabled：字段不合法/提交中；Processing：N/A。

#### Confirmation / Destructive Actions

成功会撤销其他会话；提交前以辅助文案说明，不再增加确认对话框。

#### Traceability

- Related Requirements：FR-A01。
- Related APIs：`POST /api/v1/auth/password-reset/confirm`。
- Related Phase：Phase 2；密码策略和 Token TTL 采用 API Contract 3.1，边界测试仍是 Phase 2 完成条件。

### AUTH-004 Accept Invitation / 接受邀请

#### Purpose

激活组织成员关系，并在新用户场景创建账号。

#### Users

Public，持有效邀请令牌的受邀用户。

#### Route

Frontend Page URL：`/invitations/accept?token=...`。

#### Entry Points / Exit

- Entry：SMTP 邀请链接。
- Exit：成功后进入 Login；无效/过期时联系组织管理员。

#### Primary User Goal

接受组织邀请，并在需要时设置展示名和密码。

#### Page Layout

Invitation context、conditional New User Form、Submit、success/error Result。现有文档未定义“预检邀请”API，因此页面不能在提交前声称已确认组织、邮箱或角色。

#### Components

Form、Input、Password Input、Button、Alert、Result。

#### Displayed Data

成功后可展示 `organization_id`、`role` 和 `status` 的安全结果；组织名称未在成功 Schema 中定义，不自行展示。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Accept invitation | Invitee | Submit | Activate membership/create user |
| Go to login | Accepted user | Success CTA | Open `AUTH-001` |

#### Form

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| Token | Hidden route value | Yes | Non-empty | `token` |
| 展示名 | Text Input | New user only | Non-empty when required by server | `display_name` |
| 密码 | Password Input | New user only | Server password policy | `password` |

现有/新用户分支由服务端语义决定；若首次提交返回字段要求，UI 保留 token 并显示相应字段。不得增加未定义的邀请预检请求。

#### Page States

Loading：提交 loading；Empty：缺 token；Error：无效/过期/邮箱冲突/字段错误；Forbidden：N/A；Conflict：`EMAIL_ALREADY_IN_USE`；Disabled：字段不完整/提交中；Processing：N/A。

#### Confirmation / Destructive Actions

N/A。

#### Traceability

- Related Requirements：FR-A02。
- Related APIs：`POST /api/v1/auth/invitations/accept`。
- Related Phase：Phase 2；P-08/P-09 已关闭；SMTP 后台失败可观测性的实现与测试仍阻塞 Phase 2 完成。

### PLATFORM-001 Organization List / 平台组织列表

#### Purpose

让平台管理员检索组织并发起创建。

#### Users

Platform Admin，Read/Write。

#### Route

Frontend Page URL：`/platform/organizations`。

#### Entry Points / Exit

- Entry：Platform Sidebar。
- Exit：Organization Detail、Create Organization Dialog（recommended）。

#### Primary User Goal

快速找到组织、查看状态并进入配置详情。

#### Page Layout

```text
Page Header + Create Organization
Filter Bar: Search, Status, Sort
Organization Table
Cursor Pagination
```

#### Components

Input、Select、Table、Tag、Button、Dialog、Form、Pagination/Load More、Empty、Skeleton。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `name` | 组织名称 | API | Link |
| `status` | 状态 | API | Tag |
| `retention_days` | 保留天数 | API | Number + unit |
| `created_at` | 创建时间 | API when present | Local datetime |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Search/filter | Platform Admin | Filter change/submit | Reload cursor list |
| Open organization | Platform Admin | Name link | `PLATFORM-002` |
| Create organization | Platform Admin | Primary button | Submit create form and open detail |

#### Form

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| 组织名称 | Text Input | Yes | Non-empty | `name` |
| 初始管理员邮箱 | Email Input | Yes | Valid email | `initial_admin_email` |
| 保留天数 | Number Input | No | Non-negative; default 180 | `retention_days` |

创建提交带自动生成的 `Idempotency-Key`；提交中禁用。冲突保留输入并显示名称冲突。

#### Page States

Loading：table skeleton；Empty：无组织/筛选无结果分开；Error：列表重试；Forbidden：平台权限结果页；Conflict：创建名称冲突；Disabled：提交中；Processing：N/A。

#### Confirmation / Destructive Actions

创建无需破坏性确认。

#### Traceability

- Related Requirements：FR-A02、FR-O。
- Related APIs：`GET/POST /api/v1/platform/organizations`。
- Related Phase：Phase 3。

### PLATFORM-002 Organization Detail / 平台组织详情

#### Purpose

查看并更新单个组织的名称、状态和保留期。

#### Users

Platform Admin，Read/Write；不等于进入组织业务数据。

#### Route

Frontend Page URL：`/platform/organizations/:organizationId`。

#### Entry Points / Exit

- Entry：Organization List。
- Exit：返回列表；模型配置是独立导航。

#### Primary User Goal

维护组织级平台属性，同时理解禁用操作影响。

#### Page Layout

Breadcrumb、Page Header + Status Tag、Descriptions、Edit Form、danger zone。

#### Components

Descriptions、Form、Input、InputNumber、Select/Radio、Alert、Button、Dialog。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `id` | 组织 ID | API | Copyable text |
| `name` | 组织名称 | API | Text/Input |
| `status` | 状态 | API | Tag/Control |
| `retention_days` | 保留天数 | API | Number |
| `settings` | 非秘密设置摘要 | API | Descriptions/JSON-safe summary |
| `version` | 当前版本 | API | Hidden submit value / metadata |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Update organization | Platform Admin | Save | Return updated resource |
| Disable/enable | Platform Admin | Confirm status change | Update status using version |

#### Form

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| 组织名称 | Text Input | Conditional | Non-empty if changed | `name` |
| 状态 | Status control | Conditional | `active|disabled` | `status` |
| 保留天数 | Number Input | Conditional | Non-negative | `retention_days` |
| 版本 | Hidden | Yes | Latest integer | `version` |

至少一个字段变化才允许提交。`409` 刷新最新资源，不自动覆盖。

#### Page States

Loading：detail skeleton；Empty：N/A；Error：safe retry；Forbidden：platform only；Conflict：version conflict comparison/refresh；Disabled：unchanged form/submitting；Processing：N/A。

#### Confirmation / Destructive Actions

禁用组织需要 confirmation dialog，明确会影响组织访问；无需 reason，因为 API 没有 reason 字段。启用可轻量确认。

#### Traceability

- Related Requirements：FR-A02、FR-O。
- Related APIs：`GET/PATCH /api/v1/platform/organizations/{organization_id}`。
- Related Phase：Phase 3。

### PLATFORM-003 Model Configuration / 模型配置

#### Purpose

让平台管理员查看模型环境配置状态并更新允许通过 API 修改的非秘密运行参数。

#### Users

Platform Admin，Read/Write non-secret fields。

#### Route

Frontend Page URL：`/platform/model-configuration`。

#### Entry Points / Exit

Platform Sidebar；保存后停留本页。

#### Primary User Goal

确认模型是否可用并调整超时、重试、用量记录和启停状态，而不接触密钥。

#### Page Layout

Configuration Status Alert、Read-only Environment Summary、Editable Form、Save Actions。

#### Components

Alert、Descriptions、Form、InputNumber、Switch、Select、Button。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `provider` | 提供方 | API | Read-only text |
| `model` | 模型 | API | Read-only text |
| `model_source` | 配置来源 | API | Tag |
| `secret_configured` | 密钥状态 | API | Success/Danger status; never show secret |
| `timeout_seconds` | 超时秒数 | API | Number input |
| `max_retries` | 最大重试 | API | Number input |
| `usage_tracking_enabled` | 用量记录 | API | Switch |
| `hard_budget_enabled` | 硬预算 | API | Read-only status |
| `organization_overrides_allowed` | 组织覆盖 | API | Read-only false status |
| `status` | 配置状态 | API | Tag/Select |
| `version` | 版本 | API | Hidden submit value |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Save runtime settings | Platform Admin | Save | Update allowed fields |
| Disable/enable model use | Platform Admin | Confirm status change | Update `status` |

#### Form

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| 超时秒数 | Number Input | No | Integer, server range | `timeout_seconds` |
| 最大重试 | Number Input | No | Integer, server range | `max_retries` |
| 用量记录 | Switch | No | Boolean | `usage_tracking_enabled` |
| 状态 | Select | No | `active|disabled` | `status` |
| 版本 | Hidden | Yes | Latest integer | `version` |

模型名、密钥、预算值和组织覆盖不是可编辑字段。`503 MODEL_ENVIRONMENT_NOT_CONFIGURED` 显示部署配置提示，不提供密钥输入框。

#### Page States

Loading：form skeleton；Empty：N/A；Error：retry；Forbidden：platform only；Conflict：reload latest config；Disabled：secret unconfigured or submitting; fields still inspectable；Processing：N/A。

#### Confirmation / Destructive Actions

将状态改为 `disabled` 需要确认，说明新模型任务将受影响；API 未要求 reason。

#### Traceability

- Related Requirements：FR-O；模型密钥安全要求。
- Related APIs：`GET/PATCH /api/v1/platform/model-configuration`。
- Related Phase：Phase 3；Pending P-10。

### PLATFORM-004 Platform Audit Log / 平台审计

#### Purpose

让平台管理员跨组织查询只读审计事实。

#### Users

Platform Admin，Read only。

#### Route

Frontend Page URL：`/platform/audit-logs`。

#### Entry Points / Exit

Platform Sidebar；资源链接仅在目标页面和权限语义明确时提供。

#### Primary User Goal

按组织、动作、资源、操作者和时间定位审计事件。

#### Page Layout

Filter Bar、Audit Table、Detail Drawer for safe summaries、Cursor Pagination。

#### Components

Form、Select、DateTime Range、Table、Drawer、Descriptions、Pagination。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `created_at` | 时间 | API | Local datetime |
| `organization_id` | 组织 | API | ID/text |
| `action` | 动作 | API | Text/Tag |
| `resource_type` | 资源类型 | API | Text |
| `resource_id` | 资源 ID | API | Copyable text |
| `actor_id` | 操作者 | API | ID/text |
| `request_id` | 请求 ID | API | Copyable text |
| `before_summary`/`after_summary` | 变更摘要 | API | Safe structured detail |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Apply filters | Platform Admin | Filter submit/change | Reload from first cursor |
| View safe summary | Platform Admin | Row/detail action | Open read-only Drawer |
| Load next page | Platform Admin | Pagination action | Request next cursor |

#### Form

Query fields：`organization_id`, `action`, `resource_type`, `actor_id`, `created_from`, `created_to`, cursor pagination；无修改或导出。

#### Page States

Loading：table skeleton；Empty：无事件/筛选无结果；Error：retry；Forbidden：platform only；Conflict：N/A；Disabled：invalid date range；Processing：N/A。

#### Confirmation / Destructive Actions

N/A；审计不可修改或删除。

#### Traceability

- Related Requirements：FR-A04、FR-O。
- Related APIs：`GET /api/v1/platform/audit-logs`。
- Related Phase：Phase 14A。

### ORG-001 Organization Settings / 组织设置

#### Purpose

让组织管理员维护契约允许的非秘密限制、预警、OCR、保留期和报告水印设置。

#### Users

Org Admin，Read/Write；Reviewer/Viewer 无入口。

#### Route

Frontend Page URL：`/organizations/:organizationId/settings`。

#### Entry Points / Exit

Organization Administration Sidebar；保存后停留本页。

#### Primary User Goal

在平台允许范围内调整本组织运行策略。

#### Page Layout

Page Header、Settings Form 分为“文件与并发”“预警与 OCR”“保留与报告”、Save Bar。

#### Components

Form、InputNumber、Switch、Input、Alert、Button。

#### Displayed Data

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| 文件大小上限 | Number Input | No | Integer bytes, server bounds | `file_size_limit_bytes` |
| 页数上限 | Number Input | No | Positive integer | `page_limit` |
| 并发审核上限 | Number Input | No | Positive integer | `concurrent_review_limit` |
| 中风险生成预警 | Switch | No | Boolean | `warn_on_medium_risk` |
| OCR 低置信阈值 | Decimal Input | No | 0-1 | `ocr_low_confidence_threshold` |
| 保留天数 | Number Input | No | Non-negative/server bounds | `retention_days` |
| 报告水印 | Text Input | No | String/server length | `report_watermark` |
| 版本 | Hidden | Yes | Latest integer | `version` |

这些字段同时构成页面展示值；非编辑模式使用标签与格式化数值呈现。

#### Form

表单字段、必填性、校验和 API 映射见上表；PATCH 只发送变化字段和必填 `version`。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Save settings | Org Admin | Save | PATCH changed fields and version |
| Discard changes | Org Admin | Cancel/reset | Restore last server values |

提交中禁用；字段错误就地展示；`409` 拉取新版本并让用户重新确认修改。

#### Page States

Loading：form skeleton；Empty：N/A；Error：retry；Forbidden：org admin only；Conflict：refresh/diff prompt；Disabled：no changes/submitting；Processing：N/A。

#### Confirmation / Destructive Actions

改变保留期可能影响未来清理，应使用 confirmation；API 没有 reason，不新增字段。其他保存不需要确认。

#### Traceability

- Related Requirements：FR-D、FR-W、FR-O、安全与保留要求。
- Related APIs：`GET/PATCH /api/v1/organizations/{organization_id}/settings`。
- Related Phase：Phase 3。

### ORG-002 Member Management / 成员管理

#### Purpose

管理成员、邀请状态、角色和启停状态。

#### Users

Org Admin，Read/Write。

#### Route

Frontend Page URL：`/organizations/:organizationId/members`。

#### Entry Points / Exit

Organization Administration Sidebar；邀请和编辑建议使用 Dialog/Drawer 并留在列表。

#### Primary User Goal

找到成员并安全完成邀请、重发、角色变更或停用。

#### Page Layout

```text
Page Header + Invite Member
Filter Bar: Search, Role, Status, Sort
Member Table
Cursor Pagination
Invite Dialog / Edit Drawer
```

#### Components

Input、Select、Table、Tag、Dropdown、Dialog、Drawer、Form、Alert、Pagination。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `display_name` | 姓名 | API | Text |
| `email` | 邮箱 | API | Text |
| `role` | 角色 | API | Tag |
| `status` | 状态 | API | Tag |
| `email_delivery_status` | 邀请投递 | API when present | Status text/tag |
| `invited_at` | 邀请时间 | API when present | Local datetime |
| `created_at` | 加入/创建时间 | API | Local datetime |
| `version` | 版本 | API | Hidden edit value |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Invite member | Org Admin | Primary button | Create pending invitation |
| Resend invitation | Org Admin | Row action, pending only | Queue new invitation; old token invalidated |
| Change role/status | Org Admin | Edit action | PATCH with version |

#### Form

Invite：`email`（Email, required）、`role`（Select `org_admin|reviewer|viewer`, required）。Edit：`role?`, `status? active|disabled`, `version` required。提交中禁用；invite/resend 使用 Idempotency-Key；不能显示或复制邀请 token。

#### Page States

Loading：table skeleton；Empty：邀请首位成员 CTA/筛选无结果；Error：retry；Forbidden：org admin only；Conflict：membership exists/last admin/version conflict；Disabled：row action gated by status/submitting；Processing：email delivery `queued` as server fact only。

#### Confirmation / Destructive Actions

- 停用成员：confirmation，说明会撤销相关会话；不要求 reason。
- 降级/移除管理员能力：confirmation；`LAST_ORG_ADMIN` 必须保持原状态。
- 重发邀请：轻量确认，说明旧链接失效。

#### Traceability

- Related Requirements：FR-A02、FR-A03、FR-A04。
- Related APIs：`GET/POST /organizations/{organization_id}/members`, `POST /members/{member_id}/resend-invitation`, `PATCH /members/{member_id}`。
- Related Phase：Phase 4。

### ORG-003 Support Access Management / 支持授权

#### Purpose

让组织管理员授予、查看和撤销最长四小时的平台只读支持授权。

#### Users

Org Admin，Read/Write。

#### Route

Frontend Page URL：`/organizations/:organizationId/support-access-grants`。

#### Entry Points / Exit

Organization Administration Sidebar；创建建议使用 Dialog，详情建议使用 Drawer。

#### Primary User Goal

在明确原因和到期时间下临时授权平台支持，并可立即撤销。

#### Page Layout

Security Alert、Page Header + Grant Access、Status Filters、Grant Table、Create Dialog、Detail Drawer。

#### Components

Alert、Table、Tag、Form、Select/Input、DateTimePicker、Dialog、Descriptions、Button。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `platform_admin_user_id` | 平台管理员 | API | ID/text |
| `reason` | 授权原因 | API | Text |
| `status` | 状态 | API | Tag |
| `granted_by` | 授权人 | API | ID/text |
| `created_at` | 创建时间 | API | Local datetime |
| `expires_at` | 到期时间 | API | Local datetime/countdown text |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Filter grants | Org Admin | Filter change | Reload list |
| Create grant | Org Admin | Submit dialog | Create active grant |
| Revoke grant | Org Admin | Row danger action | Immediate DELETE, status revoked |

#### Form

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| 平台管理员 | Select/ID input | Yes | Must resolve to active platform admin server-side | `platform_admin_user_id` |
| 原因 | Textarea | Yes | Non-empty | `reason` |
| 到期时间 | DateTimePicker | Yes | Future and <= 4 hours from creation | `expires_at` |

使用 Idempotency-Key；提交中禁用；不得提供写权限或下载权限选择。

#### Page States

Loading：table skeleton；Empty：no grants；Error：retry；Forbidden：org admin only；Conflict：active grant exists；Disabled：expired/revoked rows cannot revoke again visually, though repeat is idempotent；Processing：active countdown is display-only。

#### Confirmation / Destructive Actions

创建需要 confirmation，明确“只读 JSON、禁止修改和下载、全程审计、最长四小时”。撤销需要 confirmation，立即生效；不额外要求 reason。

#### Traceability

- Related Requirements：FR-A03、FR-A04；tenant/authorization safety。
- Related APIs：`GET/POST /organizations/{organization_id}/support-access-grants`, `DELETE /organizations/{organization_id}/support-access-grants/{grant_id}`。
- Related Phase：Phase 4。

### CONTRACT-001 Contract List / 合同列表

#### Purpose

展示当前用户可见的合同，并通过搜索、筛选和稳定游标快速定位目标合同。

#### Users

Org Admin、Reviewer：Read/Write entry；Viewer：仅显式授权合同 Read。

#### Route

Frontend Page URL：`/contracts`。

#### Entry Points / Exit

- Entry：Organization Sidebar、返回列表、相关流程完成后。
- Exit：Create Contract、Contract Detail。

#### Primary User Goal

找到目标合同，理解其基本状态，并进入合同详情继续审核流程。

#### Page Layout

```text
Page Header
+-- Title
+-- Create Contract (authorized roles)
Filter Bar
+-- Search
+-- Contract Status
+-- Declared Type
+-- Owner
+-- Sort
Contract Table
Cursor Pagination
```

#### Components

Input、Select、Table、Tag、Button、Empty、Skeleton、Pagination/Load More。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `display_no` | 合同编号 | API | Monospace text/link |
| `title` | 合同名称 | API | Primary link |
| `declared_type` | 声明类型 | API | Localized text/tag |
| `status` | 合同状态 | API | Tag |
| `owner_id` | 负责人 | API when returned | ID/text; do not invent name |
| `created_at` | 创建时间 | API when returned | Local datetime |
| `updated_at` | 更新时间 | API when returned | Local datetime |

列表最小响应示例只保证前四项；其他列仅在实际 OpenAPI 投影包含字段时启用。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Search/filter/sort | All allowed | Filter bar | Reload from first cursor |
| Open contract | All allowed | Row/title | `CONTRACT-003` |
| Create contract | Org Admin, Reviewer | Primary button | `CONTRACT-002` |

#### Form

筛选 Query：`q`, `status`, `declared_type`, `owner_id`, `sort=created_at|updated_at|title`, `direction`, `limit`, `cursor`。未知筛选不发送。

#### Page States

| State | UI behaviour |
| --- | --- |
| Loading | Table skeleton with stable columns |
| Empty | No contracts: create CTA for writers; neutral read-only message for viewer |
| Error | Preserve filters; safe retry with request ID |
| Forbidden | Organization access result; no resource disclosure |
| Conflict | N/A |
| Disabled | Create hidden for viewer/disabled organization |
| Processing | Background refresh keeps current rows visible |

#### Confirmation / Destructive Actions

N/A；归档在详情页执行。

#### Traceability

- Related Requirements：FR-D、FR-A03、FR-RP。
- Related APIs：`GET /api/v1/contracts`。
- Related Phase：Phase 5。

### CONTRACT-002 Create Contract / 创建合同

#### Purpose

创建合同元数据，为后续单文件上传和审核建立资源容器。

#### Users

Org Admin、Reviewer，Write。

#### Route

Frontend Page URL：`/contracts/new`。

#### Entry Points / Exit

- Entry：Contract List 主按钮。
- Exit：成功进入 Contract Detail；取消返回列表。

#### Primary User Goal

用最少必要信息创建合同，并继续上传文件。

#### Page Layout

Breadcrumb、Page Header、compact Form、Actions。

#### Components

Form、Input、Select、Button、Alert。

#### Displayed Data

成功后从 API 使用 `id`, `display_no`, `title`, `declared_type`, `status`, `current_file`, `version`；创建前无业务数据。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Create | Org Admin, Reviewer | Submit | Create resource; navigate to detail |
| Cancel | Org Admin, Reviewer | Secondary button | Return list without request |

#### Form

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| 合同名称 | Text Input | Yes | Non-empty, server length | `title` |
| 声明合同类型 | Select | No | `purchase|sales|nda|outsourcing|employment|other` | `declared_type` |

组织不在表单中提交。使用 Idempotency-Key；提交中禁用；成功后建议 CTA“上传合同文件”。

#### Page States

Loading：submit loading；Empty：N/A；Error：field/global error；Forbidden：no create permission；Conflict：idempotency conflict safe message；Disabled：invalid/submitting；Processing：N/A。

#### Confirmation / Destructive Actions

离开有未保存输入时可使用 unsaved-changes confirmation；创建本身不需确认。

#### Traceability

- Related Requirements：FR-D01、FR-A03。
- Related APIs：`POST /api/v1/contracts`。
- Related Phase：Phase 5。

### CONTRACT-003 Contract Detail / 合同详情

#### Purpose

聚合合同元数据、文件版本、最近审核和关联操作，是合同审核流程的资源入口。

#### Users

Org Admin、Reviewer：Read/Write；authorized Viewer：Read only。

#### Route

Frontend Page URL：`/contracts/:contractId`。

#### Entry Points / Exit

- Entry：Contract List、Warning Detail、Review pages。
- Exit：File Upload/Versions、Create Review、Review Progress/Result、Document Preview。

#### Primary User Goal

理解合同当前状态和可用资产，并执行下一项合法动作。

#### Page Layout

```text
Breadcrumb + Page Header
+-- display_no, title, status
+-- Primary next action
+-- More Actions
Overview Descriptions
File Versions Section
Latest Review Section
Viewer Access Section (limited by current API)
```

#### Components

Descriptions、Tag、Table、Button、Dropdown、Dialog、Alert、Empty、Skeleton。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `display_no` | 合同编号 | API | Text |
| `title` | 合同名称 | API | Title/Input in edit mode |
| `declared_type` | 声明类型 | API | Text/Select in edit mode |
| `status` | 状态 | API | Tag |
| `owner_id` | 负责人 | API when present | ID/text |
| `files[].id` | 文件 ID | API | Link/action reference |
| `files[].version_no` | 文件版本 | API | Version label |
| `files[].is_current` | 当前文件 | API | Tag |
| `latest_review.id` | 最近审核 | API | Link |
| `latest_review.status` | 最近审核状态 | API | Tag |
| `version` | 资源版本 | API | Hidden edit value |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Edit metadata | Org Admin, Reviewer | Edit | PATCH title/type/version |
| Upload file | Org Admin, Reviewer; active only | Primary/section action | `CONTRACT-004` |
| Start review | Org Admin, Reviewer; valid file/no blocking active review | CTA | `REVIEW-001` |
| Open latest review | All allowed | Review link | Progress or Result based on status |
| Download file | Contract-visible users | File action | Authorized download |
| Archive | Org Admin, Reviewer | More action + confirm | Contract becomes archived |
| Restore | Org Admin only | Page action + confirm | Contract becomes active |
| Grant/revoke viewer access | Org Admin | Access action | PUT/DELETE access grant |

#### Form

Metadata：`title?`, `declared_type?`（including null）, `version` required。Viewer grant：`user_id` path selected from same-organization active viewer; `access_level` fixed `read`。

当前 API 没有“查询某合同已有 viewer grants”接口，也未在 Contract Detail 响应中定义 grant 列表。因此 UI 可以执行针对已知 viewer 的 grant/revoke，但不能设计可信的完整授权清单；这是 Pending API/UI gap，不得通过前端缓存伪造事实。

#### Page States

| State | UI behaviour |
| --- | --- |
| Loading | Header and section skeletons |
| Empty | No files: upload CTA for writers; read-only empty for viewer; no review: contextual next step |
| Error | Section retry where possible; page retry for contract failure |
| Forbidden | API may return 404 to hide unauthorized contract |
| Conflict | Metadata version conflict reload; archive blocked by active review; restore only archived |
| Disabled | Archived contract is read-only; writer actions disabled/hidden by state and role |
| Processing | Latest active review shown with status link; do not imply contract progress percentage |

#### Confirmation / Destructive Actions

- Archive：confirmation；无 API reason 字段。若 `ACTIVE_REVIEW_EXISTS`，关闭 dialog 并引导查看 active review。
- Restore：confirmation，Org Admin only。
- Revoke viewer access：confirmation；repeat revoke remains success.

#### Traceability

- Related Requirements：FR-D、FR-A02/A03、FR-RP。
- Related APIs：`GET/PATCH /contracts/{contract_id}`, `POST /contracts/{contract_id}/archive|restore`, `PUT/DELETE /contracts/{contract_id}/access-grants/{user_id}`, `GET /files/{file_id}/download`。
- Related Phase：Phase 5、Phase 6、Phase 9A archive guard。

### CONTRACT-004 File Upload and Versions / 文件上传与版本

#### Purpose

安全上传一个合同文件版本、记录外部模型告知确认，并提供版本与下载入口。

#### Users

Org Admin、Reviewer：Upload/Download；authorized Viewer：Read version summary/Download only。

#### Route

Frontend Page URL：`/contracts/:contractId/files`；也可作为 Contract Detail 的重点 section，但必须有独立 P0 prototype frame。

#### Entry Points / Exit

- Entry：Contract Detail 上传/文件区域。
- Exit：Contract Detail、Document Preview、Create Review。

#### Primary User Goal

选择合法文件、理解数据外发范围、确认授权并完成可追踪上传。

#### Page Layout

```text
Contract Context
External Model Notice Alert
Upload Form
+-- File Picker/Drop Zone
+-- Make Current
+-- Required Acknowledgement
+-- Upload Progress
File Version Table
```

#### Components

Upload、Alert、Checkbox、Switch/Checkbox、Progress、Button、Table、Tag、Empty、Dialog。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `file.id` | 文件 ID | Upload API | Reference text |
| `file.original_name` | 文件名 | Upload API | Text |
| `file.media_type` | 文件类型 | Upload API | Text/tag |
| `file.size_bytes` | 大小 | Upload API | Formatted bytes |
| `file.scan_status` | 扫描状态 | Upload API | Tag |
| `contract_file_id` | 合同文件版本 ID | Upload API | Reference |
| `version_no` | 版本号 | Contract/Upload API | Version label |
| `is_current` | 当前版本 | Contract/Upload API | Tag |
| `external_model_notice_acknowledged_at` | 告知确认时间 | Upload API | Local datetime |

历史版本列表仅展示 Contract Detail 实际返回的字段；不得假设每个历史版本都返回完整 File Object。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Select file | Org Admin, Reviewer | File picker/drop | Local precheck only |
| Upload | Org Admin, Reviewer | Submit acknowledged form | Create one file version |
| Download | Contract-visible user | Row action | Authorized binary response |
| Continue to review | Org Admin, Reviewer | Success CTA | `REVIEW-001` with returned version |

#### Form

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| 文件 | Binary Upload | Yes | One `.docx/.pdf/.png/.jpg/.jpeg`; server validates MIME/signature/size | `file` |
| 设为当前版本 | Checkbox/Switch | No | Boolean, default true | `make_current` |
| 外部模型告知确认 | Checkbox | Yes/true | Must be true | `external_model_notice_acknowledged` |

必须展示 API Contract 第 20 节冻结的告知语义。使用 Idempotency-Key；上传中禁用替换文件和重复提交；进度仅表达浏览器上传字节，不冒充病毒扫描/存储进度。

#### Page States

| State | UI behaviour |
| --- | --- |
| Loading | Version table skeleton |
| Empty | No file versions; upload CTA for writer |
| Error | Map 413/415/422/503 to file-specific safe messages; retry preserves acknowledgement only if policy allows |
| Forbidden | Viewer has no upload control; hidden contract returns not found |
| Conflict | Archived contract prevents upload; idempotency conflict shown safely |
| Disabled | Upload disabled until file + acknowledgement and while uploading |
| Processing | Browser upload progress; post-upload scan result only from API response |

#### Confirmation / Destructive Actions

外部模型告知本身是强制确认，不再叠加额外 dialog；若以 checkbox 表达，文案必须完整可读。

#### Traceability

- Related Requirements：FR-D01、FR-D05、安全与隐私 8.3。
- Related APIs：`POST /contracts/{contract_id}/files`, `GET /files/{file_id}/download`, `GET /contracts/{contract_id}`。
- Related Phase：Phase 6。

### CONTRACT-005 Document Preview / 文档预览

#### Purpose

展示合同原文结构，并响应证据 Locator 跳转和高亮。

#### Users

任何可查看所属合同的用户；平台支持访问不得下载，但现有 JSON GET 可在有效 grant 下只读访问。

#### Route

Frontend Page URL：`/documents/:documentVersionId`，Query/fragment 可携带 locator，但不能成为权限依据。

#### Entry Points / Exit

- Entry：Review Result evidence、Warning evidence、Contract file section。
- Exit：返回来源页面，并保持来源筛选/选中项。

#### Primary User Goal

核对结论对应的原文位置和上下文。

#### Page Layout

```text
Document Toolbar
+-- Document identity
+-- Page/locator navigation
Preview Surface
+-- PDF/Image page with highlight
or
+-- DOCX logical blocks with paragraph/table highlight
Locator Context Panel
+-- Quote
+-- OCR/quality status
```

#### Components

Toolbar、InputNumber、Button icons、Alert、Skeleton、Scroll container、Descriptions、Tag、Empty。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `document_version_id` | 文档版本 | API/Locator | Metadata |
| `page_no` | 页码 | API | Page control for PDF/image only |
| `text` | 页面文本 | API | Searchable/read-only text |
| `image_file_id` | 页图 | API | Authorized image surface when supported |
| `ocr_status` | OCR 状态 | API | Tag/Alert |
| `ocr_confidence` | OCR 置信度 | API | Number/quality warning |
| `blocks[].order_no` | 块顺序 | API | Ordered content |
| `blocks[].block_type` | 块类型 | API | Structural label |
| `blocks[].text` | 块文本 | API | Highlightable text |
| Locator fields | 证据定位 | Result API | Highlight target |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Open locator | Contract-visible user | Evidence link | Navigate/highlight target |
| Change PDF/image page | Contract-visible user | Page control | GET declared page |
| Return to source | Contract-visible user | Back link | Restore prior result/warning context |

#### Form

N/A。页码控制仅适用于 `pdf_page|image_page`；不得为 DOCX 填充虚构页码。

#### Page States

Loading：page skeleton；Empty：blank/empty page warning；Error：page retry；Forbidden：404/not found semantics；Conflict：`DOCUMENT_NOT_READY`；Disabled：page controls disabled when N/A；Processing：解析中/低置信度/局部失败明确展示。

#### Confirmation / Destructive Actions

N/A。

#### Traceability

- Related Requirements：FR-D02、FR-D03、FR-D04、可解释性 8.1。
- Related APIs：`GET /documents/{document_version_id}/pages/{page_no}`；Source Locator 5.1。
- Related Phase：Phase 7、Phase 9C-12。
- DOCX 逻辑块读取已由 API Contract 9.10 明确；页面不填充虚构页码，使用段落号、表格路径和字符区间展示定位。

### REVIEW-001 Create Review / 创建审核

#### Purpose

选择合法输入版本并创建锁定输入快照的异步审核任务。

#### Users

Org Admin、Reviewer，Write。

#### Route

Frontend Page URL：`/contracts/:contractId/reviews/new`。

#### Entry Points / Exit

- Entry：Contract Detail 或 File Upload success。
- Exit：成功进入 Review Progress；未提交前离开表单返回 Contract Detail。这里的“取消”不取消已创建的任务。

#### Primary User Goal

明确使用哪个文件、规则和模板版本开始审核。

#### Page Layout

Contract Summary、Input Version Form、Locked-input explanation、Submit Actions。

#### Components

Descriptions、Form、Select、Input、Alert、Button、Tag、Skeleton。

#### Displayed Data

合同/文件上下文来自 Contract API；规则与模板选项仅来自其列表/详情 API 中用户可读且已发布的版本。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Create review | Org Admin, Reviewer | Submit | `202 pending`; navigate progress |
| Leave form | Org Admin, Reviewer | Secondary button before submit | Return contract without creating a task |

#### Form

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| 合同文件版本 | Select | Yes | Valid validated file version | `contract_file_id` |
| 文档版本 | Select/automatic | No | Successful parsed version if selected | `document_version_id` |
| 风险规则版本 | Select/automatic | No | Published version; omitted uses organization default | `rule_bundle_version_id` |
| 条款模板版本 | Select/automatic | No | Published version; omitted uses exact contract type + normalized scenario default | `clause_template_version_id` |
| 业务场景 | Text/Select | No | Missing or blank normalizes to `standard`; exact match only | `business_scenario` |

组织、模型密钥、prompt 和结果内容不在表单中。使用 Idempotency-Key；提交中禁用。未指定版本时 UI 明确显示“使用组织默认规则集/匹配场景默认模板”；服务端若无默认返回 409 配置错误，前端显示阻塞原因与配置入口。

#### Page States

Loading：option skeleton；Empty：无合法文件/无发布版本时显示阻塞原因与返回入口；Error：safe retry；Forbidden：writer roles only；Conflict：active review/version unpublished；Disabled：missing required input/submitting/archived contract；Processing：creation accepted后立即转 progress。

#### Confirmation / Destructive Actions

创建前使用确认区域说明输入版本将被锁定；不需要二次 modal，除非 Figma 测试显示误触风险。

#### Traceability

- Related Requirements：FR-D05、FR-E、FR-R、FR-C。
- Related APIs：`POST /contracts/{contract_id}/reviews`, `GET /risk-rule-bundles`, `GET /clause-templates`。
- Related Phase：Phase 9A；P-04/P-05 已关闭。

### REVIEW-002 Review Progress / 审核进度

#### Purpose

展示异步审核任务的服务端事实状态、阶段、进度、失败原因和恢复动作。

#### Users

合同可见用户 Read；Org Admin/Reviewer 可在 failed 时 Retry。

#### Route

Frontend Page URL：`/reviews/:reviewTaskId`。

#### Entry Points / Exit

- Entry：Create Review success、Contract Detail latest review。
- Exit：Review Result、Contract Detail；失败可留页重试。

#### Primary User Goal

知道审核进行到哪里、是否需要操作以及完成后去哪里。

#### Page Layout

```text
Page Header: display_no + status
Progress Summary
+-- Progress value
+-- Current stage
+-- Status message
Stage Runs Timeline (when requested)
Error/Recovery Panel
Primary Next Action
```

#### Components

Progress、Steps/Timeline、Tag、Alert、Descriptions、Button、Skeleton、Result。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `display_no` | 审核编号 | API | Text |
| `status` | 审核状态 | API | Tag/title |
| `progress` | 进度 | API | Progress; state remains authoritative |
| `current_stage` | 当前阶段 | API | Localized text |
| `error_code` | 错误代码 | API | Safe metadata |
| `error_message` | 失败原因 | API | Alert text |
| `stage_runs[].stage` | 阶段 | API | Timeline item |
| `stage_runs[].status` | 阶段状态 | API | Tag |
| `stage_runs[].attempt_no` | 尝试次数 | API | Secondary text |
| `started_at`/`finished_at` | 时间 | API | Local datetime |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Refresh/poll | All allowed | Automatic/manual | GET latest task |
| Retry failed | Org Admin, Reviewer | Retry action | POST retry; task returns pending |
| View result | All allowed | pending_review/completed CTA | `REVIEW-003` |
| Return contract | All allowed | Breadcrumb/button | `CONTRACT-003` |

#### Form

Retry body：`from_stage?` with allowed stages `parsing|classification|extraction|risk_analysis|clause_comparison|report`；recommended default is server-defined first failed stage. Viewer has no form.

#### Page States

状态行为由第 9 节 Review Progress UX 统一定义。页面级 Loading 使用 skeleton；404/403 使用安全结果；retry conflict 保留失败详情；轮询不得在终态继续。

#### Confirmation / Destructive Actions

Retry 会复用锁定输入和成功阶段，可轻量确认；不得提供“改变版本后重试”。取消审核和任务归档未在 API 定义，不展示。

#### Traceability

- Related Requirements：典型业务流程、FR-D05、NFR 8.2/8.4。
- Related APIs：`GET /review-tasks/{review_task_id}`, `POST /review-tasks/{review_task_id}/retry`。
- Related Phase：Phase 9A。

### REVIEW-003 Review Result and Human Review / 审核结果与人工复核

#### Purpose

在一个可追溯工作区中查看分类、字段、风险、条款、证据和预警，并完成授权的人工修订、反馈、审核完成和报告生成。

#### Users

Org Admin、Reviewer：Read/Write；authorized Viewer：Read only；有效平台支持授权：仅业务 JSON GET 只读，禁止下载和写操作。

#### Route

Frontend Page URL：`/reviews/:reviewTaskId/results`。

#### Entry Points / Exit

- Entry：Review Progress、Contract Detail、Warning Detail。
- Exit：Document Preview、Warning Detail、Report、Contract Detail。

#### Primary User Goal

高效理解机器审核结论、核对证据、处理必须人工项并形成可信最终结果。

#### Page Layout

```text
Page Header: Review identity, task status, primary action
Review Summary
Basic Contract Information
Classification
Extracted Fields
Risk Findings
Clause Comparisons
Warnings
Evidence Workspace
Human Revisions and Feedback
Report Actions
```

Recommended UI Decision：桌面宽屏采用“结果主栏 + 可展开证据侧栏/分栏”，而不是把证据放入深层 modal；风险/条款/字段使用 Tabs 或锚点导航，具体方式待高保真原型验证。

#### Components

Descriptions、Tabs/Anchor、Statistic、Table、Tag、Collapse、Drawer/Split Pane、Form、Dialog、Timeline、Alert、Button、Dropdown、Skeleton、Empty。

#### Displayed Data

| 数据组 | API 字段 | 展现方式 |
| --- | --- | --- |
| Summary | `risk_total`, `high`, `medium`, `low`, `warning_total`, `unresolved_count` | Statistics/summary bar |
| Classification | `model_value`, `current_value`, `confidence`, `status`, `evidence`, `version` | Comparison + status |
| Extracted fields | `id`, `field_key`, `model_value`, `current_value`, `status`, `confidence`, `evidence`, `version` | Structured rows |
| Risk findings | `id`, `risk_type`, `severity`, `title`, `description`, `basis`, `suggestion`, `confidence`, `source`, `status`, `evidence`, `version` | Severity-grouped list/table |
| Clause comparisons | `id`, `clause_key`, `status`, `contract_text`, `difference_summary`, `severity`, `suggestion`, `evidence`, `version` | Comparison rows |
| Warnings | Only fields actually returned by result/OpenAPI | Linked warning section; no invented fields |
| Task | `review_task_id`, task `status` | Header/status guard |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Filter results | All allowed | Severity/status filters | GET results with supported Query |
| Open evidence | All allowed | Evidence link | Highlight in `CONTRACT-005`/evidence pane |
| Edit classification/field/risk/clause | Org Admin, Reviewer | Edit action | PATCH with current version |
| Submit feedback | Org Admin, Reviewer | Feedback action | Create feedback fact |
| Open warning | Contract-visible user | Warning link | `WARNING-002` |
| Complete review | Org Admin, Reviewer; pending_review only | Primary action | POST complete after blockers resolved |
| Generate report | Org Admin, Reviewer; pending_review/completed | Report action | POST report and open `REPORT-001` |

#### Form

分类：`current_value`, `status`, optional `reason`, `version`。字段：`current_value`, `status`, optional `reason`, `version`。风险：`status`, optional `title/description/suggestion/reason`, `version`；`severity` 和 `source` 不可编辑。条款：`status`, optional `difference_summary/suggestion/reason`, `version`。反馈：`review_task_id`, `subject_type`, `subject_id`, `label`, `corrected_value` when modified, optional `note`。完成：optional `note`。报告：`format=html|pdf`。

所有写表单提交中禁用；修订成功局部更新并保留 model/current 对照；`409` 不覆盖服务器新版本。现有 API 将 reason 定义为可选，UI 可鼓励填写，但不得当作服务端强制事实。

#### Page States

| State | UI behaviour |
| --- | --- |
| Loading | Section skeletons with stable summary/layout |
| Empty | Per-section empty semantics: no risks is not the same as results not ready; missing fields still render defined keys with null/status |
| Error | Whole-result retry or section-safe error; request ID visible |
| Forbidden | Viewer read-only; unauthorized contract may appear 404 |
| Conflict | Results not ready; revision version conflict; unresolved completion blockers; report already generating |
| Disabled | Editing disabled for viewer, non-pending-review or archived task; complete disabled until server permits |
| Processing | Machine task still processing routes back to progress; report generating tracked separately |

#### Confirmation / Destructive Actions

- Mark risk false positive/processed and change clause status：confirmation in edit form, optional reason per API。
- Complete review：confirmation，说明完成后机器结果仍可追溯；服务端可能拒绝未处理必填项。
- Report generation：format confirmation but not destructive。

#### Traceability

- Related Requirements：FR-D04、FR-E、FR-R、FR-C、FR-RP、FR-F、可解释性 8.1。
- Related APIs：Review Result 10.4-10.9、Feedback 16.1、Report 15.1、Document 9.9、Warning 13.2。
- Related Phase：Phase 9C、10、11、12、13。

### WARNING-001 Warning List / 预警中心

#### Purpose

集中展示当前用户可见预警，支持按真实筛选字段定位待处理和高风险事项。

#### Users

Org Admin、Reviewer：Read/Write entry；authorized Viewer：Read only authorized-contract warnings。

#### Route

Frontend Page URL：`/warnings`。

#### Entry Points / Exit

- Entry：Sidebar、Notification Center、Review Result。
- Exit：Warning Detail、Contract Detail、Review Result。

#### Primary User Goal

快速识别最需要处理的预警并进入处置上下文。

#### Page Layout

```text
Page Header
Summary: unprocessed_count, high_count
Filter Bar
+-- Status, Severity, Contract Type
+-- Assignee, Risk Type, Triggered Time
+-- Sort
Warning Table
Cursor Pagination
```

#### Components

Statistic、Form、Select、DatePicker、Table、Tag、Button/Link、Empty、Skeleton、Pagination。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `id` | 预警 ID | API | Link/reference |
| `contract_id` | 合同 | API | Link by ID; do not invent title |
| `review_task_id` | 审核任务 | API | Link |
| `severity` | 风险等级 | API | Semantic Tag |
| `status` | 处置状态 | API | Status Tag |
| `priority` | 优先级 | API | Text/tag distinct from severity |
| `assignee_id` | 责任人 | API | ID/text |
| `triggered_at` | 触发时间 | API | Local datetime |
| `due_at` | 截止时间 | API when returned | Local datetime/overdue style |
| `summary.unprocessed_count` | 未处理数 | API | Statistic |
| `summary.high_count` | 高风险数 | API | Statistic |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Filter/sort | All allowed | Filter controls | Reload list |
| Open warning | All allowed | Row | `WARNING-002` |
| Open contract/review | All allowed | Context link | Authorized target page |

#### Form

Query only：`status`, `severity`, `contract_type`, `assignee_id`, `risk_type`, `triggered_from`, `triggered_to`, `sort=triggered_at|priority|due_at`, `direction`, `limit`, `cursor`。

#### Page States

Loading：summary/table skeleton；Empty：no warnings vs filters no match；Error：preserve filters/retry；Forbidden：organization/contract scope safe result；Conflict：N/A；Disabled：viewer has no quick-write actions；Processing：background polling may update summary without row shift。

#### Confirmation / Destructive Actions

列表页不执行处置状态变化，避免缺少详情和证据上下文。

#### Traceability

- Related Requirements：FR-W01-W04、FR-RP。
- Related APIs：`GET /api/v1/warnings`。
- Related Phase：Phase 11。

### WARNING-002 Warning Detail / 预警详情

#### Purpose

在证据和完整事件时间线语境中查看并执行合法预警动作。

#### Users

Contract-visible users Read；Org Admin/Reviewer Write；Viewer Read only；Reopen only Org Admin。

#### Route

Frontend Page URL：`/warnings/:warningId`。

#### Entry Points / Exit

- Entry：Warning List、Notification Center、Review Result。
- Exit：Evidence/Document Preview、Review Result、Contract Detail、Warning List。

#### Primary User Goal

理解预警为何产生、谁负责、历史如何变化，并完成下一项合法处置。

#### Page Layout

```text
Page Header: severity, status, primary legal action
Warning Context
+-- Trigger, Contract, Review, Assignee, Due At
Evidence and Related Result
Resolution
Action Panel
Event Timeline
```

#### Components

Descriptions、Tag、Alert、Button/Dropdown、Form、Dialog/Drawer、Timeline、Link、Skeleton、Empty。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `trigger_type` | 触发类型 | API | Text/tag |
| `severity` | 风险等级 | API | Semantic Tag |
| `status` | 状态 | API | Status Tag |
| `risk_finding_id`/related IDs | 关联结果 | API | Link/reference |
| `assignee` | 责任人 | API | User summary when returned |
| `due_at` | 截止时间 | API | Local datetime |
| `resolution` | 关闭结论 | API | Text |
| `evidence[]` | 原文证据 | API | Quote + locator link |
| `events[].event_type` | 事件 | API | Timeline title |
| `events[].from_status/to_status` | 状态变化 | API | Timeline tags |
| `events[].actor_id` | 操作者 | API | ID/text |
| `events[].note` | 说明 | API when returned | Timeline body |
| `events[].created_at` | 时间 | API | Local datetime |

#### Actions

| Action | Role | Available state/condition | Result |
| --- | --- | --- | --- |
| Confirm | Org Admin, Reviewer | `pending_confirmation` | `in_progress` |
| False positive | Org Admin, Reviewer | `pending_confirmation|in_progress` | `ignored`; related risk false positive |
| Ignore | Org Admin, Reviewer | `pending_confirmation|in_progress` | `ignored` |
| Assign | Org Admin, Reviewer | `pending_confirmation|in_progress`; assignee same-org active reviewer | Append event, status unchanged |
| Add note | Org Admin, Reviewer | `pending_confirmation|in_progress`; non-empty note | Append event, status unchanged |
| Resolve | Org Admin, Reviewer | `in_progress` | `resolved` |
| Close | Org Admin, Reviewer | `resolved` | `closed` with resolution/revision |
| Reopen | Org Admin only | `ignored|closed` | `in_progress` |
| Open evidence | All allowed | Evidence exists | Document preview/highlight |

#### Form

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| 动作 | Hidden/menu value | Yes | `warning_event_type` | `type` |
| 说明 | Textarea | Per action/server | String | `note` |
| 责任人 | Select | Assign only | Same-org reviewer UUID | `assignee_id` |
| 截止时间 | DateTimePicker/clear | No | Datetime or null | `due_at` |
| 关闭结论 | Textarea | Close, unless revision | Non-empty | `resolution` |
| 修订记录 | Select/reference | Close alternative | Valid revision UUID | `revision_id` |

提交中禁用当前 action。只显示当前状态可能的动作；服务端仍是最终状态机裁决者。

#### Page States

Loading：detail/timeline skeleton；Empty：no evidence uses explicit “无可用定位” only when contract permits；Error：retry；Forbidden：viewer read-only/unauthorized hidden as 404；Conflict：state changed by another user, refresh latest and discard stale action；Disabled：illegal actions absent/disabled with reason；Processing：event submit locally loading then reload detail。

#### Confirmation / Destructive Actions

- `false_positive`, `ignore`, `close`, `reopen` require confirmation because they change operational meaning。
- `close` requires `resolution` or `revision_id` in form。
- `assign`, `note`, `confirm`, `resolve` use explicit submit but do not require a second dialog unless design testing shows risk。

#### Traceability

- Related Requirements：FR-W、FR-RP、可解释性。
- Related APIs：`GET /warnings/{warning_id}`, `POST /warnings/{warning_id}/events`, Document 9.9。
- Related Phase：Phase 11、Phase 12。

### NOTIFY-001 Notification Center / 通知中心

#### Purpose

展示当前用户的站内通知、未读数量，并引导至关联预警。

#### Users

Authenticated User；只看自己的通知。

#### Route

Recommended UI Decision：Top Header Drawer，无独立 Route；如后续需要深链接，必须先在本 PRD 中记录 Page URL 与 API Route 映射。

#### Entry Points / Exit

- Entry：Header notification icon。
- Exit：Warning Detail；关闭 Drawer 回当前页面。

#### Primary User Goal

快速查看未读预警通知并进入需要关注的事项。

#### Page Layout

Drawer Header + unread count、Unread/Read filter、Notification List、Cursor load more。

#### Components

Drawer、Tabs/Segmented、Badge、List、Button、Empty、Skeleton。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `id` | 通知 ID | API | Internal key |
| `warning_id` | 关联预警 | API | Click target |
| `channel` | 渠道 | API | `in_app` metadata; usually not emphasized |
| `status` | 已读状态 | API | Visual emphasis |
| `title` | 标题 | API | Primary text |
| `body` | 内容 | API | Secondary text |
| `created_at` | 时间 | API | Local relative/absolute time |
| `unread_count` | 未读数 | API | Header Badge |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Filter unread/read | Authenticated user | Filter | Reload notifications |
| Open notification | Owner | Row click | Mark read if needed, open warning |
| Mark read | Owner | Explicit action | Status becomes read |
| Load more | Owner | Footer | Next cursor page |

#### Form

Query：`status=unread|read`, `warning_id`, cursor fields；mark-read body `{}`。没有“全部已读”API，不设计该动作。

#### Page States

Loading：list skeleton；Empty：no notifications per filter；Error：drawer-local retry；Forbidden：session expired routes login；Conflict：N/A；Disabled：read item has no repeat visual action though API is idempotent；Processing：poll unread count, page hidden reduces frequency。

#### Confirmation / Destructive Actions

N/A；标记已读可直接执行。

#### Traceability

- Related Requirements：FR-W03、NFR 5-second perception。
- Related APIs：`GET /notifications`, `POST /notifications/{notification_id}/read`, `GET /notifications/unread-count`。
- Related Phase：Phase 11。

### REPORT-001 Report Status and Viewer / 报告状态与预览

#### Purpose

展示单个不可变报告的生成状态、版本和授权预览/下载入口。

#### Users

Contract-visible users Read/Download；报告创建仅 Org Admin/Reviewer，并从 Review Result 发起；平台支持授权禁止下载。

#### Route

Frontend Page URL：`/reports/:reportId`。

#### Entry Points / Exit

- Entry：Review Result 的生成响应/报告引用。
- Exit：Review Result、inline preview、download。

#### Primary User Goal

确认报告是否就绪，并安全预览或下载对应快照。

#### Page Layout

Page Header + Status、Report Metadata Descriptions、Generation/Error Result、Preview Surface（HTML inline only when ready）、Download Actions。

#### Components

Tag、Descriptions、Result、Alert、Button、Skeleton、iframe/container with CSP constraints handled by response。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `display_no` | 报告编号 | API | Text |
| `review_task_id` | 审核任务 | API | Link |
| `format` | 格式 | API | Tag |
| `status` | 生成状态 | API | Tag/Result |
| `template_version` | 模板版本 | API | Text |
| `generated_at` | 生成时间 | API | Local datetime |
| `download_available` | 可下载 | API | Action gate |
| `error_code` | 错误 | API | Safe error metadata |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Poll status | Contract-visible user | Automatic while generating | GET report |
| Preview inline | Contract-visible user except support grant | Ready HTML action | GET download `disposition=inline` |
| Download | Contract-visible user except support grant | Ready action | GET download `attachment` |
| Return to results | Contract-visible user | Breadcrumb | Review Result |

#### Form

N/A on this page。报告创建的 `format=html|pdf` form 在 Review Result；download Query 仅 `disposition=attachment|inline`。

#### Page States

Loading：metadata skeleton；Empty：N/A；Error：request retry or safe renderer error；Forbidden：no download for support grant/hidden contract；Conflict：report not ready；Disabled：download unavailable；Processing：`generating` polls with backoff and stops on terminal status。

#### Confirmation / Destructive Actions

N/A。重新生成/失败重试不在本页发明按钮，等待 P-06 定义再次 POST 语义。

#### Traceability

- Related Requirements：FR-RP、报告安全与不可变要求。
- Related APIs：`GET /reports/{report_id}`, `GET /reports/{report_id}/download`; creation `POST /review-tasks/{review_task_id}/reports`。
- Related Phase：Phase 13；Pending P-06。
- Pending gap：Phase 13 计划提到历史报告列表，但当前 API 没有按任务/合同列出报告的接口；不设计虚构历史列表。

### RULE-001 Risk Rule Bundle List / 风险规则集

#### Purpose

展示组织风险规则集，允许组织管理员创建规则集，审核员只读已发布内容。

#### Users

Org Admin：Read/Write；Reviewer：published Read only。

#### Route

Frontend Page URL：`/risk-rule-bundles`。

#### Entry Points / Exit

Knowledge Configuration Sidebar；进入 Rule Bundle Detail。

#### Primary User Goal

找到规则集并理解其启停状态和当前发布版本。

#### Page Layout

Page Header + Create、Search/Status Filters、Table、Cursor Pagination、Create Dialog。

#### Components

Input、Select、Table、Tag、Button、Dialog、Form、Empty、Skeleton。

#### Displayed Data

| 字段 | 展示名称 | 来源 | 展现方式 |
| --- | --- | --- | --- |
| `name` | 规则集名称 | API | Link |
| `status` | 状态 | API | Tag |
| `current_published_version_id` | 当前发布版本 | API | Link/empty label |
| `is_default` | 组织默认 | API | Default tag |

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Filter/open | Org Admin, Reviewer | Filter or row | Reload list/open detail |
| Create bundle | Org Admin | Submit create dialog | Create and open detail |
| Switch default | Org Admin | Explicit row/detail action | PATCH `is_default=true`; reload default marker |

#### Form

Create field：`name` required。Create 使用 Idempotency-Key，成功进入 detail；Reviewer 无表单。

#### Page States

Loading：table skeleton；Empty：create CTA for admin/read-only message reviewer；Error：retry；Forbidden：viewer/no membership；Conflict：name conflict/default switch conflict；Disabled：create hidden reviewer；Processing：create/switch actions show loading and disable duplicate submission。

#### Confirmation / Destructive Actions

N/A。

#### Traceability

- Related Requirements：FR-R、配置可维护。
- Related APIs：`GET/POST /risk-rule-bundles`。
- Related Phase：Phase 8A。

### RULE-002 Risk Rule Bundle Detail / 规则集详情与版本

#### Purpose

展示规则集逻辑身份、版本历史和发布信息，并发起草稿、发布前查看或停用。

#### Users

Org Admin：Read/Write；Reviewer：published Read only。

#### Route

Frontend Page URL：`/risk-rule-bundles/:bundleId`。

#### Entry Points / Exit

- Entry：Rule List。
- Exit：Rule Draft Editor、返回列表。

#### Primary User Goal

理解当前发布基线与历史版本，并安全创建下一草稿。

#### Page Layout

Header + status/current version、Bundle Descriptions、Version History Table、optional Rule Preview、Action menu。

#### Components

Descriptions、Table、Tag、Button、Dialog、Form、Alert、Skeleton。

#### Displayed Data

`id`, `name`, `status`, `current_published_version_id`, `is_default`, `versions[].id`, `version_no`, `status`, `change_note`, `effective_at`, `rule_count`，以及 `include_rules=true` 时契约返回的规则。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Edit bundle identity | Org Admin | Edit | PATCH name/status/version |
| Create draft version | Org Admin | Action | POST version then open editor |
| Open version | Org Admin/Reviewer | Version row | Published read-only or draft editor |
| Publish draft | Org Admin | Draft action + confirm | Version becomes published/immutable |
| Disable bundle | Org Admin | Danger action + confirm | Bundle status disabled |
| Switch default | Org Admin | Explicit action + confirm | PATCH `is_default=true`; only active bundle with published version |

#### Form

Bundle：`name?`, `status? active|disabled`, `version`。Create draft：required `change_note`, optional `source_version_id`, required `rules[]`；因 API 要求 `rules` 必填，单纯“复制版本”仍需提交完整规则结构。Reviewer 无表单。

#### Page States

Loading：detail/version skeleton；Empty：no versions with create CTA admin；Error：retry；Forbidden：reviewer draft access rejected；Conflict：version/source/default switch conflict；Disabled：published immutable, disabled bundle state visible；Processing：identity/default/enable/disable actions show loading and disable duplicate submission。

#### Confirmation / Destructive Actions

Disable 和 Publish 必须 confirmation；Publish 明确不可逆编辑且历史任务继续引用旧版本。API 不要求 publish reason，但 draft `change_note` 必填。

#### Traceability

- Related Requirements：FR-R、版本不可变。
- Related APIs：Risk Rule 11.3-11.6、11.8，bundle PATCH 11.4。
- Related Phase：Phase 8A；P-04 已关闭。

### RULE-003 Risk Rule Draft Editor / 规则草稿编辑

#### Purpose

使用白名单结构编辑风险规则草稿并提交乐观锁版本。

#### Users

Org Admin，Write；Reviewer 不可访问 draft。

#### Route

Frontend Page URL：`/risk-rule-bundle-versions/:versionId`。

#### Entry Points / Exit

Rule Bundle Detail；保存/发布后返回 detail 或留在 read-only published view。

#### Primary User Goal

配置可验证的规则条件、等级和建议，不输入任意代码。

#### Page Layout

Draft Header + version/status、Change Note、Rule Table/Accordion、Rule Editor Drawer、Validation Summary、Sticky Save/Publish Actions。

#### Components

Form、Table、Collapse、Drawer、Select、Input、Textarea、Switch、Alert、Button。

#### Displayed Data

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| 变更说明 | Textarea | Required on create; optional update | String | `change_note` |
| 规则键 | Input | Yes | Unique in version | `rule_key` |
| 风险类型 | Input/Select | Yes | Server schema | `risk_type` |
| 引擎 | Segmented/Select | Yes | `deterministic|model` | `engine` |
| 条件 | Structured rule builder | Yes | Whitelisted operator schema only | `condition` |
| 严重度 | Select | Yes | `high|medium|low` | `severity` |
| 建议 | Textarea | Yes per RiskRule schema | Server schema | `suggestion` |
| 启用 | Switch | Yes | Boolean | `enabled` |
| 资源版本 | Hidden | Yes on PATCH | Latest integer | `version` |

列表与编辑器显示上述规则字段、草稿状态和资源版本。

条件编辑器必须按操作符提供封闭选择：关键词/正则只能选择 `contract_text`；金额阈值只能选择 `contract_amount`；日期阈值只能选择 `signing_date`；字段存在/缺失只能选择 `parties`, `signing_date`, `contract_amount`, `performance_period`, `dispute_resolution`, `payment_terms`, `auto_renewal`, `acceptance_standard`, `intellectual_property`, `data_compliance`, `force_majeure`；逻辑组合仅为 `all/any/not`，最多 5 层且每个 `all/any` 有 1-20 个子条件；`semantic` 仅在 `engine=model` 时可用。页面不得提供任意 JSON、Python、SQL 或表达式输入框。

#### Form

字段、校验和 API 映射见上表；PATCH 提交 `rules?`, `change_note?`, `version`。

#### Actions

Add/edit/remove rule in local draft array；Save PATCH；Publish through publish endpoint after server validation；cancel/leave with unsaved confirmation。

#### Page States

Loading：editor skeleton；Empty：draft with zero local rules only if server schema permits, otherwise validation blocker；Error：field/condition errors；Forbidden：org admin only；Conflict：reload latest draft, never overwrite；Disabled：published version entire editor read-only；Processing：save/publish loading。

#### Confirmation / Destructive Actions

Remove local rule requires confirmation if populated；Publish requires irreversible confirmation；disabling a rule is not deletion but should be visually explicit。

#### Traceability

- Related Requirements：FR-R、规则+模型组合策略。
- Related APIs：`GET/PATCH /risk-rule-bundle-versions/{version_id}`, `POST .../{version_id}/publish`。
- Related Phase：Phase 8A。

### CLAUSE-001 Clause Template List / 条款模板列表

#### Purpose

按合同类型、业务场景和状态查找标准条款模板，并允许组织管理员创建模板。

#### Users

Org Admin：Read/Write；Reviewer：published Read only。

#### Route

Frontend Page URL：`/clause-templates`。

#### Entry Points / Exit

Knowledge Configuration Sidebar；进入 Template Detail。

#### Primary User Goal

定位适用模板并查看当前发布版本。

#### Page Layout

Page Header + Create、Filters (`q`, contract type, scenario, status)、Table、Cursor Pagination、Create Dialog。

#### Components

Input、Select、Table、Tag、Dialog、Form、Empty、Skeleton。

#### Displayed Data

`name`, `contract_type`, `business_scenario`, `current_published_version_id`, `is_default`, `status`，均来自 API。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Filter/open | Org Admin, Reviewer | Filter or row | Reload list/open detail |
| Create template | Org Admin | Submit create dialog | Create and open detail |
| Switch default | Org Admin | Explicit row/detail action | PATCH `is_default=true`; reload scoped default marker |

#### Form

Create fields：`name` required、`contract_type` required and not `other`、`business_scenario` optional。使用 Idempotency-Key；Reviewer 无表单。

#### Page States

Loading：table skeleton；Empty：create CTA/read-only empty；Error：retry；Forbidden：viewer；Conflict：template name/default switch conflict；Disabled：create hidden reviewer；Processing：N/A。

#### Confirmation / Destructive Actions

N/A。

#### Traceability

- Related Requirements：FR-C。
- Related APIs：`GET/POST /clause-templates`。
- Related Phase：Phase 8B。

### CLAUSE-002 Clause Template Detail / 模板详情与版本

#### Purpose

查看模板逻辑身份、版本历史和标准条款，并创建/发布/停用版本。

#### Users

Org Admin：Read/Write；Reviewer：published Read only。

#### Route

Frontend Page URL：`/clause-templates/:templateId`。

#### Entry Points / Exit

Template List；进入 Draft Editor 或返回列表。

#### Primary User Goal

理解模板适用范围和当前发布条款，并维护下一版本。

#### Page Layout

Header + status/current version、Template Descriptions、Version History、Clause Preview Table、Actions。

#### Components

Descriptions、Table、Tag、Button、Dialog、Alert、Skeleton。

#### Displayed Data

`id`, `name`, `contract_type`, `business_scenario` (blank normalized to `standard`), `status`, `current_published_version_id`, `is_default`, `versions[].id/version_no/status/change_note/effective_at`, optional `clauses[].clause_key/name/severity/enabled`。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Open version | Org Admin, Reviewer | Version row | Open allowed version |
| Edit identity | Org Admin | Edit | PATCH template identity |
| Create draft | Org Admin | Action | Create draft version |
| Publish draft | Org Admin | Confirm publish | Make version immutable |
| Disable template | Org Admin | Danger action | Set template disabled |
| Switch default | Org Admin | Explicit action + confirm | PATCH `is_default=true`; only active template with published version in the same exact scope |

#### Form

Edit identity：`name?`, `business_scenario?`, `status? active|disabled`, `version`。Create draft：`change_note`, optional `source_version_id`, required `clauses[]`。Reviewer 无表单且只打开已发布版本。

#### Page States

Loading：detail skeleton；Empty：no versions/clauses；Error：retry；Forbidden：reviewer draft access；Conflict：version/source/default switch conflict；Disabled：disabled template unavailable for new default but history readable；Processing：N/A。

#### Confirmation / Destructive Actions

Disable and Publish require confirmation；Publish states immutable/history unaffected。`change_note` required for draft creation。

#### Traceability

- Related Requirements：FR-C01-C04。
- Related APIs：Clause Template 12.3-12.6、12.8，template PATCH 12.4。
- Related Phase：Phase 8B；P-05 已关闭。

### CLAUSE-003 Clause Template Draft Editor / 模板草稿编辑

#### Purpose

编辑结构化标准条款草稿，并通过版本锁和 Schema 校验后发布。

#### Users

Org Admin，Write。

#### Route

Frontend Page URL：`/clause-templates/:templateId/versions/:versionId`。

#### Entry Points / Exit

Template Detail；保存/发布后返回 detail 或只读 published view。

#### Primary User Goal

维护条款文本、允许偏差、适用条件、风险等级和建议的有序版本。

#### Page Layout

Draft Header、Change Note、Ordered Clause Table、Clause Editor Drawer、Validation Summary、Save/Publish Actions。

#### Components

Table、Form、Drawer、Input、Textarea、Select、Switch、InputNumber、Alert、Button。

#### Displayed Data

| Field | Type | Required | Validation | API Field |
| --- | --- | --- | --- | --- |
| 变更说明 | Textarea | Required on create | String | `change_note` |
| 条款键 | Input | Yes | Unique in version | `clause_key` |
| 条款名称 | Input | Yes | Non-empty | `name` |
| 标准文本 | Textarea | Yes | Server length/schema | `standard_text` |
| 允许偏差 | Textarea | Yes by StandardClause shape | String | `allowed_deviation` |
| 严重度 | Select | Yes | `high|medium|low` | `severity` |
| 适用条件 | Structured form | Yes | Schema object; no arbitrary code | `applicability` |
| 建议文本 | Textarea | Yes by StandardClause shape | String | `suggestion` |
| 启用 | Switch | Yes | Boolean | `enabled` |
| 顺序 | InputNumber/reorder control | Yes | Integer | `order_no` |
| 资源版本 | Hidden | Yes on PATCH | Latest integer | `version` |

列表与编辑器显示上述条款字段、草稿状态和资源版本。

#### Form

字段、校验和 API 映射见上表；PATCH 提交 `clauses?`, `change_note?`, `version`。

#### Actions

Add/edit/remove/reorder local clauses；Save PATCH；Publish endpoint；leave with unsaved confirmation。

#### Page States

Loading：editor skeleton；Empty：no clauses with validation guidance；Error：field/schema errors；Forbidden：org admin only；Conflict：reload latest draft；Disabled：published version read-only；Processing：save/publish loading。

#### Confirmation / Destructive Actions

Remove clause and Publish require confirmation；published content cannot be edited or deleted。

#### Traceability

- Related Requirements：FR-C、标准条款版本要求。
- Related APIs：`GET/PATCH /clause-template-versions/{version_id}`, `POST .../{version_id}/publish`。
- Related Phase：Phase 8B。

### ADMIN-001 Organization Audit Log / 组织审计

#### Purpose

让组织管理员查询本组织只读审计事实和安全变更摘要。

#### Users

Org Admin，Read only。

#### Route

Frontend Page URL：`/audit-logs`。

#### Entry Points / Exit

Organization Administration Sidebar；可从安全摘要返回相关模块，但不得越权深链。

#### Primary User Goal

按动作、资源、操作者和时间追查关键业务操作。

#### Page Layout

Filter Bar、Audit Table、Safe Summary Drawer、Cursor Pagination。

#### Components

Select、DateTimePicker、Table、Drawer、Descriptions、Empty、Skeleton。

#### Displayed Data

`id`, `action`, `resource_type`, `resource_id`, `actor_id`, `request_id`, `created_at`, `before_summary`, `after_summary`。摘要不得显示合同正文、密码、Cookie、令牌、密钥、完整 prompt 或原始模型响应。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Apply filters | Org Admin | Filter change/submit | Reload audit list |
| View safe summary | Org Admin | Row action | Open read-only Drawer |
| Copy request ID | Org Admin | Copy action | Copy displayed ID only |

#### Form

Query fields：`action`, `resource_type`, `actor_id`, `created_from`, `created_to`, `sort=created_at`, cursor fields；无修改、删除或导出。

#### Page States

Loading：table skeleton；Empty：no events/filter no match；Error：retry；Forbidden：org admin only；Conflict：N/A；Disabled：invalid date range；Processing：N/A。

#### Confirmation / Destructive Actions

N/A。

#### Traceability

- Related Requirements：FR-A04。
- Related APIs：`GET /api/v1/audit-logs`。
- Related Phase：Phase 14A。

### ADMIN-002 Operations Metrics / 运营指标

#### Purpose

展示契约定义的审核与预警聚合指标，帮助组织管理员识别运行趋势和失败情况。

#### Users

Org Admin，Read only；Phase 14A/第三阶段启用。

#### Route

Frontend Page URL：`/organizations/:organizationId/metrics`。

#### Entry Points / Exit

Organization Administration Sidebar；可进入筛选后的 Warning List，其他 drill-down 仅在现有页面筛选支持时提供。

#### Primary User Goal

在指定时间范围理解审核量、失败率、人工编辑和预警处置表现。

#### Page Layout

Date Range + domain filters、Review Metrics section、Warning Metrics section、risk type breakdown table。图表为可选原型表达，但只能使用契约字段。

#### Components

DatePicker、Select、Statistic、Table、Alert、Skeleton、Empty。

#### Displayed Data

Review：`review_count`, `completed_count`, `failed_count`, `average_duration_ms`, `parse_failure_rate`, `model_failure_rate`, `manual_edit_rate`。Warning：`created_count`, `unprocessed_count`, `closed_count`, `closure_rate`, `false_positive_rate`, `average_unprocessed_duration_ms`, `by_risk_type[].risk_type/count`。共同显示 `from`, `to`。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Apply date/domain filters | Org Admin | Submit filters | Reload review/warning metrics |
| Clear optional filters | Org Admin | Clear | Return to selected date range |

#### Form

Required `from`, `to`；Review optional `contract_type`；Warning optional `risk_type`, `severity`。Apply filters reloads both applicable endpoints；无导出 API。

#### Page States

Loading：metric skeletons；Empty：valid range no facts；Error：endpoint-local retry；Forbidden：org admin only；Conflict：N/A；Disabled：invalid/missing date range；Processing：N/A；`501 METRICS_NOT_ENABLED` 展示“运营指标尚未启用”，不是系统错误。

#### Confirmation / Destructive Actions

N/A。

#### Traceability

- Related Requirements：FR-O、NFR performance/operations。
- Related APIs：`GET /organizations/{organization_id}/metrics/reviews`, `GET .../metrics/warnings`。
- Related Phase：Phase 14A。

### ADMIN-003 Feedback Summary / 反馈统计

#### Purpose

让组织管理员按合同类型和版本维度查看审核反馈聚合。

#### Users

Org Admin，Read only；反馈提交入口在 Review Result，Org Admin/Reviewer 可写。

#### Route

Frontend Page URL：`/feedback/summary`。

#### Entry Points / Exit

Organization Administration Sidebar；可返回 Review Result 提交单条反馈，但统计响应不提供具体 subject 列表。

#### Primary User Goal

了解正确、错误、修改和忽略反馈的数量及风险类型分布。

#### Page Layout

Filter Bar、Feedback Count Statistics、Risk Type Breakdown Table、Empty/Alert。

#### Components

Select、DatePicker、Statistic、Table、Skeleton。

#### Displayed Data

`filters`, `counts.correct`, `counts.incorrect`, `counts.modified`, `counts.ignored`, `by_risk_type[].risk_type/incorrect/modified`。不得自行推算未定义的准确率或“AI 得分”。

#### Actions

| Action | Role | Trigger | Result |
| --- | --- | --- | --- |
| Apply filters | Org Admin | Submit filters | Reload feedback summary |
| Clear filters | Org Admin | Clear | Reload unfiltered summary |

#### Form

Query：`contract_type?`, `rule_bundle_version_id?`, `model_version?`, `created_from?`, `created_to?`；无分页、导出或删除。

#### Page States

Loading：statistics skeleton；Empty：no feedback in range；Error：retry；Forbidden：org admin only；Conflict：N/A；Disabled：invalid date range；Processing：N/A。

#### Confirmation / Destructive Actions

N/A。

#### Traceability

- Related Requirements：FR-F、FR-O。
- Related APIs：`GET /api/v1/feedback/summary`; write source `POST /api/v1/feedback`。
- Related Phase：Phase 12、Phase 14A contextual use。

## 9. Review Progress UX

### 9.1 Status Vocabulary

前端只使用 API `review_status`：`pending`, `parsing`, `reviewing`, `pending_review`, `completed`, `failed`, `archived`。`queued` 是示例中的 `current_stage`，不是任务状态；API 没有 `processing` 状态，UI 不创建该枚举。

### 9.2 Status Presentation Matrix

| `status` | 状态标题 | Tag 语义 | Progress / 当前阶段 | 可执行操作 | 轮询 | 下一步 CTA |
| --- | --- | --- | --- | --- | --- | --- |
| `pending` | 等待处理 | Info/Neutral | 展示 API `progress`; `current_stage` 可为 queued | 查看合同；无取消 | 2 秒起始并退避 | 等待系统开始 |
| `parsing` | 正在解析合同 | Info | 展示 API `progress` 和真实 `current_stage` | 查看已完成阶段；无手工推进 | 是；页面隐藏降频 | 等待解析完成 |
| `reviewing` | 正在执行审核 | Primary/Info | 展示 API `progress` 和真实阶段 | 查看阶段运行；无结果编辑 | 是；页面隐藏降频 | 等待机器审核完成 |
| `pending_review` | 等待人工复核 | Warning | `progress` 可为 100，但状态是事实 | 查看结果；Org Admin/Reviewer 开始复核 | 停止任务轮询；通知可独立轮询 | 查看审核结果 |
| `completed` | 审核已完成 | Success | 展示完成时间；不再动画 | 查看结果、生成报告；重新审核需新任务 | 停止 | 查看结果/报告 |
| `failed` | 审核失败 | Danger | 保留最后 `progress`, `current_stage`, safe error | Org Admin/Reviewer retry；Viewer 只读 | 停止 | 重试或返回合同 |
| `archived` | 审核已归档 | Neutral | 只读历史状态 | 查看历史结果（若可用） | 停止 | 返回合同 |

### 9.3 Polling Rules

- 调用 `GET /review-tasks/{id}`；前台建议 2 秒起始，随后退避，满足 5 秒感知目标。
- 页面不可见时降低频率；恢复可见后立即获取一次最新状态。
- `pending_review`, `completed`, `failed`, `archived` 停止任务轮询。
- 网络错误不把任务标为 failed；保留最近一次服务器状态，显示连接错误和手动重试。
- 同一个页面只维持一个有效轮询；路由离开时取消。

### 9.4 Failure and Retry

- 显示 `error_message` 为主要文案，`error_code` 与 request/task ID 为支持信息；不得显示内部异常。
- Retry 只允许 Org Admin/Reviewer 且任务为 `failed`。默认从服务端认定的第一个失败阶段恢复；手工 `from_stage` 只使用契约白名单。
- Retry 使用 Idempotency-Key；成功后状态回到 `pending`，页面重新进入轮询。
- `INPUT_VERSION_CHANGED`、并发上限或非法状态时保持当前失败详情，并给出返回合同/稍后重试路径。
- UI 不提供取消任务、归档任务、改变锁定版本或“强制完成”。

## 10. Review Result UX

### 10.1 Information Hierarchy

1. Review Summary：任务状态、风险总数、高/中/低、预警总数、未处理数。
2. Basic Contract Information：从合同和审核上下文展示合同编号、名称、声明类型、文件/审核引用；只显示实际响应字段。
3. Classification：机器分类、当前分类、状态、置信度和证据。
4. Extracted Fields：七个契约字段键的机器值、当前值、状态、置信度和证据。
5. Risk Findings：按严重度和状态扫描风险，突出依据与建议。
6. Clause Comparison：匹配、偏差、缺失、无法判断，展示合同文本、差异和建议。
7. Warnings：链接到预警详情和处置时间线；不把预警与风险列表混为同一状态机。
8. Evidence：与当前选中结果联动的原文上下文。
9. Human Revisions and Feedback：原值/当前值、本次会话修订记录、反馈表单；完整历史不由前端假造。
10. Report：选择格式、生成状态、预览/下载入口。

### 10.2 Risk Presentation

每条风险展示：

- `severity`：高/中/低，使用颜色 + 文本 + 图标/形状，不只依赖颜色。
- `status`：待复核/已确认/误报/已处理，与 severity 分列显示。
- `source`：规则/模型原始来源；人工动作通过 `edited_by`、`edited_at` 和本次会话修订记录呈现，不把原始来源改为人工。
- `title`, `description`, `basis`, `suggestion`：标题优先，依据与建议清楚分区。
- `confidence`：仅当 API 返回时显示为数值或辅助 meter；不改写为 `risk_score`，不用于重新排序业务优先级。
- `evidence[]`：显示 quote、定位类型和跳转入口；confirmed 风险必须有证据。

默认可按 `risk_severity` 和 `risk_status` 过滤。排序默认遵循 API 全局规则，除非后续契约声明结果内排序；UI 不擅自宣称严重度排序是业务事实。

### 10.3 Extracted Field Presentation

- 固定使用 API 字段键：`parties`, `signing_date`, `contract_amount`, `performance_period`, `dispute_resolution`, `payment_terms`, `auto_renewal`。
- `current_value=null` 必须结合 `status=not_found|needs_confirmation` 展示为明确业务状态，而不是空白或 `--`。
- 金额使用 `{amount, currency, tax_included}` 的结构化展示，不将字符串金额转为浮点再展示。
- 同时显示 model/current，修改后不隐藏机器原值。
- `detected` 是公共结果状态中的已识别值；不使用并列的 `found` 状态。缺失字段按 `not_found|needs_confirmation` 展示。

### 10.4 Clause Comparison Presentation

- `matched`：匹配；`deviated`：存在偏差；`missing`：缺失；`uncertain`：无法判断。
- 展示 `contract_text`, `difference_summary`, `severity`, `suggestion` 和证据。
- `missing` 可以没有定位，此时明确展示“合同中未定位到对应条款”，不能生成虚假证据。
- `uncertain` 必须保持人工复核提示，不能用绿色“通过”样式。

### 10.5 Evidence Interaction

| Locator kind | 用户点击后的行为 |
| --- | --- |
| `pdf_page` | 打开对应 `page_no`，滚动并高亮 `bbox`/字符区间，旁边保留 quote |
| `image_page` | 打开对应图片页并高亮 `bbox`，提供缩放/适配图标按钮 |
| `docx_paragraph` | 打开对应段落，按 `paragraph_no` 与 offset 高亮；不显示页码 |
| `docx_table_cell` | 打开 `table_path` 对应单元格并按 offset 高亮；不显示页码 |

- 证据面板保持当前选中结果，用户可以返回结果而不丢失筛选和滚动位置。
- 多证据按 API 顺序列出并允许切换；不要只保留主证据而隐藏其他证据。
- Locator 失效或文档未就绪时显示安全错误，不把 quote 当作完整文档替代品。

### 10.6 Result-Level Actions

- `pending_review`：Org Admin/Reviewer 可修订、反馈、处理预警并尝试完成；Viewer 只读。
- `completed`：默认只读结果，可生成新报告；是否仍允许结果 PATCH 必须以后端状态校验为准，UI 不自行放开。
- `archived`：只读。
- `failed` 或 `RESULTS_NOT_READY`：引导 Review Progress，不展示空的“无风险”成功态。

## 11. Human Review UX

### 11.1 Editable Boundaries

| Subject | 可编辑 | 只读/不可改 | API requirement |
| --- | --- | --- | --- |
| Classification | `current_value`, allowed `status`, optional `reason` | model value, confidence, evidence source | `version` required |
| Extracted Field | `current_value`, `status`, optional `reason` | model value, `field_key`, confidence | current value must match field JSON Schema; `version` required |
| Risk Finding | `status`, optional title/description/suggestion/reason | severity, model source, evidence identity | confirmed requires evidence; `version` required |
| Clause Comparison | `status`, optional difference summary/suggestion/reason | locked template/version context | uncertain cannot be silently passed; `version` required |
| Feedback | label, corrected value when modified, optional note | subject ownership/task organization | creates append-only feedback |

### 11.2 Editing Pattern

- 从结果项进入 Drawer 或 inline edit region，顶部固定展示机器原值，编辑区展示当前值。
- 结构化字段使用针对 `field_key` 的表单，而不是任意 JSON 文本框；具体子字段必须来自后端生成的 OpenAPI/Schema，不在本 PRD补造。
- 修改记录在当前 API 示例中没有独立读取接口。页面可展示本次会话产生的变更，但不能声称拥有完整历史列表；完整 revision read contract 需要后续确认。
- `reason` 在现有修订 API 中可选。视觉上鼓励风险/条款语义变化填写原因，但不将其标为服务端必填。
- Feedback 与 revision 是不同事实：修改结果不自动等于提交 feedback，除非后端契约未来明确联动。

### 11.3 Version Conflict

1. 用户提交携带当前 `version`。
2. 收到 `409 RESOURCE_VERSION_CONFLICT` 后停止成功提示，不重放旧写入。
3. 获取最新结果资源。
4. 并列显示“服务器最新值”和“你的未提交修改”。
5. 用户选择放弃本地修改或基于新版本重新应用并再次提交。

不得静默覆盖、自动合并复杂结构或仅更新隐藏 version 后重试。

### 11.4 Complete Review

- 只在任务 `pending_review` 且角色允许时显示主操作。
- 在确认区域展示 `summary.unresolved_count` 和服务端已知阻塞结果；不得由前端单独决定所有业务阻塞条件。
- 可提交 optional `note`。
- `UNRESOLVED_REQUIRED_FINDINGS` 时保持页面和编辑上下文，展示服务端错误并引导到未处理项。
- 成功后状态变为 `completed`，结果转为完成态展示，并突出生成报告 CTA。

## 12. Warning Center UX

### 12.1 Status and Action Matrix

| Current status | Confirm | False Positive | Ignore | Assign | Note | Resolve | Close | Reopen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `pending_confirmation` | Org Admin/Reviewer | Org Admin/Reviewer | Org Admin/Reviewer | Org Admin/Reviewer | Org Admin/Reviewer | No | No | No |
| `in_progress` | No | Org Admin/Reviewer | Org Admin/Reviewer | Org Admin/Reviewer | Org Admin/Reviewer | Org Admin/Reviewer | No | No |
| `ignored` | No | No | No | No; reopen first | No; reopen first | No | No | Org Admin only |
| `resolved` | No | No | No | No; reopen first | No; reopen first | No | Org Admin/Reviewer | No |
| `closed` | No | No | No | No | Read-only history | No | No | Org Admin only |

契约明确 `assign` 和 `note` 只在 `pending_confirmation`、`in_progress` 活动状态合法，且不改变主状态；`ignored`、`resolved`、`closed` 只读，需先执行合法的重新打开动作再追加说明或分派。Phase 11 contract tests 必须覆盖这两个事件在每个状态的允许/拒绝矩阵。

### 12.2 Filters and Scanning

- 状态、严重度、合同类型、责任人、风险类型、触发时间为独立筛选项。
- 摘要只显示 API 的 `unprocessed_count` 和 `high_count`；不推导 SLA、逾期数量或风险总分。
- Severity 与 priority 分开呈现，避免用户把两者视为同一字段。
- Viewer 看到同样的信息层级但没有处置控件。

### 12.3 Timeline

- 每个事件显示事件类型、from/to 状态、操作者、时间和 API 返回的 note/metadata。
- Created 事件无 actor 时显示“系统触发”，不虚构用户。
- Assign 和 Note 事件仍进入时间线，即便主状态没有变化。
- Timeline 不允许编辑或删除。

### 12.4 Evidence and Cross-Navigation

- Warning Detail 的 evidence 复用 Review Result/Document Preview 定位规则。
- 风险/条款/字段/分类至少有一种关联；UI 根据实际返回 ID 提供关联入口。
- 从证据返回时保留 warning timeline 和表单状态；从 Notification 进入后标记通知已读不改变 warning 状态。

## 13. Administration UX

| Module | Primary users | List/read | Edit/actions | Important state |
| --- | --- | --- | --- | --- |
| Platform Organizations | Platform Admin | Organization list/detail | Create, update, disable/enable | Version conflict, disabled organization |
| Organization Settings | Org Admin | Current non-secret settings | Update whitelisted fields | Version conflict, retention confirmation |
| Members/Invitations | Org Admin | Members and delivery status | Invite, resend, role/status update | Pending invitation, last admin protection |
| Support Access | Org Admin | Active/history grants | Grant <=4h, revoke | Active/expired/revoked, no write/download |
| Model Configuration | Platform Admin | Provider/model/secret status | Timeout, retries, tracking, status | Secret not configured; no secret input |
| Risk Rules | Org Admin write; Reviewer published read | Bundles/version history/rules | Draft, edit, publish, disable | Draft/published/disabled, immutable publish |
| Clause Templates | Org Admin write; Reviewer published read | Templates/version history/clauses | Draft, edit, publish, disable | Draft/published/disabled, immutable publish |
| Organization Audit | Org Admin read | Filtered append-only facts | None | Safe summaries only |
| Platform Audit | Platform Admin read | Cross-org filtered facts | None | Safe summaries only |
| Operations | Org Admin read | Review/warning metrics | Filters only | `501 METRICS_NOT_ENABLED` |
| Feedback Summary | Org Admin read | Aggregated counts | Filters only | No invented accuracy score |

Administration 页面遵循一致模式：左侧/顶部明确管理范围，列表优先，编辑使用经过 Schema 限制的 Form，危险动作确认，发布版本不可编辑，Secret 永不显示。

## 14. Global UI States

### 14.1 Loading

- 首次加载使用 Skeleton，尺寸与最终组件一致，避免布局跳动。
- 表单提交使用局部 loading；不阻塞无关只读区域。
- 后台刷新保留旧数据并显示轻量 refreshing；不清空表格。

### 14.2 Empty

- 区分“系统尚无数据”和“当前筛选无结果”。
- 写角色可看到与当前 Phase/权限合法的 CTA；只读角色只显示说明和返回路径。
- Review Result 的空风险不能与 `RESULTS_NOT_READY` 混淆。

### 14.3 Error

- 展示 API `message` 和可复制 `request_id`，不展示堆栈、SQL、路径、密钥、合同正文或供应商原始响应。
- 字段错误靠近字段；页面错误使用 Alert/Result；异步业务失败使用对应资源状态，而不是通用 toast 替代。
- Retry 只在操作安全且契约允许时出现。

### 14.4 Forbidden and Not Found

- `401`：会话失效，进入登录并保留安全 return target。
- `403`：展示无权限结果和可用导航。
- 为防枚举返回的 `404`：使用统一“资源不存在或不可访问”，不显示组织/资源细节。
- Platform support context 始终显示只读标识，隐藏写和下载入口。

### 14.5 Conflict

- `RESOURCE_VERSION_CONFLICT`：刷新、对比、重新编辑，不自动覆盖。
- `IDEMPOTENCY_KEY_REUSED`：提示请求无法重复使用，生成新键只用于用户明确发起的新请求。
- `INVALID_STATE_TRANSITION`：刷新资源状态并重新计算合法动作。
- `ACTIVE_REVIEW_EXISTS`：引导现有任务。
- 名称/成员/活动授权冲突：保留表单输入，显示具体安全错误。

### 14.6 Disabled

- 同时说明“为什么不可操作”和“下一步是什么”，但不暴露用户无权知道的信息。
- 角色无权的危险动作优先不渲染；状态暂时不允许的动作可禁用并给出 Tooltip。
- 归档、发布、禁用、生成中等资源状态不会改变页面主要布局。

### 14.7 Processing

- 审核、报告、上传分别使用各自真实状态；不要用一个全局“AI处理中”替代。
- 轮询有明确终止条件和页面隐藏降频。
- 浏览器上传进度、Worker 业务进度和报告生成状态不得混为一个百分比。

## 15. Visual Design Direction

产品类型：企业级 AI 合同智能审核后台 SaaS / Enterprise Web Application。

### 15.1 Desired Qualities

- Professional、Clean、Reliable、Modern、Enterprise。
- AI-enabled but not overly futuristic：AI 是审核能力，不是视觉噱头。
- Data-heavy but readable：支持高密度扫描，但保留清晰分组、行高和次级信息层级。
- 证据优先：风险结论与原文证据在视觉上建立明确关联。
- 状态可信：任务、风险、条款、预警和报告使用各自独立且一致的状态语义。

### 15.2 Avoid

- 过度赛博朋克、霓虹、游戏 UI、大量渐变、大面积装饰和营销网站式 hero。
- 把后台 section 全部做成浮动卡片，或在卡片中嵌套卡片。
- 用巨大标题压缩数据空间；用同一种蓝紫色表达所有状态。
- 用机器人、星光、发光球体等装饰替代真实合同、风险和证据内容。

### 15.3 Visual Focus

1. 合同与审核上下文始终清楚。
2. 高/中/低风险明显但不过度警报化。
3. 机器原值、当前值、人工修订和证据可比较。
4. 数据表格具有稳定列、清晰对齐和可扫描状态。
5. 危险动作与日常操作有明确层级。

## 16. Design System Direction

### 16.1 Layout

- Desktop-first，Sidebar + Top Header + Main Content。
- 数据列表和审核工作区优先使用可用宽度；表单/纯文本内容设置合理 max-width，但不把所有页面收窄为居中卡片。
- 使用一致 spacing scale；页面标题、筛选、内容和分页位置稳定。
- 审核结果与证据使用响应式分栏约束，避免结果或高亮互相遮挡。

### 16.2 Typography

- Page Title：页面级，清晰但克制。
- Section Title：区分结果模块和管理分区。
- Body：业务说明与表单值。
- Secondary Text：ID、版本、时间、辅助状态和 request ID。
- Table Text：紧凑可读，数值、时间和状态列对齐一致。
- 不在此 PRD 固定具体字体；遵循中文桌面系统可读性和现有前端字体栈。

### 16.3 Color Semantics

| Semantic | Usage |
| --- | --- |
| Primary | 当前主操作、选中导航、可信交互焦点 |
| Success | 完成、已解决、匹配、已发布等成功事实 |
| Warning | 待复核、中风险、低置信度、即将到期等需注意状态 |
| Danger | 高风险、失败、禁用、破坏性操作 |
| Info | 处理中、说明、规则/模型来源等信息状态 |
| Neutral | 归档、只读、未分配、次级元数据 |

风险等级、状态和可操作性不能只靠颜色区分；同时使用文字、图标或形状。不要在 PRD 中锁定大量 Hex，具体 Token 在视觉设计阶段建立。

### 16.4 Interaction and Motion

- 表格筛选、Drawer、Dialog 和证据定位使用短促、功能性过渡。
- 不给 processing 状态使用持续干扰的装饰动画；优先 Progress/Skeleton 和状态文本。
- Hover 不改变元素尺寸；工具图标有 Tooltip 和稳定点击区域。

### 16.5 Element Plus Usage

优先映射现有 Element Plus pattern：

| Need | Preferred Element Plus pattern |
| --- | --- |
| Data list | Table + Pagination/Load more |
| Structured input | Form + Input/Select/InputNumber/DatePicker/Switch/Checkbox |
| Resource summary | Descriptions / Statistic |
| Status | Tag + Alert/Result where needed |
| Secondary edit | Drawer |
| Confirmation / compact create | Dialog |
| Subviews | Tabs only when content hierarchy benefits |
| Async placeholder | Skeleton |
| No data | Empty |
| Historical events | Timeline |
| Secondary commands | Dropdown |
| Upload | Upload + Progress + required acknowledgement |

Element Plus 是实现基础，不限制后续 Token、排版和组合方式。避免把每个内容区都做成 Card；Card 仅用于真正独立的重复实体或工具区域。

## 17. Responsive Strategy

### 17.1 Primary Viewports

- 主要高保真原型：1440px 宽桌面。
- 必须验证：1280px 宽桌面完整可操作。
- 不设计独立 Mobile App；窄屏只提供基本保护。

### 17.2 Behaviour

- Sidebar 可折叠，但关键导航文本在展开态可见；折叠图标必须有 Tooltip。
- 1280px 下审核结果/证据分栏可调整比例或将证据改为 Drawer；不得遮挡操作和正文。
- 宽表格优先允许水平滚动和固定关键列，不压缩到文本不可读。
- Header 操作过多时保留一个主按钮，其余进入 Dropdown。
- Dialog/Drawer 使用 viewport 约束，长表单内部可滚动，提交区保持可达。
- 小于产品支持宽度时显示可用的窄屏布局或提示使用桌面，不出现元素重叠、裁切关键按钮或正文溢出。

## 18. Prototype Priority

### 18.1 Prototype P0

最先设计，覆盖核心合同审核闭环：

1. `LAYOUT-001` Authenticated Application Shell
2. `AUTH-001` Login
3. `CONTRACT-001` Contract List
4. `CONTRACT-002` Create Contract
5. `CONTRACT-003` Contract Detail
6. `CONTRACT-004` File Upload and Versions
7. `CONTRACT-005` Document Preview
8. `REVIEW-001` Create Review
9. `REVIEW-002` Review Progress
10. `REVIEW-003` Review Result and Human Review
11. `WARNING-001` Warning List
12. `WARNING-002` Warning Detail

### 18.2 Prototype P1

完成核心路径后设计：认证辅助页、Notification Center、Report Viewer、Platform Organization、Organization Settings、Members、Risk Rules、Clause Templates。

### 18.3 Prototype P2

最后设计：Support Access、Platform/Organization Audit、Operations Metrics、Feedback Summary。

Prototype priority 不改变 Development Phase 顺序；前端实现仍严格按 `development-plan.md` 当前 Phase 推进。

## 19. Prototype Generation Plan

### Batch 1 - Foundation and Authentication

```text
LAYOUT-001 App Shell
AUTH-001 Login
AUTH-002 Forgot Password
AUTH-003 Reset Password
AUTH-004 Accept Invitation
```

目标：冻结整体视觉语言、认证表单、全局状态、Sidebar/Header 和角色语境。

### Batch 2 - Contract Catalog

```text
CONTRACT-001 Contract List
CONTRACT-002 Create Contract
CONTRACT-003 Contract Detail
```

目标：冻结数据表、筛选、详情层级、归档状态和权限呈现。

### Batch 3 - File and Evidence

```text
CONTRACT-004 File Upload and Versions
CONTRACT-005 Document Preview
```

目标：冻结外部模型告知、上传状态、文件版本、PDF/图片/DOCX 证据体验。

### Batch 4 - Review Task

```text
REVIEW-001 Create Review
REVIEW-002 Review Progress
```

目标：冻结版本选择、任务状态、阶段、轮询、失败和重试体验。

### Batch 5 - Review Result and Human Review

```text
REVIEW-003 Review Result and Human Review
```

该页面单独一批，至少生成：默认结果、证据打开、人工编辑、版本冲突、待处理阻塞、viewer 只读六个状态 Frame。

### Batch 6 - Warning, Notification and Report

```text
WARNING-001 Warning List
WARNING-002 Warning Detail
NOTIFY-001 Notification Center
REPORT-001 Report Status and Viewer
```

目标：冻结预警状态机、时间线、通知入口和异步报告状态。

### Batch 7 - Knowledge Configuration

```text
RULE-001 / RULE-002 / RULE-003
CLAUSE-001 / CLAUSE-002 / CLAUSE-003
```

目标：共享版本历史、草稿编辑、Schema 校验、发布不可变语言。

### Batch 8 - Organization Administration

```text
ORG-001 Organization Settings
ORG-002 Member Management
ORG-003 Support Access Management
ADMIN-001 Organization Audit Log
ADMIN-002 Operations Metrics
ADMIN-003 Feedback Summary
```

### Batch 9 - Platform Administration

```text
PLATFORM-001 Organization List
PLATFORM-002 Organization Detail
PLATFORM-003 Model Configuration
PLATFORM-004 Platform Audit Log
```

每个 Batch 开始时复用前一批确认的 Shell、spacing、typography、状态 Tag、表单和表格规范；不要在不同批次重做视觉语言。

## 20. Prototype Naming Convention

原型资产目录：

```text
docs/ui/stitch/
```

文件命名：

```text
<PAGE-ID>-<kebab-case-page-name>[-<state>].png
```

示例：

```text
LAYOUT-001-app-shell.png
AUTH-001-login.png
CONTRACT-001-contract-list-empty.png
CONTRACT-004-file-upload-error.png
REVIEW-002-review-progress-failed.png
REVIEW-003-review-result-conflict.png
WARNING-002-warning-detail-closed.png
```

Figma Page/Frame 同样使用 Page ID 作为前缀：`REVIEW-003 / Review Result / Pending Review`。交互状态使用 suffix，不创建新的业务 Page ID。HTML 用于布局和交互参考，PNG 用于视觉对照；二者都不是可直接复制的生产代码。

原型状态使用 `approved`、`draft`、`deprecated`。未显式标记时按当前 Phase Review 结果确认；`.stitch/metadata.json` 已标记 deprecated 的资产不得用于最终实现。

## 21. AI Prototype Handoff

每次交给 UI 生成 AI 的输入应包含：

```text
Product Context
+ Target User and Permission Mode
+ Selected Page Specification
+ Related API Fields and Status Values
+ Visual Design Direction
+ Existing Prototype Reference / Shared Shell
+ Required Loading, Empty, Error, Forbidden, Conflict and Disabled States
+ Interaction Requirements and Entry/Exit
```

AI 原型负责：

- 视觉布局；
- 信息层级；
- UI 元素组合；
- 交互状态表达；
- 在 1440px/1280px 下验证内容可用性。

AI 原型不负责：

- 修改业务规则或流程；
- 修改/发明 API 和字段；
- 修改权限或租户边界；
- 修改状态机；
- 创建新的产品能力；
- 把 Recommended/Pending UI Decision 写成已确认产品事实。

生成后 Review 必须逐项对照 Page ID、角色、Displayed Data、Actions、Forms、States 和 Traceability。发现规范冲突先报告，不直接在原型中“优化掉”业务步骤。

页面实现完成还必须在 1440px 和 1280px 下对照 approved PNG，覆盖适用的 loading、empty、error、forbidden、conflict、disabled、processing 和 retry 状态，并通过组件测试和适用的 Playwright 测试。页面完成不等于 Phase 完成，Phase 状态仍按 `docs/phase-status.md` 记录。

## 22. Traceability

### 22.1 API Module to UI Coverage

| API Module | Count | UI coverage | Internal/no business UI |
| --- | ---: | --- | --- |
| Authentication | 6 | AUTH-001-004, LAYOUT-001 | None |
| Organization and User | 18 | LAYOUT-001 organization profile/permissions, PLATFORM-001-003, ORG-001-003, ORG-002 invitation actions, CONTRACT-003 viewer grants | None; grant-list gap noted |
| Contract and File | 9 | CONTRACT-001-005 | None |
| Review Task and Result | 9 | REVIEW-001-003 | None |
| Risk Rule | 8 | RULE-001-003 | None |
| Clause Template | 8 | CLAUSE-001-003 | None |
| Warning | 3 | WARNING-001-002 | None |
| Notification | 3 | NOTIFY-001 | None |
| Report | 3 | REVIEW-003 create, REPORT-001 status/preview | None; list/retry gap noted |
| Feedback | 2 | REVIEW-003 submit, ADMIN-003 summary | None |
| Audit, Operations and Health | 6 | ADMIN-001-002, PLATFORM-004 | Health live/ready are proxy/orchestrator endpoints, no user page |

### 22.2 Requirements to Page Groups

| Requirement group | Primary pages |
| --- | --- |
| FR-A Authentication, organization, permission, audit | AUTH-*, LAYOUT-001, PLATFORM-*, ORG-*, ADMIN-001 |
| FR-D Upload, parsing, OCR, preview | CONTRACT-003-005, REVIEW-002 |
| FR-E Classification and extraction | REVIEW-003, CONTRACT-005 |
| FR-R Risk analysis | RULE-*, REVIEW-003 |
| FR-W Warnings and notification | WARNING-*, NOTIFY-001, REVIEW-003 |
| FR-C Clause templates and comparison | CLAUSE-*, REVIEW-003 |
| FR-RP Result and report | REVIEW-003, REPORT-001 |
| FR-F Feedback | REVIEW-003, ADMIN-003 |
| FR-O Configuration and operations | PLATFORM-003, ORG-001, ADMIN-002-003 |

### 22.3 Implementation Trace Chain

```text
Prototype Frame (Page ID)
-> docs/ui/design-system.md
-> docs/ui/frontend-prd.md Page Specification
-> docs/api-contract.md Method/Path/Schema/Permission/State
-> docs/requirements.md FR/NFR
-> docs/development-plan.md Phase
```

前端工程师在实现页面前仍需按当前 Phase 重新检查 API Contract、生成 OpenAPI 类型和所有直接调用方；本 PRD 不是 DTO 来源。

## 23. Pending UI Decisions

### 23.1 Upstream Contract/Product Decisions

| ID | Decision | Current recommendation | Blocking boundary |
| --- | --- | --- | --- |
| UI-P01 | 多组织用户如何选择当前组织 | 已采用 API Contract 2.2.1：`X-Organization-ID` 仅为选择提示，服务端校验 membership；单组织可自动选择，多组织缺失 Header 返回 409 | Closed 2026-08-18 |
| UI-P02（已关闭） | `found` 是否属于 `result_status` | 不加入 `found`；公共结果状态统一使用 `detected`，原型中的 TODO 以该语义实现 | Closed 2026-08-20 |
| UI-P03 | 规则集默认版本选择 | 已采用 P-04：每组织一个默认规则集，首个发布自动默认，后续显式切换，无默认时 409 | Closed 2026-08-19 |
| UI-P04 | 模板默认版本/业务场景选择 | 已采用 P-05：按组织+合同类型+规范化场景精确选择默认，无匹配时 409 | Closed 2026-08-19 |
| UI-P05 | 报告完整状态、失败重试、过期和再次生成 | 等待 P-06；只设计 generating/ready 的确认部分和通用失败容器 | Phase 13 |
| UI-P06 | Review `archived` 来源与恢复 | 等待 P-07；只读展示，不创建 archive/restore/cancel 控件 | Phase 9A |
| UI-P07 | 密码策略和 token TTL | 已采用 API Contract 3.1：密码 12-128 字符、重置 Token 30 分钟、邀请 Token 7 天 | Closed 2026-08-18; boundary tests required |
| UI-P08 | 合同已有 viewer 授权如何读取 | 当前没有 grant list/contract grant summary；需要先补契约或明确嵌入字段 | Phase 5 UI completeness |
| UI-P09 | DOCX 逻辑块如何通过浏览器 API 读取 | 已采用 API Contract 9.10 `GET /documents/{document_version_id}/blocks`；物理页仍使用 9.9 | Closed 2026-08-19 |
| UI-P10 | 完整修订历史如何读取 | API 保证修订事实但没有独立读取接口；仅展示当前响应和本次会话追加的修订，不假造完整 history feed | Phase 12 UI completeness |
| UI-P11 | 报告历史列表来源 | 当前无报告列表 API；不实现前端假列表 | Phase 13 UI completeness |
| UI-P12 | 邀请接受如何预判新用户/已有用户 | 无 invitation preflight API；先采用提交后字段反馈，或先更新契约 | Phase 2 UX |

### 23.2 Pure UI Decisions

| Decision | Recommended UI Decision | Status |
| --- | --- | --- |
| 是否需要 Dashboard | 首期不设；无专用 API，避免制造摘要字段 | Pending UI Decision, non-blocking |
| 默认登录后首页 | Platform-only context -> Organizations；组织工作区 -> Contracts | Pending until P-01 closes |
| Sidebar 信息层级 | Contracts/Warnings 一级；Rules/Templates 为 Knowledge Configuration；管理项 grouped | Pending visual validation |
| Create Organization/Invite/Grant | Compact Dialog；复杂编辑留独立页面/Drawer | Pending Figma usability test |
| Review Result navigation | Anchor/Tabs + evidence split pane | Pending high-fidelity prototype test |
| Notification form factor | Header Drawer | Pending UI Decision |
| 1280px Evidence behaviour | Split pane when viable; otherwise Drawer | Pending responsive prototype test |
| Frontend Page URL | 使用 Inventory 的固定 Vue Page URL，并保持 6.1 API 映射 | Page URL 不是 API Route；接口只以 API Contract 为准 |
| UI 文案 | 使用本 PRD 中文语义，最终错误文案优先 API `message` | Pending content review |

这些纯 UI 决策不阻塞无关后端 Phase。任何会改变 API、权限、状态或数据字段的需求不再属于纯 UI 决策，必须回到 Source of Truth 流程。

## 24. PRD Self-Check

1. 核心合同审核、预警、报告和管理流程均有页面承载。
2. 75 个 API 已按模块映射到 UI；health/ready 明确为内部接口。
3. 四类角色均有入口、可操作范围和禁止事项。
4. 主路径严格使用“合同 -> 文件 -> 审核任务 -> 结果/预警 -> 完成 -> 报告”。
5. 主要页面覆盖 loading、empty、error、forbidden、conflict、disabled 和 processing。
6. Review Result 已定义信息层级、风险、字段、条款、证据和人工复核。
7. Warning actions 使用 API Contract 现有状态与事件类型。
8. Displayed Data 和 Form 未加入 `risk_score`, `progress_percentage` 等未定义字段；审核进度只使用 API `progress`。
9. Platform Admin、Viewer 和组织角色边界未被页面入口突破。
10. 33 个设计面使用稳定 Page ID，原型命名沿用相同 ID。
11. 原型按 9 个共享视觉语言的 Batch 交付，不要求一次生成全部页面。
12. 前端工程师可从页面追踪 API/Requirements/Phase；UI Designer 无需阅读后端代码即可设计主要页面。
13. 33 个设计面均有显式 API Route 映射，且 Vue Page URL 不占用 `/api/v1`。
14. 原型目录、design system、deprecated 规则和 Phase Status 入口均已固定。
