# UI Implementation Guide

## Purpose

本目录保存前端页面 PRD、视觉设计系统和按 Page ID 管理的 HTML/PNG 原型。它们服务于 Vue 页面实现和 UI Review，但不替代业务需求、架构或 API 契约。

## Reading Order

前端任务按以下顺序读取：

1. `docs/phase-status.md`：确认实际 Phase 和完成边界。
2. `docs/development-plan.md`：确认当前 Phase 的范围、依赖和验收条件。
3. `docs/ui/frontend-prd.md`：确认 Page ID、角色、页面操作、状态和页面 URL 映射。
4. `docs/ui/design-system.md`：确认视觉语言和响应式规则。
5. `docs/ui/stitch/<PAGE-ID>-*.html` 与 `.png`：确认具体布局和状态原型。
6. `docs/api-contract.md`：确认接口 Method、Path、字段、权限、错误和状态机。

## Source Boundaries

- `docs/api-contract.md` 是 API Route、字段、权限、状态和错误的唯一来源。
- `frontend-prd.md` 是页面结构、Page ID、用户操作、页面状态和 API 映射的来源。
- `design-system.md` 和 approved 原型是视觉、布局、组件和交互状态的实现基准。
- Vue Page URL 是浏览器导航地址，不得被误认为 API Route；API 的 `/api/v1` 前缀不直接作为页面 URL。
- 发现原型与需求、API、权限或状态机冲突时，先报告并更新相应规范，不在 UI 中隐式改变语义。

## Prototype Assets

原型实际目录为 `docs/ui/stitch/`。HTML 用于布局和交互参考，PNG 用于视觉对照；`.stitch/metadata.json` 用于查看屏幕索引和 deprecated 标记。

原型不是生产代码。不得直接复制其中的 CDN、Tailwind、Google Fonts、Material Symbols、静态数据或模拟请求；生产页面必须使用仓库的 Vue、Element Plus、API Client 和测试边界。

页面以稳定 Page ID 关联，状态使用文件名 suffix 表达，不创建新的业务 Page ID。标记为 `deprecated` 的资产不得作为最终实现依据。

## Page Completion

一个前端页面完成至少需要：对应 Page ID 的 API 映射、角色和权限呈现、适用状态、1440px/1280px 验证、组件测试和适用的 Playwright 测试。页面完成不能替代 Phase 完成；Phase 仍需满足全栈验收并更新 `docs/phase-status.md`。
