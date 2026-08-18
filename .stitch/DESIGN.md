# Design System: Contract Evidence Workspace
**Project ID:** 7860852984903933438

## 1. Visual Theme & Atmosphere

A professional, evidence-first enterprise workspace for legal, compliance, and risk teams. The interface is calm, precise, and operational rather than promotional. It supports dense tables and long-form contract review without feeling cramped, using clear hierarchy, stable alignment, neutral surfaces, and restrained semantic accents.

AI assistance is communicated through source labels, evidence links, and processing states rather than futuristic decoration. The visual language avoids gradients, glow effects, oversized headings, decorative cards, nested cards, and large empty hero areas. Conclusions always remain visually connected to their source evidence.

The default appearance is light mode. Pages are optimized for a 1440px desktop viewport and remain fully usable at 1280px. Narrower screens protect content from overlap but are not treated as a separate mobile product.

## 2. Color Palette & Roles

- **Evidence Blue (#2457A6):** Primary actions, selected navigation, focused controls, links, and active evidence references. Use selectively so status colors remain distinct.
- **Deep Ink (#172033):** Primary text, page titles, table values, and high-emphasis legal content.
- **Secondary Teal (#217A70):** Secondary brand accent, selected evidence relationships, and supporting information that should not compete with the primary action.
- **Workspace Mist (#F5F7FA):** Application background and low-emphasis page bands.
- **Paper White (#FFFFFF):** Tables, forms, document surfaces, drawers, dialogs, and primary work areas.
- **Quiet Panel (#EEF2F6):** Filter bars, secondary headers, skeletons, and subtle grouping without floating-card styling.
- **Structural Border (#D7DEE8):** Dividers, input borders, table rules, and panel boundaries.
- **Muted Text (#5F6B7A):** Secondary descriptions, timestamps, IDs, and helper text.
- **Placeholder Gray (#8A95A3):** Placeholder and disabled secondary text; never used for critical information.
- **Confirmed Green (#16805B):** Completed, published, matched, resolved, and confirmed facts.
- **Review Amber (#B86A00):** Pending review, medium risk, low confidence, and attention states.
- **Critical Red (#C43D3D):** High risk, failure, disabled resources, and destructive actions.
- **Informational Cyan (#1677A6):** Neutral processing, system information, and non-risk status messages.

Every status color must be paired with text and an icon or shape. Severity, workflow status, and action availability are separate semantics and must not share one generic color scale.

## 3. Typography Rules

Use **Noto Sans** as the primary interface family with Chinese system sans-serif fallback. It provides neutral bilingual legibility for dense tables and long contract excerpts. Use **JetBrains Mono** only for request IDs, version identifiers, hashes, contract display numbers, and other character-sensitive technical values.

- Page titles: 24px, weight 600, line height 32px.
- Section titles: 16px, weight 600, line height 24px.
- Body and table text: 14px, weight 400, line height 22px.
- Form labels: 13px, weight 500, line height 20px.
- Metadata and status support text: 12px, weight 400, line height 18px.
- Letter spacing is always 0. Do not scale typography with viewport width.

## 4. Component Stylings

* **Buttons:** Standard controls use slightly softened 4px corners. Primary buttons use Evidence Blue with white text. Secondary buttons use a white surface with a Structural Border. Destructive actions stay visually quiet until confirmation and use Critical Red only when the action is explicit. Icon-only tools use familiar Lucide-style symbols, stable 32px or 36px hit areas, and tooltips.
* **Cards/Containers:** Do not wrap page sections in decorative cards. Tables, dialogs, drawers, and genuinely repeated entities may use Paper White surfaces with a 1px Structural Border and up to 6px corners. Avoid nested cards. Elevation is mostly flat; dialogs and popovers use one restrained, diffused shadow.
* **Inputs/Forms:** Paper White background, 1px Structural Border, 4px corners, visible Evidence Blue focus ring, persistent labels, nearby validation messages, and stable control heights. Long forms group fields with headings and dividers instead of cards.
* **Tables:** Compact but readable rows, fixed header treatment, stable columns, left-aligned text, right-aligned numeric values, and horizontal scrolling before content compression. Important identity columns may remain fixed. Row hover changes surface only and never changes dimensions.
* **Status Tags:** Compact, gently rounded labels with text, icon or leading shape, light semantic background, semantic border, and dark readable text. Tags describe facts and are never styled like action buttons.
* **Navigation:** A 240px expanded sidebar with icon-label pairs and grouped sections. The active item uses a subtle primary-tinted background and a strong left indicator. The 56px top header contains breadcrumb, notification entry, and user menu without extra global tools.
* **Evidence Workspace:** Review results occupy the main column. A linked evidence pane uses a persistent divider and synchronized selection. At 1280px the pane may become a right drawer, preserving filters and scroll position. Quotes and highlights use restrained semantic fills rather than glowing effects.
* **Loading and Empty States:** Skeletons match final component dimensions. Empty states are compact and contextual, distinguishing no data from no filtered results. Processing, upload progress, review progress, and report generation use their own server-backed status language.

## 5. Layout Principles

Use a fixed-fluid desktop shell: 240px expanded sidebar, 56px top header, and a fluid main workspace. Page content uses 24px outer margins at 1440px and 20px at 1280px. A 4px base spacing unit produces common gaps of 8px, 12px, 16px, 24px, and 32px.

Page headers contain the title, resource status, concise context, and at most one primary action. Secondary commands move into an adjacent group or dropdown. Filters, tables, pagination, and save bars remain in stable locations across modules.

Standard forms use a readable maximum width while contract tables, audit tables, document preview, review results, and evidence workspaces use the available width. Long drawers and dialogs are viewport-constrained with scrollable bodies and reachable action bars. No control, label, status, or dynamic value may overlap or resize the surrounding layout.

Use short, functional motion only for drawers, dialogs, evidence focus, and state changes. Avoid continuous decorative animation. Hover and focus states never change component dimensions.
