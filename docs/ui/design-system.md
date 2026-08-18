# Contract Evidence Workspace Design System

本文件是前端生产实现使用的稳定视觉规范。`.stitch/DESIGN.md` 是生成来源；两者冲突时先 Review，不在代码中自行选择。

## Visual Direction

界面面向法务、合规和风控团队，采用证据优先、安静、精确、桌面优先的企业工作区。避免渐变、发光、装饰性卡片、嵌套卡片、超大标题和持续装饰动画。

## Tokens

| Token | Value | Use |
| --- | --- | --- |
| Evidence Blue | `#2457A6` | 主操作、选中导航、焦点、证据链接 |
| Deep Ink | `#172033` | 标题、正文、合同内容 |
| Secondary Teal | `#217A70` | 次要强调、证据关系 |
| Workspace Mist | `#F5F7FA` | 应用背景 |
| Paper White | `#FFFFFF` | 表格、表单、文档和工作区 |
| Quiet Panel | `#EEF2F6` | 筛选条、次级分组、骨架屏 |
| Structural Border | `#D7DEE8` | 分隔线、边框、表格规则 |
| Muted Text | `#5F6B7A` | 描述、时间、编号和辅助文案 |
| Confirmed Green | `#16805B` | 完成、发布、匹配、解决 |
| Review Amber | `#B86A00` | 待复核、中风险、低置信度 |
| Critical Red | `#C43D3D` | 高风险、失败、禁用和破坏性动作 |
| Informational Cyan | `#1677A6` | 处理中、系统提示和中性信息 |

状态颜色必须同时配合文字和图标/形状；严重度、工作流状态和操作可用性不能共用一个颜色语义。

## Typography

- 主字体：`Noto Sans`，回退到中文系统无衬线字体。
- 技术值：`JetBrains Mono`，仅用于 request ID、版本、哈希和展示编号。
- 页面标题：24px / 600 / 32px。
- 区块标题：16px / 600 / 24px。
- 正文和表格：14px / 400 / 22px。
- 标签：13px / 500 / 20px；辅助信息：12px / 400 / 18px。
- 字间距为 0，不随视口宽度缩放字体。

## Layout and Components

- 展开 Sidebar 240px，Top Header 56px；1440px 外边距 24px，1280px 外边距 20px。
- 使用 4px 基础间距，常用 8/12/16/24/32px。
- 页面区块不使用装饰性浮动卡片；表格、对话框、抽屉和真实重复实体最多使用 6px 圆角。
- 控件一般使用 4px 圆角，焦点使用 Evidence Blue 可见焦点环。
- 表格保持稳定列宽和表头；空间不足时优先水平滚动，不压缩到不可读。
- 页面标题区最多一个主操作，次要操作进入操作组或菜单。
- 审核结果采用结果主栏与证据侧栏/分栏；1280px 可退化为抽屉，但不得遮挡正文和操作。
- Skeleton 必须匹配最终组件尺寸；空数据要区分无数据和筛选无结果。

## Viewports and Motion

主要设计宽度为 1440px，1280px 必须完整可操作。窄屏只做内容保护，不作为独立移动端产品。动效只用于抽屉、对话框、证据聚焦和状态变化，不能使用持续装饰动画或改变布局尺寸的 hover 效果。
