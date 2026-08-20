# API Contract

## 1. 文档说明

本文件是企业合同智能审核与风险预警系统的唯一 API 契约来源（Single Source of Truth）。它基于 `docs/requirements.md` v1.0 和 `docs/architecture.md` 编写，覆盖首期闭环及架构中已定义的企业配置接口。

后端实现、前端 API Client、前端 TypeScript 类型、自动化测试和 API 文档必须以本文件为准。任何接口修改都必须同步检查：HTTP Method、Path、Request Schema、Response Schema、Error Schema、Authentication、Authorization、后端实现、前端 API Client、前端类型、测试和文档。前端或后端不得自行假设本文件未定义的字段。

本文件第 20 节记录已经确认的产品与部署基线。客户端不得以部署差异为由改变接口形状或自行选择另一套协议。

### 1.1 业务范围

接口覆盖：认证与用户、组织、合同与文件、审核任务与结果、风险规则、标准条款、预警、站内通知、HTML/PDF 报告、反馈、审计和运行健康检查。千问、OCR、病毒扫描、文件存储和 Worker 是后端内部适配边界，不对浏览器暴露供应商接口。SMTP 只负责发送邀请和密码重置令牌，不用于风险预警。

不在本契约中：自动签署或修改原合同、最终法律意见、印章鉴定、知识图谱、多轮改约、外部风险预警邮件/企业微信通知、OIDC SSO、履约日期提醒、批量 Word/Excel 导入和内部微服务接口。

## 2. 全局 API 约定

### 2.1 基础信息

| 项目 | 约定 |
| --- | --- |
| Base URL | `/api/v1` |
| 版本策略 | 主版本写入路径；新增字段保持向后兼容，删除字段或改变含义须发布新的主版本 |
| JSON Content-Type | `application/json; charset=utf-8` |
| 文件上传 Content-Type | `multipart/form-data` |
| 字段命名 | JSON、Query 和表单字段统一使用 `snake_case` |
| 字符编码 | UTF-8 |
| 时间 | ISO 8601 UTC，例如 `2026-08-17T03:30:00Z`；客户端按用户时区展示 |
| 日期 | `YYYY-MM-DD` |
| ID | UUID 字符串；展示编号另用 `display_no`，例如 `CTR-20260817-000123` |
| 金额 | 十进制字符串，不使用浮点数；同时传 ISO 4217 `currency` |
| 置信度 | 0 到 1 的 JSON number，服务端按 `0.0000` 精度保存 |
| 空值 | 可选或未发现的值使用 JSON `null`，不使用空字符串代替 |
| 默认排序 | `created_at` 降序；同一字段相同时以 `id` 降序稳定排序 |

### 2.2 公共请求头

| Header | 必填 | 说明 |
| --- | --- | --- |
| `Cookie` | 需登录接口必填 | 浏览器自动携带 `session` 会话 Cookie |
| `X-CSRF-Token` | 已登录的 POST/PATCH/PUT/DELETE 必填 | 使用 `GET /auth/session` 返回的 CSRF 原值；GET/HEAD 不需要 |
| `Origin` | 浏览器请求必填 | 服务端校验同源；不开放任意 CORS Origin |
| `X-Request-ID` | 否 | 客户端可提供符合长度/字符集限制的值；否则服务端生成并在响应中返回 |
| `X-Organization-ID` | 按接口需要 | 仅用于不含组织路径的组织级接口选择当前组织；服务端必须重新校验会话与有效成员关系，客户端值不是授权依据 |
| `Idempotency-Key` | 指定写接口必填 | 见 2.3；客户端只提供键，幂等作用域由服务端从可信上下文生成 |
| `X-Support-Access-Grant` | 平台管理员临时查看业务 JSON 时必填 | 有效临时支持授权 UUID；组织上下文由授权记录确定，最长有效 4 小时 |
| `If-Match` | 否 | 本契约统一使用请求体 `version` 做人工编辑乐观锁；服务端可额外返回 ETag |

响应都返回 `X-Request-ID`。除登录、密码重置和邀请接受等尚无会话的接口外，所有写请求都同时校验 Origin 和 CSRF。公共认证请求至少校验 Origin，并按 IP/账号限流。

### 2.2.1 当前组织选择

组织路径或已验证资源归属存在时，服务端从该路径/资源建立 Tenant Context，忽略 `X-Organization-ID`。没有组织路径但需要组织上下文的接口（例如组织审计日志）使用 `X-Organization-ID` 选择；服务端仅在会话用户拥有该组织的有效成员关系时建立上下文。缺失该 Header 且用户有且仅有一个有效成员关系时可自动选择该组织；多个有效成员关系时返回 `409 ORGANIZATION_CONTEXT_REQUIRED`。前端可本地记住用户选择，但每个请求都必须由后端重新校验，不能通过 Header 提升权限或改变资源归属。

### 2.3 版本与幂等

以下接口必须携带 `Idempotency-Key`：创建组织、创建合同、上传文件、创建审核、重试审核、生成报告、发送/重发邀请、创建临时支持授权、创建规则集/模板及其版本。键保留期默认 24 小时。

客户端只能提交 `Idempotency-Key`，不得通过 Header、Path、Query 或 Body 提交或控制 `idempotency_scope`、organization scope、tenant scope 或 platform scope。幂等作用域必须在认证、授权和租户/资源归属校验后由服务端生成；幂等命中和结果重放不得绕过当前请求的权限校验：

| 写接口类型 | 服务端作用域 | 可信来源 |
| --- | --- | --- |
| 组织级写接口 | `organization:<organization_id>` | 后端验证后的 Tenant Context；路径或资源中的组织 ID 在完成 membership、角色和资源归属校验前不是可信作用域 |
| 无 organization context 的平台级写接口 | `platform:<authenticated_user_id>` | 有效会话中的用户 ID，且当前用户已经通过 Platform Admin 权限校验 |

逻辑唯一性固定为 `(idempotency_scope, idempotency_key)`，路由不参与唯一键。同一组织内的不同用户共享组织作用域；不同组织可以使用相同键而互不冲突。不同平台操作主体可以使用相同键而互不冲突；同一平台操作主体的键在全部平台级写接口中共享作用域。服务端不得从客户端字段拼接作用域，也不得在冲突响应中返回原作用域、原请求摘要、原操作者或跨组织资源信息。

request fingerprint 必须由通过 Schema 校验并应用默认值后的关键请求语义规范化生成，至少包含 HTTP Method、规范化路由模板/operation key、可信 Path 参数、排序后的 Query 参数和规范化 Body；文件请求使用内容摘要及影响业务结果的元数据，不把原文件内容写入幂等记录。规范化结果使用确定性编码并只持久化密码学散列摘要，不持久化原始请求副本。`Cookie`、`Authorization`、会话令牌、CSRF Token、密码、一次性令牌、API Key、Secret、`X-Request-ID` 和 `Idempotency-Key` 本身不得进入可持久化摘要。operation key 属于 fingerprint，因此同一 scope 下把同一个键用于不同接口会得到不同 fingerprint，并返回冲突，而不会错误重放另一个接口的结果。

同一 scope、同一键且 fingerprint 相同，在原业务事务成功提交后返回原始成功状态和资源引用，或语义等价的重放结果；同一 scope、同一键但 fingerprint 不同，返回 `409 IDEMPOTENCY_KEY_REUSED`。并发重复请求必须由数据库唯一约束和事务串行化为一次业务写入：幂等记录、业务变更及对应审计在同一事务提交或回滚，只有已提交结果可以重放；首次事务回滚时不得留下伪成功记录。过期记录清理后，该键可以按新请求重新使用。

人工修改 `classification`、`extracted_field`、`risk_finding`、`clause_comparison` 时必须提交资源当前 `version`；版本不一致返回 `409 RESOURCE_VERSION_CONFLICT`。每次成功修改产生不可变修订记录。

### 2.4 成功响应

普通成功响应直接返回资源对象，不包装无依据的 `code/data/message` envelope。创建同步资源使用 `201 Created`，更新/读取使用 `200 OK`，归档等无响应体动作使用 `204 No Content`。长耗时审核和报告生成使用 `202 Accepted`，直接返回任务或报告资源。

列表使用游标分页：

```json
{
  "items": [],
  "next_cursor": "eyJjcmVhdGVkX2F0Ijoi...",
  "has_more": true
}
```

`limit` 默认 20，最大 100；没有 `next_cursor` 或值为 `null` 表示没有下一页。除非某个接口明确返回统计字段，不保证列表返回 `total`。

### 2.5 通用错误响应

所有错误使用同一结构，`message` 为可展示中文，不能包含堆栈、SQL、密钥、合同正文或供应商原始响应：

```json
{
  "error": {
    "code": "CONTRACT_FILE_UNSUPPORTED",
    "message": "仅支持 DOCX、PDF、PNG 和 JPEG 文件。",
    "request_id": "req_01J...",
    "details": { "field": "file" }
  }
}
```

`code` 是稳定的机器可读值；`details` 只放字段错误、限额、冲突版本或可恢复提示。HTTP 状态码表达协议层职责，业务代码表达具体原因：

| HTTP | 职责 | 常见业务错误码 |
| --- | --- | --- |
| `400` | 参数格式正确但业务条件不成立 | `INVALID_STATE_TRANSITION`, `INVALID_ACTION` |
| `401` | 未登录、会话过期或会话已撤销 | `AUTHENTICATION_REQUIRED`, `SESSION_EXPIRED` |
| `403` | 角色、组织或合同访问范围不允许 | `FORBIDDEN`, `CROSS_ORGANIZATION_ACCESS` |
| `404` | 资源不存在，或隐藏无权资源以防枚举 | `RESOURCE_NOT_FOUND` |
| `409` | 状态冲突、幂等键冲突、版本冲突 | `RESOURCE_VERSION_CONFLICT`, `IDEMPOTENCY_KEY_REUSED` |
| `413` | 超过组织配置的文件大小/页数/配额 | `FILE_TOO_LARGE`, `PAGE_LIMIT_EXCEEDED` |
| `415` | 扩展名、MIME 或文件签名不支持 | `CONTRACT_FILE_UNSUPPORTED` |
| `422` | 请求字段或结构化结果未通过 Schema 校验 | `VALIDATION_ERROR`, `MODEL_OUTPUT_INVALID` |
| `429` | 用户/组织并发达到上限，或请求触发速率限制 | `CONCURRENCY_LIMIT_EXCEEDED`, `RATE_LIMITED` |
| `500` | 未预期服务错误 | `INTERNAL_ERROR` |
| `502/503/504` | 同步依赖不可用；异步依赖通常写入任务状态 | `DEPENDENCY_UNAVAILABLE`, `SERVICE_NOT_READY` |

## 3. Authentication

### 3.1 会话认证

系统使用服务端不透明会话 Cookie，不使用 JWT，不使用 Refresh Token。生产环境登录成功后服务端设置 `Secure; HttpOnly; SameSite=Lax` Cookie；本地开发和自动化测试可使用非 Secure Cookie，且不得部署到公网。响应 JSON 不返回会话令牌。会话默认闲置 8 小时、绝对有效期 7 天，密码重置、停用用户和关键权限变化会撤销会话。密码至少 12 个字符、最多 128 个字符；不强制字符类别，以支持密码管理器生成的长口令。密码重置令牌有效期 30 分钟，邀请令牌有效期 7 天，二者均使用至少 256 位随机值并且数据库只保存哈希。

### 3.2 登录

**接口名称：用户登录**

`POST /api/v1/auth/login`

权限：`Public`。

Request：

| 位置 | 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- | --- |
| Header | `Origin` | string | 是 | 必须是允许的同源 |
| Body | `email` | string | 是 | 邮箱会被规范化后全局匹配 |
| Body | `password` | string | 是 | 仅用于 Argon2id 校验，不回显 |

Request Example：

```json
{ "email": "legal@example.com", "password": "correct-horse-battery" }
```

Success `200 OK`：返回 `Session`，并设置会话 Cookie。

```json
{
  "user": { "id": "8b2f8a68-5e4a-4b0a-b6a2-6dce4e0f5a11", "email": "legal@example.com", "display_name": "李法务", "is_platform_admin": false },
  "organizations": [{ "id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "name": "示例企业", "role": "reviewer" }],
  "csrf_token": "csrf_01J..."
}
```

主要错误：`400 INVALID_CREDENTIALS`（格式非法）、`401 AUTHENTICATION_FAILED`（账号或密码错误）、`403 USER_DISABLED`、`429 RATE_LIMITED`。

### 3.3 退出

**接口名称：用户退出**

`POST /api/v1/auth/logout`

权限：`Authenticated User`。无 Request Body；需要 `X-CSRF-Token`。

Request Example：`{}`

Success `204 No Content`：撤销当前会话并清除 Cookie。

主要错误：`401 SESSION_EXPIRED`、`403 CSRF_INVALID`。

### 3.4 查询会话

**接口名称：获取当前会话**

`GET /api/v1/auth/session`

权限：`Authenticated User`。

Request：无 Path、Query 或 Body；使用会话 Cookie。

Request Example：`GET /api/v1/auth/session`

Success `200 OK`：返回当前用户、可用组织角色和新的/轮换后的 CSRF 原值。

```json
{
  "user": { "id": "8b2f8a68-5e4a-4b0a-b6a2-6dce4e0f5a11", "email": "legal@example.com", "display_name": "李法务", "status": "active", "is_platform_admin": false },
  "memberships": [{ "organization_id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "organization_name": "示例企业", "role": "reviewer", "status": "active" }],
  "csrf_token": "csrf_01J..."
}
```

主要错误：`401 AUTHENTICATION_REQUIRED`、`401 SESSION_EXPIRED`。

### 3.5 请求密码重置

**接口名称：发起密码重置**

`POST /api/v1/auth/password-reset/request`

权限：`Public`。服务端无论邮箱是否存在都返回相同结果，防止账号枚举；账号存在时通过 SMTP 异步发送一次性重置链接。SMTP 投递结果不得用于推断账号是否存在。

部署必须配置 `SMTP_HOST`、`SMTP_PORT`、`SMTP_FROM` 和 `FRONTEND_BASE_URL`；配置缺失时在查询账号前统一返回 `503 SMTP_NOT_CONFIGURED`，因此该错误不泄露账号是否存在。首期每个请求最多执行 1 次后台 SMTP 投递，不做自动重试（retry cap = 0）；投递失败不得改变已经返回的 `202`，但必须记录只包含 `request_id`、错误类别和投递阶段的安全结构化日志/指标，不记录收件邮箱、Token 或完整重置 URL。普通自动化测试使用 Fake Mailer，不调用真实 SMTP；后续如增加持久化投递和重试，必须先扩展契约和数据状态。

Request：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `email` | string | 是 | 规范化邮箱 |

Request Example：`{ "email": "legal@example.com" }`

Success `202 Accepted`：

```json
{ "accepted": true, "message": "如果账号存在，系统将继续处理密码重置请求。" }
```

主要错误：`422 VALIDATION_ERROR`、`429 RATE_LIMITED`、`503 SMTP_NOT_CONFIGURED`。不得返回“邮箱不存在”；SMTP 运行时投递失败不通过响应区分账号状态。

### 3.6 确认密码重置

**接口名称：确认密码重置**

`POST /api/v1/auth/password-reset/confirm`

权限：`Public`，使用 SMTP 邮件中的一次性令牌；成功后撤销该用户其他会话。

Request：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `token` | string | 是 | 一次性重置令牌 |
| `new_password` | string | 是 | 满足服务端密码策略 |

Request Example：`{ "token": "reset_01J...", "new_password": "new-correct-password" }`

Success `204 No Content`。

主要错误：`400 TOKEN_INVALID`、`400 TOKEN_EXPIRED`、`409 TOKEN_ALREADY_USED`、`422 VALIDATION_ERROR`。

### 3.7 接受组织邀请

**接口名称：接受组织邀请**

`POST /api/v1/auth/invitations/accept`

权限：`Public`，使用一次性邀请令牌；已有用户只设置组织成员关系，新用户同时创建账号。

Request：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `token` | string | 是 | 一次性邀请令牌 |
| `display_name` | string | 新用户必填 | 展示名 |
| `password` | string | 新用户必填 | 新账号密码 |

Request Example：`{ "token": "invite_01J...", "display_name": "王审核", "password": "strong-password" }`

Success `200 OK`：

```json
{ "user_id": "a2c7d7d7-4c31-4e45-aef5-02d1ec4b9011", "organization_id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "role": "reviewer", "status": "active" }
```

主要错误：`400 TOKEN_INVALID`、`400 TOKEN_EXPIRED`、`409 EMAIL_ALREADY_IN_USE`、`422 VALIDATION_ERROR`。

## 4. Authorization

### 4.1 角色

| 值 | 中文含义 | 前端是否可直接修改 | 说明 |
| --- | --- | --- | --- |
| `platform_admin` | 平台管理员 | 否 | 由 `users.is_platform_admin` 表示，只能通过平台路由管理 |
| `org_admin` | 组织管理员 | 是（仅平台管理员或组织管理员按策略） | 管理本组织用户、规则、模板、数据和报表 |
| `reviewer` | 审核员/法务 | 是 | 上传、审核、复核、修改结果、处置预警和反馈 |
| `viewer` | 业务查看者 | 是 | 仅查看显式授权的合同、报告和预警 |

所有业务资源都绑定 `organization_id`。服务端按“会话有效 -> 组织成员有效 -> 动作权限 -> 资源组织归属 -> viewer 显式合同授权”的顺序校验。审核员可查看和处理本组织全部合同；viewer 仅能查看显式授权合同。客户端不得提交 `organization_id` 来提升权限；使用组织路径时服务端仍以会话和成员关系为准。

平台管理员默认不能访问组织业务数据。组织管理员可授予最长 4 小时的临时只读支持权限；平台管理员携带有效 `X-Support-Access-Grant` 后，仅可调用现有业务 JSON GET 接口。临时权限不允许任何写操作，也不允许调用合同文件或报告下载接口。授权创建、撤销以及授权期间的每次访问都必须写入审计日志。

| 动作 | 平台管理员 | 组织管理员 | 审核员 | 业务查看者 |
| --- | --- | --- | --- | --- |
| 平台组织、模型、全局审计 | 是 | 否 | 否 | 否 |
| 本组织用户、规则、模板 | 平台路由按需授权 | 读写 | 只读已发布版本 | 否 |
| 创建合同、上传、创建审核 | 否 | 是 | 是 | 否 |
| 查看本组织合同/报告 JSON | 临时支持授权期间只读 | 全部 | 本组织全部 | 显式授权 |
| 下载合同/报告文件 | 否 | 是 | 是 | 显式授权 |
| 修改审核结果、处置预警 | 否 | 是 | 是 | 否 |
| 审计查询 | 全局 | 本组织 | 否 | 否 |

### 4.2 组织与用户数据结构

`Organization`：`id`, `name`, `status`, `retention_days`, `settings`（不含秘密）。

`Membership`：`id`, `organization_id`, `user_id`, `email`, `display_name`, `role`, `status`, `invited_at`, `email_delivery_status`, `version`, `created_at`, `updated_at`。

`email_delivery_status` 仅用于待邀请成员，可为 `queued | sent | failed`；已激活或未发送邀请的成员返回 `null`。后台投递失败不改变已经返回的创建/重发成功状态，也不自动重试；组织管理员通过成员列表看到 `failed` 并可显式重发。

平台管理员标记、密码哈希、会话令牌、CSRF 哈希、模型密钥和 `secret_ref` 不在普通业务响应中返回。

## 5. 通用数据结构

### 5.1 Source Locator

所有模型结论、风险和条款结果至少提供一个证据定位（缺失条款允许没有定位）。

```json
{
  "document_version_id": "2c5b0b5d-6c3c-46aa-a9d1-75c5a817d4b1",
  "kind": "pdf_page",
  "page_no": 3,
  "paragraph_no": null,
  "table_path": null,
  "start_offset": 128,
  "end_offset": 176,
  "bbox": { "x": 80.2, "y": 214.0, "width": 420.0, "height": 38.0 },
  "quote": "乙方应承担全部且无限的责任。"
}
```

`kind`：`pdf_page | image_page | docx_paragraph | docx_table_cell`。DOCX 不伪造页码；其权威定位是段落号、表格路径和字符区间。

### 5.2 File Object

```json
{
  "id": "9c2e75b3-95d1-4f18-8f8c-65d25358c90e",
  "original_name": "采购合同.pdf",
  "media_type": "application/pdf",
  "size_bytes": 284901,
  "sha256": "3f786850e387550fdab836ed7e6dc881de23001b",
  "scan_status": "clean",
  "storage_status": "stored",
  "created_at": "2026-08-17T03:31:00Z"
}
```

允许上传扩展名及 MIME/文件签名均通过校验的 `.docx`、`.pdf`、`.png`、`.jpg`、`.jpeg`。具体大小和页数由组织配置决定，契约不硬编码数值。

### 5.3 Contract

```json
{
  "id": "5a7b9e6b-3e0d-4ae0-9ae8-0e45fcf3be17",
  "display_no": "CTR-20260817-000123",
  "title": "供应商采购合同",
  "declared_type": "purchase",
  "status": "active",
  "owner_id": "8b2f8a68-5e4a-4b0a-b6a2-6dce4e0f5a11",
  "current_file": { "id": "9c2e75b3-95d1-4f18-8f8c-65d25358c90e", "version_no": 1, "is_current": true },
  "created_at": "2026-08-17T03:30:00Z",
  "updated_at": "2026-08-17T03:31:00Z",
  "version": 1
}
```

### 5.4 Review Task

```json
{
  "id": "67f0ab0d-cf70-470c-b5e7-92a18d6d73a5",
  "display_no": "REV-20260817-000045",
  "contract_id": "5a7b9e6b-3e0d-4ae0-9ae8-0e45fcf3be17",
  "status": "pending_review",
  "progress": 100,
  "current_stage": "report",
  "error_code": null,
  "error_message": null,
  "rule_bundle_version_id": "d2f7e5cd-9235-4328-b0b1-7af8dfc5fa99",
  "clause_template_version_id": "7f4e18e9-2d1e-4b52-8c8c-4d08c8d11120",
  "created_at": "2026-08-17T03:32:00Z",
  "started_at": "2026-08-17T03:32:02Z",
  "finished_at": "2026-08-17T03:34:10Z"
}
```

### 5.5 Review Result

审核结果由 `classification`、`extracted_fields`、`risk_findings`、`clause_comparisons`、`warnings` 和 `summary` 组成；所有人工修改保留 `model_value`、`current_value` 和修订历史。

### 5.6 Money and extracted fields

金额：`{ "amount": "100000.00", "currency": "CNY", "tax_included": true }`。

字段键：`parties`, `signing_date`, `contract_amount`, `performance_period`, `dispute_resolution`, `payment_terms`, `auto_renewal`。缺失字段的 `current_value` 为 `null`，`status` 必须为 `not_found` 或 `needs_confirmation`。

## 6. 枚举与状态定义

### 6.1 合同和审核

| 枚举 | 值 | 中文含义 | 前端可直接修改 |
| --- | --- | --- | --- |
| `contract_type` | `purchase`, `sales`, `nda`, `outsourcing`, `employment`, `other` | 采购、销售、保密、服务外包、劳动、其他/待确认 | `declared_type` 可修改；模型分类须通过结果修订接口 |
| `contract_status` | `active`, `archived` | 活跃、已归档 | 否，使用 archive/restore 动作 |
| `review_status` | `pending`, `parsing`, `reviewing`, `pending_review`, `completed`, `failed`, `archived` | 待处理、解析中、审核中、待复核、已完成、失败、已归档 | 否，使用业务动作 |
| `result_status` | `detected`, `not_found`, `needs_confirmation`, `confirmed`, `corrected` | 已识别、未发现、待确认、已确认、人工修订 | 通过审核/修订接口间接改变 |

任务合法流转：`pending -> parsing -> reviewing -> pending_review -> completed`；任一处理阶段可到 `failed`，
`failed -> parsing/reviewing` 由 retry；重新审核创建新的 `ReviewTask`；`archived` 仅表示已有的只读历史事实，
本契约没有把合同归档或任何未定义命令作为其进入来源。合同归档不改变任务状态。

### 6.2 风险、条款和预警

| 枚举 | 值 | 中文含义 | 前端可直接修改 |
| --- | --- | --- | --- |
| `severity` | `high`, `medium`, `low` | 高、中、低 | 风险发现不可直接改等级；规则/模板草稿可配置 |
| `risk_source` | `rule`, `model`, `human` | 规则、模型、人工 | 否 |
| `risk_finding_status` | `pending_review`, `confirmed`, `false_positive`, `processed` | 待复核、已确认、误报、已处理 | 只能由审核/预警动作产生 |
| `clause_comparison_status` | `matched`, `deviated`, `missing`, `uncertain` | 匹配、存在偏差、缺失、无法判断 | 只能人工修订结果，不可把 uncertain 静默改为 matched |
| `warning_status` | `pending_confirmation`, `in_progress`, `ignored`, `resolved`, `closed` | 待确认、处理中、已忽略、已解决、已关闭 | 只能通过 warning event |
| `warning_event_type` | `confirm`, `false_positive`, `ignore`, `assign`, `note`, `resolve`, `close`, `reopen` | 确认、误报、忽略、转派、补充说明、解决、关闭、重新打开 | 是，但必须遵守状态机和必填字段 |
| `version_status` | `draft`, `published`, `disabled` | 草稿、已发布、已停用 | 只能通过版本动作 |
| `feedback_label` | `correct`, `incorrect`, `modified`, `ignored` | 正确、错误、修改、忽略 | 是 |

预警合法流转：`pending_confirmation -> in_progress -> resolved -> closed`；`pending_confirmation/in_progress -> ignored`；组织管理员可 `ignored/closed -> in_progress`。`assign` 和 `note` 不改变主状态。关闭必须有 `resolution` 或 `revision_id`。

## 7. 分页、筛选和排序

列表通用 Query：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `limit` | integer | 否 | 1-100，默认 20 |
| `cursor` | string | 否 | 上一页返回的 `next_cursor` |
| `sort` | string | 否 | 仅接受接口声明的白名单字段 |
| `direction` | `asc\|desc` | 否 | 默认 `desc` |
| `q` | string | 否 | 接口支持时按名称、标题或邮箱搜索 |

合同列表支持 `status`, `declared_type`, `owner_id`；审核任务支持 `status`, `contract_id`；预警支持 `status`, `severity`, `contract_type`, `assignee_id`, `risk_type`, `triggered_from`, `triggered_to`；审计支持 `action`, `resource_type`, `actor_id`, `created_from`, `created_to`。未知筛选字段返回 `422 VALIDATION_ERROR`。

## 8. Organization and User APIs

### 8.1 平台组织列表

`GET /api/v1/platform/organizations`。权限：`Platform Admin`。用于平台级组织检索。

Request Query：通用分页，加 `q`, `status`；`sort` 允许 `created_at`, `name`。无 Body。

Request Example：`GET /api/v1/platform/organizations?status=active&limit=20`

Success `200 OK`：`CursorPage<Organization>`。

```json
{ "items": [{ "id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "name": "示例企业", "status": "active", "retention_days": 180 }], "next_cursor": null, "has_more": false }
```

主要错误：`401 AUTHENTICATION_REQUIRED`、`403 PLATFORM_ADMIN_REQUIRED`。

### 8.2 创建组织

`POST /api/v1/platform/organizations`。权限：`Platform Admin`。需要 `Idempotency-Key` 和 CSRF。

Request Body：`name: string`（必填）、`initial_admin_email: string`（必填）、`retention_days?: integer`（非负，默认 180）。

Request Example：`{ "name": "示例企业", "initial_admin_email": "admin@example.com", "retention_days": 180 }`

Success `201 Created`：返回 `Organization`。

```json
{ "id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "name": "示例企业", "status": "active", "retention_days": 180, "created_at": "2026-08-17T03:00:00Z" }
```

主要错误：`403 PLATFORM_ADMIN_REQUIRED`、`409 ORGANIZATION_NAME_CONFLICT`、`422 VALIDATION_ERROR`。

### 8.3 获取组织

`GET /api/v1/platform/organizations/{organization_id}`。权限：`Platform Admin`。

Path：`organization_id` UUID，必填。无 Query/Body。

Request Example：`GET /api/v1/platform/organizations/1d2f3a4b-5c6d-7e8f-9012-345678901234`

Success `200 OK`：返回完整 `Organization`，包括非秘密配置摘要。

```json
{ "id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "name": "示例企业", "status": "active", "retention_days": 180, "settings": { "warn_on_medium_risk": false } }
```

主要错误：`403 PLATFORM_ADMIN_REQUIRED`、`404 ORGANIZATION_NOT_FOUND`。

### 8.4 更新组织

`PATCH /api/v1/platform/organizations/{organization_id}`。权限：`Platform Admin`。

Request Body：`name?: string`, `status?: active|disabled`, `retention_days?: integer`, `version: integer`；至少一个可更新字段。

Request Example：`{ "status": "disabled", "version": 3 }`

Success `200 OK`：返回更新后的 `Organization`。

```json
{ "id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "name": "示例企业", "status": "disabled", "retention_days": 180, "version": 4 }
```

主要错误：`403 PLATFORM_ADMIN_REQUIRED`、`404 ORGANIZATION_NOT_FOUND`、`409 ORGANIZATION_NAME_CONFLICT`、`409 RESOURCE_VERSION_CONFLICT`。

组织名称按 `lower(trim(name))` 做规范化并在平台范围内唯一；首尾空白和大小写差异视为同名。

### 8.5 获取当前组织资料

`GET /api/v1/organizations/{organization_id}`。权限：该组织的 `Org Admin | Reviewer | Viewer`。

Path：`organization_id` UUID。无 Body。

Request Example：`GET /api/v1/organizations/{organization_id}`

Success `200 OK`：返回组织基础资料以及当前用户权限集合。

```json
{ "id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "name": "示例企业", "status": "active", "my_role": "reviewer", "permissions": ["contracts:read", "contracts:create", "reviews:write", "warnings:write"] }
```

主要错误：`401 AUTHENTICATION_REQUIRED`、`404 ORGANIZATION_NOT_FOUND`（含跨组织隐藏）。

### 8.6 获取组织设置

`GET /api/v1/organizations/{organization_id}/settings`。权限：`Org Admin`；审核员和查看者不得访问管理配置。

Request：Path `organization_id`；无 Query/Body。

Request Example：`GET /api/v1/organizations/{organization_id}/settings`

Success `200 OK`：只返回非秘密设置。

```json
{ "file_size_limit_bytes": 20971520, "page_limit": 100, "concurrent_review_limit": 3, "warn_on_medium_risk": false, "ocr_low_confidence_threshold": 0.8, "retention_days": 180, "report_watermark": "仅供内部审核", "version": 2 }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 ORGANIZATION_NOT_FOUND`。首期默认值为 20 MiB、100 页、每组织并发审核 3 个、OCR 阈值 0.80、合同/报告保留 180 天；组织管理员可在平台允许范围内调整组织设置。

### 8.7 更新组织设置

`PATCH /api/v1/organizations/{organization_id}/settings`。权限：`Org Admin`。

Request Body：8.6 中任一非秘密字段，加必填 `version`。未知字段返回 `422`；模型密钥不得通过本接口提交。

Request Example：`{ "warn_on_medium_risk": true, "report_watermark": "内部资料", "version": 2 }`

Success `200 OK`：返回更新后的设置，`version` 递增。

```json
{ "warn_on_medium_risk": true, "report_watermark": "内部资料", "version": 3 }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`409 RESOURCE_VERSION_CONFLICT`、`422 VALIDATION_ERROR`。

### 8.8 获取平台模型配置

`GET /api/v1/platform/model-configuration`。权限：`Platform Admin`。

Request：无参数。Success `200 OK`：不返回密钥或令牌，只返回是否已配置秘密。

Request Example：`GET /api/v1/platform/model-configuration`

```json
{ "provider": "qwen", "model": "qwen-model-from-environment", "model_source": "environment", "timeout_seconds": 60, "max_retries": 3, "hard_budget_enabled": false, "usage_tracking_enabled": true, "organization_overrides_allowed": false, "secret_configured": true, "status": "active", "version": 1 }
```

主要错误：`403 PLATFORM_ADMIN_REQUIRED`。

### 8.9 更新平台模型配置

`PATCH /api/v1/platform/model-configuration`。权限：`Platform Admin`。

Request Body：`timeout_seconds?: integer`, `max_retries?: integer`, `usage_tracking_enabled?: boolean`, `status?: active|disabled`, `version: integer`。首期模型名称和密钥仅由部署环境变量提供，不能通过 API 修改；组织不能覆盖平台模型配置。

Request Example：`{ "timeout_seconds": 60, "max_retries": 3, "usage_tracking_enabled": true, "version": 1 }`

Success `200 OK`：返回脱敏后的模型配置。

```json
{ "provider": "qwen", "model": "qwen-model-from-environment", "model_source": "environment", "timeout_seconds": 60, "max_retries": 3, "hard_budget_enabled": false, "usage_tracking_enabled": true, "organization_overrides_allowed": false, "secret_configured": true, "status": "active", "version": 2 }
```

主要错误：`403 PLATFORM_ADMIN_REQUIRED`、`409 RESOURCE_VERSION_CONFLICT`、`422 VALIDATION_ERROR`、`503 MODEL_ENVIRONMENT_NOT_CONFIGURED`。

### 8.10 组织成员列表

`GET /api/v1/organizations/{organization_id}/members`。权限：`Org Admin`。

Request Query：通用分页，加 `q`, `role`, `status`；排序允许 `created_at`, `display_name`。

Request Example：`GET /api/v1/organizations/{organization_id}/members?role=reviewer&status=active`

Success `200 OK`：`CursorPage<Membership>`。成员项包含 `id`, `user_id`, `email`, `display_name`, `role`, `status`, `invited_at`, `email_delivery_status`, `version`, `created_at`, `updated_at`；未发送邀请的 `invited_at` 和 `email_delivery_status` 为 `null`。

```json
{ "items": [{ "id": "6a33fe0b-c292-4e0a-886c-9b767496527f", "user_id": "8b2f8a68-5e4a-4b0a-b6a2-6dce4e0f5a11", "email": "legal@example.com", "display_name": "李法务", "role": "reviewer", "status": "active" }], "next_cursor": null, "has_more": false }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 ORGANIZATION_NOT_FOUND`。

### 8.11 邀请组织成员

`POST /api/v1/organizations/{organization_id}/members`。权限：`Org Admin`。需要 `Idempotency-Key`。

Request Body：`email: string`（必填）、`role: org_admin|reviewer|viewer`（必填，不能为 platform_admin）。

Request Example：`{ "email": "reviewer@example.com", "role": "reviewer" }`

Success `201 Created`：创建 `pending_invitation` 成员，响应中的 `email_delivery_status` 为 `queued`；SMTP 后台投递成功后变为 `sent`，运行时失败后变为 `failed`。后台失败不改变已返回的 `201`，不自动重试。

```json
{ "id": "2f69c1a8-7302-4f97-8f81-c9adc2774ed8", "email": "reviewer@example.com", "role": "reviewer", "status": "pending_invitation", "invited_at": "2026-08-17T04:00:00Z", "email_delivery_status": "queued" }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`409 MEMBERSHIP_ALREADY_EXISTS`、`422 INVALID_ROLE`、`503 SMTP_NOT_CONFIGURED`。成功时通过 SMTP 异步发送一次性邀请链接；邮件正文不得包含密码或会话令牌。

### 8.12 重发组织邀请

`POST /api/v1/members/{member_id}/resend-invitation`。权限：目标组织的 `Org Admin`。需要 `Idempotency-Key`；仅 `pending_invitation` 成员可调用。

Request Body：`{}`。

Request Example：`POST /api/v1/members/{member_id}/resend-invitation` with body `{}`

Success `202 Accepted`：作废旧邀请令牌，生成新的单次令牌并通过 SMTP 异步发送；响应中的 `email_delivery_status` 为 `queued`，后台完成后按 `sent` 或 `failed` 更新。后台失败不改变已返回的 `202`，不自动重试。

```json
{ "member_id": "2f69c1a8-7302-4f97-8f81-c9adc2774ed8", "status": "pending_invitation", "email_delivery_status": "queued", "invited_at": "2026-08-17T04:30:00Z" }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 MEMBER_NOT_FOUND`、`409 MEMBER_NOT_PENDING_INVITATION`、`429 RATE_LIMITED`、`503 SMTP_NOT_CONFIGURED`。

### 8.13 更新组织成员

`PATCH /api/v1/members/{member_id}`。权限：目标组织的 `Org Admin`。

Request Body：`role?: org_admin|reviewer|viewer`, `status?: active|disabled`, `version: integer`。不得授予平台管理员；不得停用组织最后一个有效组织管理员。

Request Example：`{ "role": "viewer", "version": 2 }`

Success `200 OK`：返回更新后的 `Membership`。

```json
{ "id": "6a33fe0b-c292-4e0a-886c-9b767496527f", "email": "legal@example.com", "role": "viewer", "status": "active", "version": 3 }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 MEMBER_NOT_FOUND`、`409 LAST_ORG_ADMIN`、`409 RESOURCE_VERSION_CONFLICT`。

### 8.14 授予合同查看权限

`PUT /api/v1/contracts/{contract_id}/access-grants/{user_id}`。权限：`Org Admin`。只允许为同组织有效 `viewer` 授权。

Request Body：`{ "access_level": "read" }`；当前仅支持 `read`。

Request Example：`{ "access_level": "read" }`

Success `200 OK`：

```json
{ "contract_id": "5a7b9e6b-3e0d-4ae0-9ae8-0e45fcf3be17", "user_id": "a2c7d7d7-4c31-4e45-aef5-02d1ec4b9011", "access_level": "read" }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 CONTRACT_OR_USER_NOT_FOUND`、`409 CROSS_ORGANIZATION_ACCESS`。

### 8.15 撤销合同查看权限

`DELETE /api/v1/contracts/{contract_id}/access-grants/{user_id}`。权限：`Org Admin`。无 Body。

Request Example：`DELETE /api/v1/contracts/{contract_id}/access-grants/{user_id}`

Success `204 No Content`；重复撤销同样返回 204。

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 CONTRACT_OR_USER_NOT_FOUND`。

### 8.16 查询临时支持授权

`GET /api/v1/organizations/{organization_id}/support-access-grants`。权限：`Org Admin`。用于查看当前及历史平台支持授权。

Request Query：通用分页，加 `status=active|expired|revoked`, `platform_admin_user_id`；排序允许 `created_at`, `expires_at`。

Request Example：`GET /api/v1/organizations/{organization_id}/support-access-grants?status=active`

Success `200 OK`：

```json
{ "items": [{ "id": "10e249ae-ae58-48be-b660-1fe3ef137a5a", "organization_id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "platform_admin_user_id": "312aac55-05a7-42a5-a5bb-8c8ea7347c5f", "reason": "排查报告生成失败", "status": "active", "granted_by": "8b2f8a68-5e4a-4b0a-b6a2-6dce4e0f5a11", "created_at": "2026-08-17T06:00:00Z", "expires_at": "2026-08-17T10:00:00Z" }], "next_cursor": null, "has_more": false }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 ORGANIZATION_NOT_FOUND`、`422 INVALID_FILTER`。

### 8.17 创建临时支持授权

`POST /api/v1/organizations/{organization_id}/support-access-grants`。权限：`Org Admin`。需要 `Idempotency-Key`。

Request Body：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `platform_admin_user_id` | UUID | 是 | 目标用户必须是有效平台管理员 |
| `reason` | string | 是 | 非空支持原因，写入审计日志 |
| `expires_at` | datetime | 是 | 必须晚于当前时间，且不得超过创建时间后 4 小时 |

Request Example：`{ "platform_admin_user_id": "312aac55-05a7-42a5-a5bb-8c8ea7347c5f", "reason": "排查报告生成失败", "expires_at": "2026-08-17T10:00:00Z" }`

Success `201 Created`：

```json
{ "id": "10e249ae-ae58-48be-b660-1fe3ef137a5a", "organization_id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "platform_admin_user_id": "312aac55-05a7-42a5-a5bb-8c8ea7347c5f", "reason": "排查报告生成失败", "status": "active", "granted_by": "8b2f8a68-5e4a-4b0a-b6a2-6dce4e0f5a11", "expires_at": "2026-08-17T10:00:00Z" }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 PLATFORM_ADMIN_NOT_FOUND`、`409 ACTIVE_SUPPORT_GRANT_EXISTS`、`422 SUPPORT_GRANT_DURATION_INVALID`。

### 8.18 撤销临时支持授权

`DELETE /api/v1/organizations/{organization_id}/support-access-grants/{grant_id}`。权限：`Org Admin`。无 Body；撤销立即生效。

Request Example：`DELETE /api/v1/organizations/{organization_id}/support-access-grants/{grant_id}`

Success `204 No Content`。已撤销或已过期的授权重复撤销同样返回 204。

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 SUPPORT_GRANT_NOT_FOUND`。

## 9. Contract and File APIs

### 9.1 创建合同

`POST /api/v1/contracts`。权限：`Org Admin | Reviewer`。需要 `Idempotency-Key`。

Request Body：`title: string`（必填）、`declared_type?: contract_type`。组织由当前会话确定，不接受客户端 `organization_id`。

Request Example：`{ "title": "供应商采购合同", "declared_type": "purchase" }`

Success `201 Created`：返回 `Contract`，初始 `status=active`，文件为空。

```json
{ "id": "5a7b9e6b-3e0d-4ae0-9ae8-0e45fcf3be17", "display_no": "CTR-20260817-000123", "title": "供应商采购合同", "declared_type": "purchase", "status": "active", "current_file": null, "version": 1 }
```

主要错误：`403 FORBIDDEN`、`422 VALIDATION_ERROR`、`429 ORGANIZATION_QUOTA_EXCEEDED`。

### 9.2 合同列表

`GET /api/v1/contracts`。权限：`Org Admin | Reviewer | Viewer`；viewer 仅返回显式授权合同。

Request Query：通用分页，加 `q`, `status`, `declared_type`, `owner_id`；排序允许 `created_at`, `updated_at`, `title`。

Request Example：`GET /api/v1/contracts?status=active&declared_type=purchase&limit=20`

Success `200 OK`：`CursorPage<Contract>`。

```json
{ "items": [{ "id": "5a7b9e6b-3e0d-4ae0-9ae8-0e45fcf3be17", "display_no": "CTR-20260817-000123", "title": "供应商采购合同", "declared_type": "purchase", "status": "active" }], "next_cursor": null, "has_more": false }
```

主要错误：`401 AUTHENTICATION_REQUIRED`、`422 VALIDATION_ERROR`。

### 9.3 合同详情

`GET /api/v1/contracts/{contract_id}`。权限：`Org Admin | Reviewer | authorized Viewer`。

Path：`contract_id` UUID。无 Body。

Request Example：`GET /api/v1/contracts/{contract_id}`

Success `200 OK`：返回 `Contract`，附文件版本摘要和最近审核摘要。

```json
{ "id": "5a7b9e6b-3e0d-4ae0-9ae8-0e45fcf3be17", "display_no": "CTR-20260817-000123", "title": "供应商采购合同", "declared_type": "purchase", "status": "active", "files": [{ "id": "9c2e75b3-95d1-4f18-8f8c-65d25358c90e", "version_no": 1, "is_current": true }], "latest_review": { "id": "67f0ab0d-cf70-470c-b5e7-92a18d6d73a5", "status": "pending_review" }, "version": 1 }
```

主要错误：`404 CONTRACT_NOT_FOUND`（含无权访问时隐藏）。

### 9.4 更新合同元数据

`PATCH /api/v1/contracts/{contract_id}`。权限：`Org Admin | Reviewer`。已归档合同不可修改。

Request Body：`title?: string`, `declared_type?: contract_type|null`, `version: integer`。

Request Example：`{ "title": "2026 年供应商采购合同", "version": 1 }`

Success `200 OK`：返回更新后的 `Contract`。

主要错误：`403 FORBIDDEN`、`404 CONTRACT_NOT_FOUND`、`409 CONTRACT_ARCHIVED`、`409 RESOURCE_VERSION_CONFLICT`。

### 9.5 归档合同

`POST /api/v1/contracts/{contract_id}/archive`。权限：`Org Admin | Reviewer`。无 Body。

归档与审核任务在同一事务边界内检查。若该合同存在状态为
`pending`、`parsing`、`reviewing` 或 `pending_review` 的活动 `ReviewTask`，归档不得写入合同，返回
`409 ACTIVE_REVIEW_EXISTS`；响应不泄露其他组织或无权任务的信息。合同归档不会级联修改任何
`ReviewTask` 或 `ReviewStageRun`。已经处于 `completed`、`failed` 或 `archived` 的任务保持原状态、只读和可追溯，
其历史输入快照不因合同归档而改变。

本契约未定义审核任务取消、任务归档或任务恢复命令，因此本 Phase 不提供这些接口，也不增加相应状态迁移。

Request Example：`{}`

Success `200 OK`：`{ "id": "5a7b9e6b-3e0d-4ae0-9ae8-0e45fcf3be17", "status": "archived", "archived_at": "2026-08-17T05:00:00Z" }`

主要错误：`403 FORBIDDEN`、`404 CONTRACT_NOT_FOUND`、`409 ACTIVE_REVIEW_EXISTS`。

### 9.6 恢复归档合同

`POST /api/v1/contracts/{contract_id}/restore`。权限：`Org Admin`。无 Body。

Request Example：`{}`

Success `200 OK`：`{ "id": "5a7b9e6b-3e0d-4ae0-9ae8-0e45fcf3be17", "status": "active", "archived_at": null }`

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 CONTRACT_NOT_FOUND`、`409 CONTRACT_NOT_ARCHIVED`。

### 9.7 上传合同文件

`POST /api/v1/contracts/{contract_id}/files`。权限：`Org Admin | Reviewer`。需要 `multipart/form-data`、`Idempotency-Key` 和 CSRF。

Request Form：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | binary | 是 | 单个 DOCX/PDF/PNG/JPG/JPEG；数量固定为 1 |
| `make_current` | boolean | 否 | 默认 `true` |
| `external_model_notice_acknowledged` | boolean | 是 | 必须为 `true`；确认界面已告知合同内容将用于千问分类、抽取、风险分析和条款比对 |

Request Example：表单 `file=@采购合同.pdf`, `make_current=true`, `external_model_notice_acknowledged=true`。

Success `201 Created`：返回 `File Object` 和合同文件版本；上传只完成校验、病毒扫描和存储，不自动创建审核。

```json
{ "file": { "id": "9c2e75b3-95d1-4f18-8f8c-65d25358c90e", "original_name": "采购合同.pdf", "media_type": "application/pdf", "size_bytes": 284901, "scan_status": "clean" }, "contract_file_id": "9c86608c-6c82-456f-8958-b65223e33ba3", "version_no": 1, "is_current": true, "external_model_notice_acknowledged_at": "2026-08-17T03:31:00Z" }
```

主要错误：`403 FORBIDDEN`、`404 CONTRACT_NOT_FOUND`、`409 CONTRACT_ARCHIVED`、`413 FILE_TOO_LARGE`、`415 CONTRACT_FILE_UNSUPPORTED`、`422 FILE_CORRUPTED`、`422 EXTERNAL_MODEL_NOTICE_NOT_ACKNOWLEDGED`、`503 ANTIVIRUS_UNAVAILABLE`。

### 9.8 下载原文件

`GET /api/v1/files/{file_id}/download`。权限：能查看所属合同的用户；每次重新校验组织和合同权限。

Query：`disposition=attachment|inline`，默认 `attachment`。无 Body。

Request Example：`GET /api/v1/files/{file_id}/download?disposition=attachment`

Success `200 OK`：二进制流，设置正确 `Content-Type`, `Content-Length`, `Content-Disposition`；不返回 JSON。

主要错误：`404 FILE_NOT_FOUND`（含越权隐藏）、`409 FILE_NOT_READY`、`429 DOWNLOAD_RATE_LIMITED`。

### 9.9 获取文档页面/逻辑块

`GET /api/v1/documents/{document_version_id}/pages/{page_no}`。权限：能查看所属合同的用户。

Path：`document_version_id` UUID，`page_no` 从 1 开始，仅适用于 PDF 和图片的物理页。Query：`include_blocks` boolean，默认 true。

Request Example：`GET /api/v1/documents/{id}/pages/3?include_blocks=true`

Success `200 OK`：

```json
{ "document_version_id": "2c5b0b5d-6c3c-46aa-a9d1-75c5a817d4b1", "document_kind": "pdf", "page_no": 3, "page_count": 18, "width": 612, "height": 792, "text": "...", "image_file_id": "bb9faea0-d5cc-4501-9012-09a44b8204de", "ocr_status": "completed", "ocr_confidence": 0.93, "error_code": null, "error_message": null, "blocks": [{ "id": "48b75611-80fd-49b2-a511-42ea168d66b8", "order_no": 1, "block_type": "paragraph", "paragraph_no": null, "table_path": null, "text": "乙方应承担...", "bbox": null, "source_spans": [] }] }
```

主要错误：`404 DOCUMENT_OR_PAGE_NOT_FOUND`、`409 DOCUMENT_NOT_READY`。DOCX 没有物理页，不能调用此接口。

### 9.10 获取 DOCX 逻辑块

`GET /api/v1/documents/{document_version_id}/blocks`。权限：能查看所属合同的用户。

Path：`document_version_id` UUID。Query：`include_source_spans` boolean，默认 true。该接口返回文档的全部逻辑块，按原始顺序排列；DOCX 块使用 `docx_paragraph` 或 `docx_table_cell` 定位，不返回虚构页码。PDF/图片也可使用该接口读取其已解析块，但页面跳转必须使用 9.9。

Request Example：`GET /api/v1/documents/{id}/blocks?include_source_spans=true`

Success `200 OK`：

```json
{ "document_version_id": "2c5b0b5d-6c3c-46aa-a9d1-75c5a817d4b1", "document_kind": "docx", "page_count": 0, "blocks": [{ "id": "48b75611-80fd-49b2-a511-42ea168d66b8", "order_no": 1, "block_type": "paragraph", "page_no": null, "paragraph_no": 4, "table_path": null, "text": "乙方应承担...", "bbox": null, "source_spans": [{ "document_version_id": "2c5b0b5d-6c3c-46aa-a9d1-75c5a817d4b1", "kind": "docx_paragraph", "page_no": null, "paragraph_no": 4, "table_path": null, "start_offset": 0, "end_offset": 7, "bbox": null, "quote": "乙方应承担..." }] }] }
```

主要错误：`404 DOCUMENT_NOT_FOUND`、`409 DOCUMENT_NOT_READY`。

## 10. Review Task and Result APIs

### 10.1 创建审核任务

`POST /api/v1/contracts/{contract_id}/reviews`。权限：`Org Admin | Reviewer`。需要 `Idempotency-Key`。

Request Body：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `contract_file_id` | UUID | 是 | 已通过校验的合同文件版本 |
| `document_version_id` | UUID | 否 | 已成功解析时可指定；否则由服务端选择/创建 |
| `rule_bundle_version_id` | UUID | 否 | 已发布风险规则版本；为空使用当前组织默认规则集的当前发布版本 |
| `clause_template_version_id` | UUID | 否 | 已发布条款模板版本；为空按合同类型和规范化场景选择默认模板的当前发布版本 |
| `business_scenario` | string | 否 | 模板选择场景；缺省规范为 `standard`，只做合同类型和场景精确匹配，不回退到其他场景 |

客户端不能提交组织 ID、模型密钥、提示词或结果内容。服务端在任务创建时锁定文件、文档、规则、模板、提示词和模型配置快照，并验证所选文件已经记录外部模型告知确认。

Request Example：

```json
{ "contract_file_id": "9c86608c-6c82-456f-8958-b65223e33ba3", "rule_bundle_version_id": "d2f7e5cd-9235-4328-b0b1-7af8dfc5fa99", "clause_template_version_id": "7f4e18e9-2d1e-4b52-8c8c-4d08c8d11120" }
```

Success `202 Accepted`：返回 `ReviewTask`，初始 `status=pending`。响应包含锁定的
`contract_file_id`、可用时的 `document_version_id`、已发布规则/模板版本 ID 和业务场景；配置快照中的
模型密钥、合同正文和提示词正文不返回。

```json
{ "id": "67f0ab0d-cf70-470c-b5e7-92a18d6d73a5", "display_no": "REV-20260817-000045", "contract_id": "5a7b9e6b-3e0d-4ae0-9ae8-0e45fcf3be17", "status": "pending", "progress": 0, "current_stage": "queued", "rule_bundle_version_id": "d2f7e5cd-9235-4328-b0b1-7af8dfc5fa99", "clause_template_version_id": "7f4e18e9-2d1e-4b52-8c8c-4d08c8d11120" }
```

主要错误：`403 FORBIDDEN`、`404 CONTRACT_FILE_NOT_FOUND`、`404 DOCUMENT_NOT_FOUND`、`409 CONTRACT_ARCHIVED`、
`409 ACTIVE_REVIEW_EXISTS`、`409 VERSION_NOT_PUBLISHED`、`409 CONTRACT_FILE_NOT_READY`、
`409 DOCUMENT_NOT_READY`、
`409 DEFAULT_RISK_RULE_BUNDLE_NOT_CONFIGURED`、`409 DEFAULT_CLAUSE_TEMPLATE_NOT_CONFIGURED`、
`409 DEFAULT_VERSION_NOT_APPLICABLE`、`422 EXTERNAL_MODEL_NOTICE_NOT_ACKNOWLEDGED`、
`422 VALIDATION_ERROR`、`429 CONCURRENCY_LIMIT_EXCEEDED`。

### 10.2 获取审核任务

`GET /api/v1/review-tasks/{review_task_id}`。权限：合同可见用户；viewer 需显式授权。

Request：Path `review_task_id` UUID；无 Body。可选 Query `include_stage_runs` boolean，默认 false。

`include_stage_runs=true` 时返回当前任务可见的阶段尝试；阶段事实包含 `stage`、`status`、`attempt_no`、租约心跳
时间和安全错误信息，不返回内部堆栈或外部供应商响应。Viewer 必须对合同具有显式 `read` 授权；平台支持访问
仅可读取，不可创建或重试。

Request Example：`GET /api/v1/review-tasks/67f0ab0d-cf70-470c-b5e7-92a18d6d73a5?include_stage_runs=true`

Success `200 OK`：返回 `ReviewTask`；`failed` 必须有可读 `error_code`/`error_message`，不能暴露内部异常。

```json
{ "id": "67f0ab0d-cf70-470c-b5e7-92a18d6d73a5", "status": "failed", "progress": 42, "current_stage": "risk_analysis", "error_code": "MODEL_OUTPUT_INVALID", "error_message": "模型结果未通过结构化校验，请重试或人工复核。", "stage_runs": [{ "stage": "parsing", "status": "succeeded", "attempt_no": 1 }, { "stage": "risk_analysis", "status": "failed", "attempt_no": 2 }] }
```

主要错误：`404 REVIEW_TASK_NOT_FOUND`、`403 FORBIDDEN`。

### 10.3 重试失败审核

`POST /api/v1/review-tasks/{review_task_id}/retry`。权限：`Org Admin | Reviewer`；仅 `failed` 可调用。需要 `Idempotency-Key`。

Request Body：`{}`；可选 `from_stage?: parsing|classification|extraction|risk_analysis|clause_comparison|report`，默认从第一个失败阶段继续。不得改变已锁定输入版本。成功阶段在输入指纹未变化时复用，
新的 stage attempt 以数据库唯一约束记录。Phase 9A 每个 `ReviewTask` 最多允许 3 次显式 retry；达到上限后返回
`409 RETRY_LIMIT_EXCEEDED`，任务保持 `failed`，不得创建新的 attempt。

Request Example：`{ "from_stage": "risk_analysis" }`

Success `202 Accepted`：

```json
{ "review_task_id": "67f0ab0d-cf70-470c-b5e7-92a18d6d73a5", "status": "pending", "resumed_from_stage": "risk_analysis" }
```

主要错误：`403 FORBIDDEN`、`404 REVIEW_TASK_NOT_FOUND`、`409 INVALID_STATE_TRANSITION`、
`409 INPUT_VERSION_CHANGED`、`409 RETRY_LIMIT_EXCEEDED`、`429 CONCURRENCY_LIMIT_EXCEEDED`。

### 10.4 确认审核完成

`POST /api/v1/review-tasks/{review_task_id}/complete`。权限：`Org Admin | Reviewer`；仅 `pending_review` 可调用。

Request Body：`{ "note?: string" }`；若仍有无证据风险或未处理的必须人工项，服务端拒绝完成。

Request Example：`{ "note": "已完成人工复核" }`

Success `200 OK`：返回 `ReviewTask`，`status=completed`，并保留完成操作者和时间。

```json
{ "id": "67f0ab0d-cf70-470c-b5e7-92a18d6d73a5", "status": "completed", "completed_by": "8b2f8a68-5e4a-4b0a-b6a2-6dce4e0f5a11", "finished_at": "2026-08-17T05:10:00Z" }
```

主要错误：`403 FORBIDDEN`、`404 REVIEW_TASK_NOT_FOUND`、`409 INVALID_STATE_TRANSITION`、`409 UNRESOLVED_REQUIRED_FINDINGS`。

### 10.5 获取审核结果

`GET /api/v1/review-tasks/{review_task_id}/results`。权限：合同可见用户；viewer 只读。

Request Query：`risk_severity?: high|medium|low`, `risk_status?: risk_finding_status`, `clause_status?: clause_comparison_status`, `include_evidence?: boolean`（默认 true）。无 Body。

Request Example：`GET /api/v1/review-tasks/{id}/results?risk_severity=high&include_evidence=true`

Success `200 OK`：

```json
{
  "review_task_id": "67f0ab0d-cf70-470c-b5e7-92a18d6d73a5",
  "classification": { "model_value": "purchase", "current_value": "purchase", "confidence": 0.96, "status": "detected", "evidence": [{ "kind": "pdf_page", "page_no": 1, "quote": "采购合同" }], "version": 1 },
  "extracted_fields": [{ "id": "0a47b8d3-6df8-46c4-a5cb-4c277f7c1c2e", "field_key": "contract_amount", "model_value": { "amount": "100000.00", "currency": "CNY", "tax_included": true }, "current_value": { "amount": "100000.00", "currency": "CNY", "tax_included": true }, "status": "found", "confidence": 0.91, "evidence": [{ "kind": "pdf_page", "page_no": 2, "quote": "合同总价为含税人民币壹拾万元" }], "version": 1 }],
  "risk_findings": [{ "id": "b7c6a5d4-3210-4fed-8abc-1234567890ab", "risk_type": "unlimited_liability", "severity": "high", "title": "责任范围不封顶", "description": "...", "basis": "责任条款未设置上限", "suggestion": "建议约定责任上限。", "confidence": 0.88, "source": "model", "status": "pending_review", "evidence": [{ "kind": "pdf_page", "page_no": 3, "quote": "乙方承担全部且无限的责任" }], "version": 1 }],
  "clause_comparisons": [{ "id": "f2b55477-b6a5-4f31-a5c5-bb58b5ca9138", "clause_key": "payment", "status": "deviated", "contract_text": "验收后付款", "difference_summary": "缺少付款期限", "severity": "medium", "suggestion": "补充付款期限。", "evidence": [{ "kind": "pdf_page", "page_no": 4, "quote": "验收后付款" }], "version": 1 }],
  "summary": { "risk_total": 1, "high": 1, "medium": 0, "low": 0, "warning_total": 1, "unresolved_count": 1 }
}
```

主要错误：`403 FORBIDDEN`、`404 REVIEW_TASK_NOT_FOUND`、`409 RESULTS_NOT_READY`。

### 10.6 修订合同分类

`PATCH /api/v1/contract-classifications/{classification_id}`。权限：`Org Admin | Reviewer`；viewer 不允许。

Request Body：`current_value: contract_type`, `status?: confirmed|corrected|needs_confirmation`, `reason?: string`, `version: integer`。必须保留模型原值；没有证据时不能将风险结果确认。

Request Example：`{ "current_value": "sales", "status": "corrected", "reason": "人工核对合同标题", "version": 1 }`

Success `200 OK`：返回分类及 `version=2`、`edited_by`、`edited_at`。

主要错误：`403 FORBIDDEN`、`404 CLASSIFICATION_NOT_FOUND`、`409 RESOURCE_VERSION_CONFLICT`、`422 INVALID_CONTRACT_TYPE`。

### 10.7 修订抽取字段

`PATCH /api/v1/extracted-fields/{field_id}`。权限：`Org Admin | Reviewer`。

Request Body：`current_value: object|null`, `status: found|not_found|needs_confirmation|confirmed|corrected`, `reason?: string`, `version: integer`。值必须符合该 `field_key` 的 JSON Schema。

Request Example：`{ "current_value": { "amount": "120000.00", "currency": "CNY", "tax_included": true }, "status": "corrected", "reason": "补录附件金额", "version": 1 }`

Success `200 OK`：返回字段、模型值、当前值、证据和新版本。

```json
{ "id": "0a47b8d3-6df8-46c4-a5cb-4c277f7c1c2e", "field_key": "contract_amount", "model_value": { "amount": "100000.00", "currency": "CNY", "tax_included": true }, "current_value": { "amount": "120000.00", "currency": "CNY", "tax_included": true }, "status": "corrected", "version": 2 }
```

主要错误：`403 FORBIDDEN`、`404 FIELD_NOT_FOUND`、`409 RESOURCE_VERSION_CONFLICT`、`422 FIELD_SCHEMA_INVALID`。

### 10.8 修订风险发现

`PATCH /api/v1/risk-findings/{finding_id}`。权限：`Org Admin | Reviewer`。

Request Body：`status: pending_review|confirmed|false_positive|processed`, `title?: string`, `description?: string`, `suggestion?: string`, `reason?: string`, `version: integer`。`confirmed` 必须有证据；严重度和来源不可由客户端任意改写。

Request Example：`{ "status": "confirmed", "reason": "已核对原文", "version": 1 }`

Success `200 OK`：返回风险发现及修订后的 `version`。

```json
{ "id": "b7c6a5d4-3210-4fed-8abc-1234567890ab", "status": "confirmed", "source": "human", "evidence_count": 1, "version": 2 }
```

主要错误：`403 FORBIDDEN`、`404 RISK_FINDING_NOT_FOUND`、`409 RESOURCE_VERSION_CONFLICT`、`422 EVIDENCE_REQUIRED`。

### 10.9 修订条款比对

`PATCH /api/v1/clause-comparisons/{comparison_id}`。权限：`Org Admin | Reviewer`。

Request Body：`status: matched|deviated|missing|uncertain`, `difference_summary?: string`, `suggestion?: string`, `reason?: string`, `version: integer`。`uncertain` 必须进入人工复核，不能自动视为匹配或缺失。

Request Example：`{ "status": "deviated", "difference_summary": "付款期限未明确", "version": 1 }`

Success `200 OK`：返回比对结果、证据和新版本。

主要错误：`403 FORBIDDEN`、`404 CLAUSE_COMPARISON_NOT_FOUND`、`409 RESOURCE_VERSION_CONFLICT`、`422 EVIDENCE_REQUIRED`。

## 11. Risk Rule APIs

规则集和版本属于组织配置。已发布版本不可编辑；修改必须从已发布版本创建新草稿并填写 `change_note`。规则条件仅允许下述白名单 Schema（关键词、正则、金额/日期阈值、字段存在性和逻辑组合），不得提交 Python、SQL、脚本或任意表达式。

规则集和规则版本的成功资源响应均包含服务端根据路径/资源归属确认的 `organization_id`。该字段仅用于展示和客户端上下文同步，客户端不得在 Body、Query 或 Header 中用它改变资源归属；资源路径接口忽略 `X-Organization-ID`。

默认规则集语义：每个组织最多一个默认规则集。第一个成功发布的有效规则集自动成为默认；后续发布不会自动替换默认项。组织管理员通过 11.4 的 `is_default: true` 显式切换，响应返回新的默认标识。发布默认规则集的新版本会原子更新其 `current_published_version_id`。当前默认规则集不能直接停用或取消默认，必须先切换到另一个可用规则集；数据库唯一约束处理并发竞争。没有可用默认规则集时，省略规则版本的审核创建返回 `409 DEFAULT_RISK_RULE_BUNDLE_NOT_CONFIGURED`。

### 11.1 规则集列表

`GET /api/v1/risk-rule-bundles`。权限：`Org Admin | Reviewer`（审核员只读已发布版本）。

Request Query：通用分页，加 `status=active|disabled`、`q`。无 Body。

Request Example：`GET /api/v1/risk-rule-bundles?limit=20`

Success `200 OK`：

```json
{ "items": [{ "id": "5f95fbf7-98fb-4d89-8cd0-4b5d9b1d0e65", "organization_id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "name": "企业风险基线", "current_published_version_id": "d2f7e5cd-9235-4328-b0b1-7af8dfc5fa99", "status": "active", "is_default": true, "version": 3 }], "next_cursor": null, "has_more": false }
```

主要错误：`403 FORBIDDEN`。

### 11.2 创建规则集

`POST /api/v1/risk-rule-bundles`。权限：`Org Admin`。需要 `Idempotency-Key`。

Request Body：`name: string`（必填）。

Request Example：`{ "name": "采购合同风险规则" }`

Success `201 Created`：`{ "id": "5f95fbf7-98fb-4d89-8cd0-4b5d9b1d0e65", "organization_id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "name": "采购合同风险规则", "status": "active", "current_published_version_id": null, "is_default": false, "version": 1 }`

主要错误：`403 ORG_ADMIN_REQUIRED`、`409 RULE_BUNDLE_NAME_CONFLICT`、`422 VALIDATION_ERROR`。

### 11.3 获取规则集及版本

`GET /api/v1/risk-rule-bundles/{bundle_id}`。权限：`Org Admin | Reviewer`。

Request：Path `bundle_id` UUID；Query `include_rules?: boolean` 默认 false。无 Body。

Request Example：`GET /api/v1/risk-rule-bundles/5f95fbf7-98fb-4d89-8cd0-4b5d9b1d0e65?include_rules=true`

Success `200 OK`：返回规则集、版本列表（含 `version_no`, `status`, `change_note`, `effective_at`）和按要求的规则。

```json
{ "id": "5f95fbf7-98fb-4d89-8cd0-4b5d9b1d0e65", "organization_id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "name": "企业风险基线", "current_published_version_id": "d2f7e5cd-9235-4328-b0b1-7af8dfc5fa99", "status": "active", "is_default": true, "version": 3, "versions": [{ "id": "d2f7e5cd-9235-4328-b0b1-7af8dfc5fa99", "organization_id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "version_no": 3, "status": "published", "change_note": "增加数据合规风险", "rule_count": 11 }] }
```

主要错误：`403 FORBIDDEN`、`404 RULE_BUNDLE_NOT_FOUND`。

### 11.4 更新/停用规则集

`PATCH /api/v1/risk-rule-bundles/{bundle_id}`。权限：`Org Admin`。

Request Body：`name?: string`, `status?: active|disabled`, `is_default?: boolean`, `version: integer`。该动作只修改规则集逻辑身份；规则内容修改必须创建新版本。`is_default: true` 是显式切换默认规则集的请求，目标必须为 active 且已有当前发布版本；`is_default: false` 不能直接取消当前默认项，必须先把另一个可用规则集设为默认。

Request Example：`{ "is_default": true, "version": 2 }`

Success `200 OK`：`{ "id": "5f95fbf7-98fb-4d89-8cd0-4b5d9b1d0e65", "organization_id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "name": "企业风险基线", "status": "active", "current_published_version_id": "d2f7e5cd-9235-4328-b0b1-7af8dfc5fa99", "is_default": true, "version": 3 }`

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 RULE_BUNDLE_NOT_FOUND`、`409 RESOURCE_VERSION_CONFLICT`、`409 RULE_BUNDLE_NAME_CONFLICT`、`409 DEFAULT_RULE_BUNDLE_REQUIRED`、`409 DEFAULT_RULE_BUNDLE_CONFLICT`。

### 11.5 创建规则草稿版本

`POST /api/v1/risk-rule-bundles/{bundle_id}/versions`。权限：`Org Admin`。需要 `Idempotency-Key`。

Request Body：`change_note: string`（必填）、`source_version_id?: UUID`、`rules: RiskRule[]`（必填，1-200 条；可从来源版本复制后修改）。

`RiskRule` 字段：`rule_key: string`、`risk_type: string`、`engine: deterministic|model`、`condition: RiskRuleCondition`、`severity: high|medium|low`、`suggestion: string`、`enabled: boolean`。同一版本的 `rule_key` 必须唯一；请求中的额外字段返回 422。

`RiskRuleCondition` 是按 `operator` 判别的封闭对象，只允许对应行列出的字段；字符串字段均不得为空白。条件字段必须来自下表的操作符专用白名单，不接受未声明的字段键。逻辑组合从根条件计最多 5 层，每个 `all/any` 含 1 到 20 个子条件：

| `operator` | 其余字段 | 约束 |
| --- | --- | --- |
| `keyword` | `field: contract_text`, `value: string` | 只对规范化合同全文执行关键词匹配 |
| `regex` | `field: contract_text`, `pattern: string` | pattern 最长 1000 字符且必须为有效正则 |
| `amount_threshold` | `field: contract_amount`, `comparison: gt\|gte\|lt\|lte\|eq`, `value: decimal string` | 有限十进制值，不接受 JSON 浮点数、NaN 或 Infinity |
| `date_threshold` | `field: signing_date`, `comparison: gt\|gte\|lt\|lte\|eq`, `value: YYYY-MM-DD` | 严格日历日期 |
| `field_exists` / `field_missing` | `field: parties\|signing_date\|contract_amount\|performance_period\|dispute_resolution\|payment_terms\|auto_renewal\|acceptance_standard\|intellectual_property\|data_compliance\|force_majeure` | 仅检查 5.6 定义的核心抽取字段和内置基线字段是否存在；无其他字段 |
| `all` / `any` | `conditions: RiskRuleCondition[]` | 1 到 20 个子条件 |
| `not` | `condition: RiskRuleCondition` | 恰好一个子条件 |
| `semantic` | 无 | 仅允许 `engine=model` |

Request Example：

```json
{ "source_version_id": "d2f7e5cd-9235-4328-b0b1-7af8dfc5fa99", "change_note": "增加数据合规风险", "rules": [{ "rule_key": "data_compliance_missing", "risk_type": "data_compliance", "engine": "deterministic", "condition": { "operator": "field_missing", "field": "data_compliance" }, "severity": "high", "suggestion": "补充数据合规责任条款。", "enabled": true }] }
```

Success `201 Created`：返回 `status=draft` 的完整版本（含服务端确认的 `organization_id`）；草稿不改变默认标识，只有成功发布时才按默认规则处理。

```json
{ "id": "ec1d23c1-06a4-4fd6-9b16-ccff9811c2d8", "organization_id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "bundle_id": "5f95fbf7-98fb-4d89-8cd0-4b5d9b1d0e65", "version_no": 4, "status": "draft", "change_note": "增加数据合规风险", "rules": [{ "rule_key": "data_compliance_missing", "severity": "high", "enabled": true }] }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 RULE_BUNDLE_NOT_FOUND`、`409 RULE_BUNDLE_DISABLED`、`409 VERSION_SOURCE_INVALID`、`422 VALIDATION_ERROR`、`422 RULE_SCHEMA_INVALID`。

### 11.6 获取规则版本

`GET /api/v1/risk-rule-bundle-versions/{version_id}`。权限：`Org Admin | Reviewer`；审核员只可读已发布版本。

Request：Path `version_id` UUID；无 Body。

Request Example：`GET /api/v1/risk-rule-bundle-versions/{version_id}`

Success `200 OK`：返回完整不可变（发布版）或可编辑（草稿）规则版本，并包含服务端确认的 `organization_id`、所属规则集的 `is_default`、`current_published_version_id` 标识和草稿资源 `version`；审核员访问草稿仍返回 403。

主要错误：`403 FORBIDDEN`、`404 RULE_VERSION_NOT_FOUND`。

### 11.7 修改规则草稿

`PATCH /api/v1/risk-rule-bundle-versions/{version_id}`。权限：`Org Admin`；仅 `draft` 可修改。

Request Body：`rules?: RiskRule[]`, `change_note?: string`, `version: integer`。版本号是草稿资源乐观锁。

Request Example：`{ "rules": [{ "rule_key": "unlimited_liability", "risk_type": "unlimited_liability", "engine": "model", "condition": { "operator": "semantic" }, "severity": "high", "suggestion": "约定责任上限。", "enabled": true }], "version": 1 }`

Success `200 OK`：返回新草稿版本。修改草稿不会改变默认规则集或任何已发布版本。

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 RULE_VERSION_NOT_FOUND`、`409 VERSION_ALREADY_PUBLISHED`、`409 RESOURCE_VERSION_CONFLICT`、`422 VALIDATION_ERROR`、`422 RULE_SCHEMA_INVALID`。

### 11.8 发布规则版本

`POST /api/v1/risk-rule-bundle-versions/{version_id}/publish`。权限：`Org Admin`。

Request Body：严格空对象 `{}`。发布前校验规则 Schema；发布后不可编辑，已有审核任务继续引用旧版本。

Request Example：`POST /api/v1/risk-rule-bundle-versions/{version_id}/publish` with body `{}`

Success `200 OK`：`{ "id": "ec1d23c1-06a4-4fd6-9b16-ccff9811c2d8", "organization_id": "1d2f3a4b-5c6d-7e8f-9012-345678901234", "status": "published", "effective_at": "2026-08-17T06:00:00Z", "published_by": "...", "is_default": true, "current_published_version_id": "ec1d23c1-06a4-4fd6-9b16-ccff9811c2d8" }`。首次成功发布时 `is_default=true`；其他规则集发布时保持原默认项不变；发布默认规则集的新版本只更新该集的当前发布版本。

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 RULE_VERSION_NOT_FOUND`、`409 VERSION_NOT_DRAFT`、`409 RULE_BUNDLE_DISABLED`、`409 DEFAULT_RULE_BUNDLE_CONFLICT`、`422 RULE_SCHEMA_INVALID`。

## 12. Clause Template APIs

条款模板与版本遵循同一版本原则：发布版本不可编辑，审核任务创建时锁定版本。每个条款至少有合同类型、业务场景、条款编号、名称、标准文本、允许偏差、风险等级、适用条件、建议文本、启用状态和顺序。

默认模板语义：每个组织、合同类型和规范化业务场景组合最多一个默认模板。`business_scenario` 缺省或为空白时规范为 `standard`；默认选择只做合同类型和场景精确匹配，不回退到其他场景。每个组合下第一个成功发布的有效模板自动成为默认；后续发布不会自动替换。组织管理员通过 12.4 的 `is_default: true` 显式切换，响应返回新的默认标识。发布默认模板的新版本会原子更新其 `current_published_version_id`。当前默认模板不能直接停用或取消默认，必须先切换到同一合同类型和场景下另一个可用模板；数据库唯一约束处理并发竞争。没有对应默认模板时，省略模板版本的审核创建返回 `409 DEFAULT_CLAUSE_TEMPLATE_NOT_CONFIGURED`。

### 12.1 模板列表

`GET /api/v1/clause-templates`。权限：`Org Admin | Reviewer`（审核员只读已发布版本）。

Request Query：通用分页，加 `contract_type`, `business_scenario`, `status`, `q`。

Request Example：`GET /api/v1/clause-templates?contract_type=purchase&status=published`

Success `200 OK`：

```json
{ "items": [{ "id": "a82c9d51-feb3-43b4-9a0d-9e3c4edec0c1", "name": "采购合同基线", "contract_type": "purchase", "business_scenario": "standard", "current_published_version_id": "7f4e18e9-2d1e-4b52-8c8c-4d08c8d11120", "status": "active", "is_default": true }], "next_cursor": null, "has_more": false }
```

主要错误：`403 FORBIDDEN`。

### 12.2 创建模板

`POST /api/v1/clause-templates`。权限：`Org Admin`。需要 `Idempotency-Key`。

Request Body：`name: string`, `contract_type: contract_type`（不得为 `other`）, `business_scenario?: string`。场景缺省或为空白时服务端规范为 `standard`。

Request Example：`{ "name": "采购合同基线", "contract_type": "purchase", "business_scenario": "standard" }`

Success `201 Created`：`{ "id": "a82c9d51-feb3-43b4-9a0d-9e3c4edec0c1", "name": "采购合同基线", "contract_type": "purchase", "business_scenario": "standard", "status": "active", "current_published_version_id": null }`

主要错误：`403 ORG_ADMIN_REQUIRED`、`409 TEMPLATE_NAME_CONFLICT`、`422 VALIDATION_ERROR`。

### 12.3 获取模板及版本

`GET /api/v1/clause-templates/{template_id}`。权限：`Org Admin | Reviewer`。

Request：Path `template_id` UUID；Query `include_clauses?: boolean` 默认 false。

Request Example：`GET /api/v1/clause-templates/a82c9d51-feb3-43b4-9a0d-9e3c4edec0c1?include_clauses=true`

Success `200 OK`：返回模板、版本列表和可选标准条款。

```json
{ "id": "a82c9d51-feb3-43b4-9a0d-9e3c4edec0c1", "name": "采购合同基线", "contract_type": "purchase", "business_scenario": "standard", "status": "active", "is_default": true, "versions": [{ "id": "7f4e18e9-2d1e-4b52-8c8c-4d08c8d11120", "version_no": 1, "status": "published", "clauses": [{ "clause_key": "payment", "name": "付款", "severity": "medium", "enabled": true }] }] }
```

主要错误：`403 FORBIDDEN`、`404 TEMPLATE_NOT_FOUND`。

### 12.4 更新/停用模板

`PATCH /api/v1/clause-templates/{template_id}`。权限：`Org Admin`。

Request Body：`name?: string`, `business_scenario?: string`, `status?: active|disabled`, `is_default?: boolean`, `version: integer`。场景在写入前规范化，条款正文修改必须创建新版本；`is_default: true` 是显式切换同一合同类型和规范化场景默认模板的请求，目标必须为 active 且已有当前发布版本；`is_default: false` 不能直接取消当前默认项，必须先切换另一个模板。停用后不能作为新审核的默认模板，历史任务仍可读取。

Request Example：`{ "is_default": true, "version": 1 }`

Success `200 OK`：`{ "id": "a82c9d51-feb3-43b4-9a0d-9e3c4edec0c1", "name": "采购合同基线", "contract_type": "purchase", "business_scenario": "standard", "status": "active", "current_published_version_id": "7f4e18e9-2d1e-4b52-8c8c-4d08c8d11120", "is_default": true, "version": 2 }`

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 TEMPLATE_NOT_FOUND`、`409 RESOURCE_VERSION_CONFLICT`、`409 DEFAULT_CLAUSE_TEMPLATE_REQUIRED`、`409 DEFAULT_CLAUSE_TEMPLATE_CONFLICT`。

### 12.5 创建模板草稿版本

`POST /api/v1/clause-templates/{template_id}/versions`。权限：`Org Admin`。需要 `Idempotency-Key`。

Request Body：`change_note: string`, `source_version_id?: UUID`, `clauses: StandardClause[]`。

`StandardClause` 字段：`clause_key`, `name`, `standard_text`, `allowed_deviation`, `severity`, `applicability`, `suggestion`, `enabled`, `order_no`。

Request Example：

```json
{ "change_note": "补充付款期限", "clauses": [{ "clause_key": "payment", "name": "付款", "standard_text": "付款应在验收后 30 日内完成。", "allowed_deviation": "期限可协商但必须明确", "severity": "medium", "applicability": {}, "suggestion": "补充付款期限。", "enabled": true, "order_no": 1 }] }
```

Success `201 Created`：返回 `draft` 版本和完整条款；草稿不改变默认标识，只有成功发布时才按组合默认规则处理。

```json
{ "id": "b5be4d02-7c0b-4d4f-bd83-5e3ea9e204b2", "template_id": "a82c9d51-feb3-43b4-9a0d-9e3c4edec0c1", "version_no": 2, "status": "draft", "change_note": "补充付款期限", "clauses": [{ "clause_key": "payment", "enabled": true }] }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 TEMPLATE_NOT_FOUND`、`409 VERSION_SOURCE_INVALID`、`422 CLAUSE_SCHEMA_INVALID`。

### 12.6 获取模板版本

`GET /api/v1/clause-template-versions/{version_id}`。权限：`Org Admin | Reviewer`；审核员只读已发布版本。

Request：Path `version_id` UUID；无 Body。

Request Example：`GET /api/v1/clause-template-versions/{version_id}`

Success `200 OK`：返回版本、条款、发布信息和 `change_note`，并包含所属模板的 `is_default` 标识；审核员只可获取已发布版本。

主要错误：`403 FORBIDDEN`、`404 TEMPLATE_VERSION_NOT_FOUND`。

### 12.7 修改模板草稿

`PATCH /api/v1/clause-template-versions/{version_id}`。权限：`Org Admin`；仅 `draft` 可修改。

Request Body：`clauses?: StandardClause[]`, `change_note?: string`, `version: integer`。

Request Example：`{ "clauses": [{ "clause_key": "payment", "name": "付款", "standard_text": "验收后 30 日内付款", "allowed_deviation": "", "severity": "medium", "applicability": {}, "suggestion": "明确期限", "enabled": true, "order_no": 1 }], "version": 1 }`

Success `200 OK`：返回更新后的草稿。修改草稿不会改变默认模板或任何已发布版本。

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 TEMPLATE_VERSION_NOT_FOUND`、`409 VERSION_ALREADY_PUBLISHED`、`409 RESOURCE_VERSION_CONFLICT`、`422 CLAUSE_SCHEMA_INVALID`。

### 12.8 发布模板版本

`POST /api/v1/clause-template-versions/{version_id}/publish`。权限：`Org Admin`。

Request Body：`{}`。

Request Example：`POST /api/v1/clause-template-versions/{version_id}/publish` with body `{}`

Success `200 OK`：`{ "id": "b5be4d02-7c0b-4d4f-bd83-5e3ea9e204b2", "status": "published", "effective_at": "2026-08-17T06:10:00Z", "published_by": "...", "is_default": true, "current_published_version_id": "b5be4d02-7c0b-4d4f-bd83-5e3ea9e204b2" }`。首次成功发布时 `is_default=true`；其他同合同类型/场景模板发布时保持原默认项不变；发布默认模板的新版本只更新该模板的当前发布版本。

主要错误：`403 ORG_ADMIN_REQUIRED`、`404 TEMPLATE_VERSION_NOT_FOUND`、`409 VERSION_NOT_DRAFT`、`409 DEFAULT_CLAUSE_TEMPLATE_CONFLICT`、`422 CLAUSE_SCHEMA_INVALID`。

## 13. Warning APIs

预警是风险/条款/字段/分类结果的运营化事件，不因审核任务完成而自动消失。高风险默认生成；中风险和人工复核预警由组织设置控制。活动预警按任务、风险类型和原文位置去重。

### 13.1 预警列表

`GET /api/v1/warnings`。权限：`Org Admin | Reviewer | authorized Viewer`；viewer 只读授权合同的预警。

Request Query：通用分页，加 `status`, `severity`, `contract_type`, `assignee_id`, `risk_type`, `triggered_from`, `triggered_to`；排序允许 `triggered_at`, `priority`, `due_at`。

Request Example：`GET /api/v1/warnings?status=pending_confirmation&severity=high&limit=20`

Success `200 OK`：

```json
{ "items": [{ "id": "4e0a17a5-93e3-48c6-8b0e-2b88d2eb7d4a", "contract_id": "5a7b9e6b-3e0d-4ae0-9ae8-0e45fcf3be17", "review_task_id": "67f0ab0d-cf70-470c-b5e7-92a18d6d73a5", "severity": "high", "status": "pending_confirmation", "priority": "high", "assignee_id": null, "triggered_at": "2026-08-17T03:34:00Z" }], "next_cursor": null, "has_more": false, "summary": { "unprocessed_count": 1, "high_count": 1 } }
```

主要错误：`401 AUTHENTICATION_REQUIRED`、`422 INVALID_FILTER`。

### 13.2 预警详情

`GET /api/v1/warnings/{warning_id}`。权限：预警所属合同可见用户。

Request：Path `warning_id` UUID；无 Body。

Request Example：`GET /api/v1/warnings/4e0a17a5-93e3-48c6-8b0e-2b88d2eb7d4a`

Success `200 OK`：返回关联风险/条款/字段、责任人、截止时间、主证据定位和完整事件时间线。

```json
{ "id": "4e0a17a5-93e3-48c6-8b0e-2b88d2eb7d4a", "trigger_type": "high_risk", "severity": "high", "status": "pending_confirmation", "risk_finding_id": "b7c6a5d4-3210-4fed-8abc-1234567890ab", "assignee": null, "due_at": null, "resolution": null, "evidence": [{ "kind": "pdf_page", "page_no": 3, "quote": "乙方承担全部且无限的责任" }], "events": [{ "event_type": "created", "to_status": "pending_confirmation", "actor_id": null, "created_at": "2026-08-17T03:34:00Z" }] }
```

主要错误：`404 WARNING_NOT_FOUND`（含越权隐藏）。

### 13.3 预警事件

`POST /api/v1/warnings/{warning_id}/events`。权限：`Org Admin | Reviewer`；viewer 不允许。需要 CSRF。

Request Body：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `type` | `warning_event_type` | 是 | 业务动作 |
| `note` | string | 视动作 | `note`, `assign`, `resolve`, `close` 等可要求说明 |
| `assignee_id` | UUID | `assign` 必填 | 必须是同组织审核员 |
| `due_at` | datetime/null | 否 | 截止时间 |
| `resolution` | string | `close` 必填 | 关闭依据；或提交 `revision_id` |
| `revision_id` | UUID | `close` 二选一 | 关联人工修订记录 |

Request Example：`{ "type": "assign", "assignee_id": "8b2f8a68-5e4a-4b0a-b6a2-6dce4e0f5a11", "due_at": "2026-08-20T09:00:00Z", "note": "请复核责任上限" }`

Success `201 Created`：

```json
{ "event_id": "7ca9e0e7-4567-4a32-9e5d-69c39bb69121", "event_type": "assign", "from_status": "pending_confirmation", "to_status": "pending_confirmation", "assignee_id": "8b2f8a68-5e4a-4b0a-b6a2-6dce4e0f5a11", "created_at": "2026-08-17T05:00:00Z" }
```

主要错误：`403 FORBIDDEN`、`404 WARNING_NOT_FOUND`、`409 INVALID_STATE_TRANSITION`、`422 ACTION_FIELD_REQUIRED`。`false_positive` 将预警置为 `ignored`，并将关联风险标为 `false_positive`；`close` 必须有结论或修订引用；组织管理员才可重新打开 `ignored/closed`。

## 14. Notification APIs

业务预警首期只实现站内通知；通知投递失败记录在通知资源中，不回滚预警。SMTP 仅用于身份邀请和密码重置，不属于本模块；风险预警邮件和企业微信仅保留适配边界。

### 14.1 通知列表

`GET /api/v1/notifications`。权限：`Authenticated User`，仅返回当前用户通知。

Request Query：通用分页，加 `status=unread|read`, `warning_id`；排序允许 `created_at`。

Request Example：`GET /api/v1/notifications?status=unread&limit=20`

Success `200 OK`：

```json
{ "items": [{ "id": "f11c64c8-1c7d-4f80-8c1a-8de7f3c0a5a1", "warning_id": "4e0a17a5-93e3-48c6-8b0e-2b88d2eb7d4a", "channel": "in_app", "status": "unread", "title": "发现高风险合同条款", "body": "请复核责任范围不封顶风险。", "created_at": "2026-08-17T03:34:05Z" }], "next_cursor": null, "has_more": false }
```

主要错误：`401 AUTHENTICATION_REQUIRED`。

### 14.2 标记通知已读

`POST /api/v1/notifications/{notification_id}/read`。权限：通知所属用户。

Request Body：`{}`。

Request Example：`POST /api/v1/notifications/{notification_id}/read` with body `{}`

Success `200 OK`：`{ "id": "f11c64c8-1c7d-4f80-8c1a-8de7f3c0a5a1", "status": "read", "read_at": "2026-08-17T05:01:00Z" }`

主要错误：`404 NOTIFICATION_NOT_FOUND`（含他人通知隐藏）。重复调用幂等。

### 14.3 未读数量

`GET /api/v1/notifications/unread-count`。权限：`Authenticated User`。

Request：无参数。Success `200 OK`：`{ "unread_count": 3 }`。

Request Example：`GET /api/v1/notifications/unread-count`

主要错误：`401 AUTHENTICATION_REQUIRED`。

## 15. Report APIs

### 15.1 生成报告

`POST /api/v1/review-tasks/{review_task_id}/reports`。权限：`Org Admin | Reviewer`；任务至少为 `pending_review` 或 `completed`。需要 `Idempotency-Key`。

Request Body：`format: html|pdf`（必填）。HTML 在线报告和 PDF 导出均为第一阶段必备能力，使用同一份不可变报告快照。

Request Example：`{ "format": "html" }`

Success `202 Accepted`：

```json
{ "id": "caef1f5b-7ae1-48ad-bb8e-1b12f311c58f", "review_task_id": "67f0ab0d-cf70-470c-b5e7-92a18d6d73a5", "format": "html", "status": "generating" }
```

主要错误：`403 FORBIDDEN`、`404 REVIEW_TASK_NOT_FOUND`、`409 REPORT_ALREADY_GENERATING`、`429 CONCURRENCY_LIMIT_EXCEEDED`、`503 REPORT_RENDERER_UNAVAILABLE`。

### 15.2 获取报告

`GET /api/v1/reports/{report_id}`。权限：报告所属合同可见用户。

Request：Path `report_id` UUID。无 Body。

Request Example：`GET /api/v1/reports/{report_id}`

Success `200 OK`：

```json
{ "id": "caef1f5b-7ae1-48ad-bb8e-1b12f311c58f", "display_no": "RPT-20260817-000009", "review_task_id": "67f0ab0d-cf70-470c-b5e7-92a18d6d73a5", "format": "html", "status": "ready", "template_version": "report-v1", "generated_at": "2026-08-17T05:20:00Z", "download_available": true, "error_code": null }
```

主要错误：`404 REPORT_NOT_FOUND`、`403 FORBIDDEN`。

### 15.3 下载/在线预览报告

`GET /api/v1/reports/{report_id}/download`。权限：报告所属合同可见用户；每次重新授权。

Query：`disposition=attachment|inline`，默认 `attachment`。无 Body。

Request Example：`GET /api/v1/reports/{report_id}/download?disposition=inline`

Success `200 OK`：返回 HTML 或 PDF 二进制流，并设置安全 `Content-Type`、`Content-Disposition` 和 CSP；服务端使用不可变报告快照。

主要错误：`404 REPORT_NOT_FOUND`、`409 REPORT_NOT_READY`、`410 REPORT_EXPIRED`、`429 DOWNLOAD_RATE_LIMITED`。

## 16. Feedback APIs

### 16.1 提交反馈/标注

`POST /api/v1/feedback`。权限：`Org Admin | Reviewer`。需要 `Idempotency-Key`。

Request Body：

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `review_task_id` | UUID | 是 | 所属审核任务 |
| `subject_type` | `classification|extracted_field|risk_finding|clause_comparison` | 是 | 被标注对象类型 |
| `subject_id` | UUID | 是 | 被标注对象 |
| `label` | `feedback_label` | 是 | 正确/错误/修改/忽略 |
| `corrected_value` | object|null | `modified` 时必填 | 人工结果 |
| `note` | string | 否 | 说明 |

Request Example：`{ "review_task_id": "67f0ab0d-cf70-470c-b5e7-92a18d6d73a5", "subject_type": "risk_finding", "subject_id": "b7c6a5d4-3210-4fed-8abc-1234567890ab", "label": "incorrect", "note": "责任条款有上限" }`

Success `201 Created`：

```json
{ "id": "e7dc3492-1d5f-4b6e-a762-5232471c8a12", "subject_type": "risk_finding", "subject_id": "b7c6a5d4-3210-4fed-8abc-1234567890ab", "label": "incorrect", "created_by": "8b2f8a68-5e4a-4b0a-b6a2-6dce4e0f5a11", "created_at": "2026-08-17T05:30:00Z" }
```

主要错误：`403 FORBIDDEN`、`404 SUBJECT_NOT_FOUND`、`409 SUBJECT_ORGANIZATION_MISMATCH`、`422 FEEDBACK_SCHEMA_INVALID`。

### 16.2 反馈统计

`GET /api/v1/feedback/summary`。权限：`Org Admin`。

Request Query：`contract_type?`, `rule_bundle_version_id?`, `model_version?`, `created_from?`, `created_to?`；支持通用分页不适用，返回聚合结果。

Request Example：`GET /api/v1/feedback/summary?contract_type=purchase`

Success `200 OK`：

```json
{ "filters": { "contract_type": "purchase" }, "counts": { "correct": 42, "incorrect": 5, "modified": 9, "ignored": 3 }, "by_risk_type": [{ "risk_type": "unlimited_liability", "incorrect": 2, "modified": 1 }] }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`422 INVALID_FILTER`。

## 17. Audit, Operations and Health APIs

### 17.1 组织审计日志

`GET /api/v1/audit-logs`。权限：`Org Admin`；只查询当前组织，禁止修改或删除。

Request Query：通用分页，加 `action`, `resource_type`, `actor_id`, `created_from`, `created_to`；排序允许 `created_at`。

Request Example：`GET /api/v1/audit-logs?action=warning_event&limit=20`

Success `200 OK`：`CursorPage<AuditLog>`。`before_summary`/`after_summary` 只包含必要摘要，不含合同正文、密码、Cookie、令牌和密钥。

```json
{ "items": [{ "id": "be11af77-7fcf-458a-8a8b-4e4cfe2c3bb8", "action": "warning_event", "resource_type": "warning", "resource_id": "4e0a17a5-93e3-48c6-8b0e-2b88d2eb7d4a", "actor_id": "8b2f8a68-5e4a-4b0a-b6a2-6dce4e0f5a11", "request_id": "req_01J...", "created_at": "2026-08-17T05:00:00Z" }], "next_cursor": null, "has_more": false }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`422 INVALID_FILTER`。

### 17.2 平台审计日志

`GET /api/v1/platform/audit-logs`。权限：`Platform Admin`；支持跨组织查询，禁止修改。

Request Query：通用分页，加 `organization_id`, `action`, `resource_type`, `actor_id`, `created_from`, `created_to`。

Request Example：`GET /api/v1/platform/audit-logs?organization_id=1d2f3a4b-5c6d-7e8f-9012-345678901234`

Success `200 OK`：与 17.1 相同的 `CursorPage<AuditLog>`。

Response Example：`{ "items": [], "next_cursor": null, "has_more": false }`

主要错误：`403 PLATFORM_ADMIN_REQUIRED`、`422 INVALID_FILTER`。

### 17.3 审核运营统计

`GET /api/v1/organizations/{organization_id}/metrics/reviews`。权限：`Org Admin`。属于阶段三运营能力；未启用时返回 `501 METRICS_NOT_ENABLED`，不改变核心审核 API。

Request Query：`from`、`to`（datetime，必填）、`contract_type?`。不分页。

Request Example：`GET /api/v1/organizations/{organization_id}/metrics/reviews?from=2026-08-01T00:00:00Z&to=2026-08-17T00:00:00Z`

Success `200 OK`：

```json
{ "from": "2026-08-01T00:00:00Z", "to": "2026-08-17T00:00:00Z", "review_count": 28, "completed_count": 23, "failed_count": 2, "average_duration_ms": 124000, "parse_failure_rate": 0.04, "model_failure_rate": 0.02, "manual_edit_rate": 0.31 }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`422 INVALID_DATE_RANGE`、`501 METRICS_NOT_ENABLED`。

### 17.4 预警运营统计

`GET /api/v1/organizations/{organization_id}/metrics/warnings`。权限：`Org Admin`。阶段三能力。

Request Query：`from`、`to`（必填）、`risk_type?`, `severity?`。

Request Example：`GET /api/v1/organizations/{organization_id}/metrics/warnings?from=2026-08-01T00:00:00Z&to=2026-08-17T00:00:00Z`

Success `200 OK`：

```json
{ "from": "2026-08-01T00:00:00Z", "to": "2026-08-17T00:00:00Z", "created_count": 35, "unprocessed_count": 7, "closed_count": 20, "closure_rate": 0.57, "false_positive_rate": 0.09, "average_unprocessed_duration_ms": 86400000, "by_risk_type": [{ "risk_type": "unlimited_liability", "count": 8 }] }
```

主要错误：`403 ORG_ADMIN_REQUIRED`、`422 INVALID_DATE_RANGE`、`501 METRICS_NOT_ENABLED`。

### 17.5 存活检查

`GET /api/v1/health/live`。权限：`Public/Internal`，反向代理和编排系统调用；不泄露依赖细节。

Request：无参数。Request Example：`GET /api/v1/health/live`。Success `200 OK`：`{ "status": "ok" }`。主要错误：`503 SERVICE_UNAVAILABLE`。

### 17.6 就绪检查

`GET /api/v1/health/ready`。权限：`Internal`，不对公网开放。

Request：无参数。Request Example：`GET /api/v1/health/ready`。Success `200 OK`：`{ "status": "ready", "database": "ok", "configuration": "ok" }`。千问短暂不可用不使 API 进程失去就绪；主要错误：`503 SERVICE_NOT_READY`，不得包含密钥或连接串。

## 18. 业务流程和契约边界

### 18.1 首期浏览器流程

```text
POST /contracts
  -> POST /contracts/{id}/files
  -> POST /contracts/{id}/reviews (202)
  -> GET /review-tasks/{id} 轮询（建议首轮 2 秒并退避）
  -> GET /review-tasks/{id}/results
  -> GET /warnings / POST /warnings/{id}/events
  -> POST /review-tasks/{id}/complete
  -> POST /review-tasks/{id}/reports (202)
  -> GET /reports/{id}/download
```

需求文档流程图把“创建审核任务”写在“上传合同”之前；架构的资源接口和数据约束要求先有合同文件，再创建审核任务。本契约采用后者的三步资源流程，避免审核任务引用不存在的文件。若产品必须支持单请求上传并创建任务，应新增明确的聚合接口并更新本文件，客户端不得自行拼接。

### 18.2 异步和重试

审核、报告生成和通知投递由 Worker 执行；API 只返回数据库事实状态。Worker 的超时、千问 429/5xx、OCR 低置信度、非法 JSON、通知失败和报告失败分别写入任务/页面/通知/报告状态；API 不返回伪造结论。`retry` 复用输入版本和成功阶段的指纹，人工选择重新审核则创建新的 `review_task`。

### 18.3 删除、归档和历史版本

合同使用 archive/restore，不提供物理 `DELETE /contracts/{id}`。规则/模板发布版本、报告快照、人工修订、预警事件、反馈和审计日志不提供删除接口。文件进入软删除和保留期清理流程；被历史审核、报告或审计引用的版本在保留期内不可物理删除。

合同和报告默认保留 180 天，审计日志保留 365 天；生产应用日志保留 30 天，本地开发日志保留 7 天。清理任务必须先检查历史引用并写入审计日志。

## 19. 需求-架构一致性检查

| 检查项 | 结果 |
| --- | --- |
| 用户角色 | 一致：平台管理员、组织管理员、审核员、业务查看者；审核员访问本组织全部合同，viewer 仅访问显式授权合同 |
| 组织隔离 | 一致：客户端不提交可信组织归属，后端按会话、成员和资源组织复核 |
| 认证 | 一致：不透明 Cookie + Argon2id + CSRF；没有 JWT 或 Refresh Token |
| 核心流程 | 需求和架构存在顺序表述差异；本契约已固定为“合同 -> 文件 -> 审核任务”，不提供单请求聚合上传 |
| 任务/预警状态 | 一致；英文 API 值与中英文说明一一对应，严格使用本文件状态机 |
| 分页 | 采用架构明确的 cursor/limit，不引入需求示例中的 page/page_size |
| 文件能力 | 一致支持 DOCX/PDF/PNG/JPG/JPEG、MIME/签名/病毒检查、页面和证据定位；默认 20 MiB、100 页、组织并发审核 3 个 |
| 规则/模板版本 | 一致：发布后不可变，审核任务锁定版本 |
| 外部模型/通知 | 浏览器不直接调用千问；SMTP 仅发送邀请/密码重置，业务预警首期仅站内通知，不加入企业微信或 OAuth |
| 平台临时支持 | 已补充组织管理员授权、最长 4 小时、只读 JSON、禁止下载和完整审计规则 |
| 报告 | 产品确认第一阶段同时交付 HTML 和 PDF；该决定覆盖原分阶段建议，二者使用同一报告快照 |
| 运营指标 | 组织级聚合接口已冻结，第三阶段启用；内部 Prometheus `/metrics` 不对公网开放 |
| PostgreSQL | 需求允许开发环境 MySQL，但架构明确统一 PostgreSQL；该技术选择不改变 API 字段 |

架构中有但需求未逐项命名的接口（游标、幂等键、乐观锁、健康检查、版本详情）均有架构数据一致性或运行要求支撑；本契约没有暴露 Worker、Redis、ModelGateway、OCR 或 FileStore 内部接口。

## 20. 已确认的产品与部署基线

| 项目 | 已确认决策 |
| --- | --- |
| 文件与并发 | 默认单文件 20 MiB、最多 100 页、每组织同时审核 3 个任务 |
| 千问配置 | 模型名由环境变量注入；超时 60 秒；瞬时错误最多重试 3 次；记录 token 和费用，不设硬预算 |
| OCR | 低置信度阈值 0.80；低于阈值必须提示人工复核 |
| 保留期 | 合同/报告 180 天，审计日志 365 天，生产应用日志 30 天，本地开发日志 7 天 |
| 认证邮件 | 邀请和密码重置通过 SMTP；风险预警不发送邮件 |
| 审核员范围 | 可查看和处理本组织全部合同 |
| 平台临时支持 | 组织管理员授权，最长 4 小时，只读 JSON，禁止修改和下载，全程审计 |
| 模型覆盖 | 组织不能覆盖平台模型配置 |
| 报告 | 第一阶段同时支持 HTML 在线报告和 PDF 导出 |
| 运营指标 | 第三阶段启用任务、解析、模型、人工修改和预警完整指标 |
| 部署与数据 | 企业私有服务器单机 Docker Compose；不接入 SSO 或外部风险预警通知；评测仅使用已授权脱敏合同或公开合同 |

上传前必须向用户展示并记录至少包含以下语义的告知：

> 您确认已获得处理该合同的合法授权。合同内容将发送至千问商用 API，用于合同分类、要素抽取、风险分析和条款比对；系统将记录调用范围与模型版本。请勿上传未获授权的数据。

## 21. 模块与接口数量

| 模块 | 接口数量 |
| --- | ---: |
| Authentication | 6 |
| Organization and User | 18 |
| Contract and File | 9 |
| Review Task and Result | 9 |
| Risk Rule | 8 |
| Clause Template | 8 |
| Warning | 3 |
| Notification | 3 |
| Report | 3 |
| Feedback | 2 |
| Audit, Operations and Health | 6 |
| **合计** | **75** |
