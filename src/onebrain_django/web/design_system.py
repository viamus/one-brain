from __future__ import annotations

# ruff: noqa: E501

ONEBRAIN_DESIGN_SYSTEM_CSS = """
:root {
  color-scheme: dark;
  --ob-tigerlily: #d97757;
  --ob-copper: #b8694d;
  --ob-ink: #0e0f0d;
  --ob-ink-2: #121311;
  --ob-canvas: #0a0b0a;
  --ob-panel: #171816;
  --ob-panel-raised: #20211e;
  --ob-control: #151714;
  --ob-line: #34352f;
  --ob-line-soft: rgba(242, 239, 231, 0.08);
  --ob-text: #f2efe7;
  --ob-muted: #a9a39a;
  --ob-blue: #7aa7d9;
  --ob-green: #65b891;
  --ob-yellow: #e1a34a;
  --ob-red: #e06a5f;
  --ob-radius-panel: 8px;
  --ob-radius-compact: 6px;
  --ob-shadow-focus: 0 0 0 2px rgba(217, 119, 87, 0.26);
  --bg: var(--ob-ink);
  --canvas: var(--ob-canvas);
  --panel: var(--ob-panel);
  --panel-strong: var(--ob-panel-raised);
  --panel-float: rgba(23, 24, 22, 0.92);
  --control: var(--ob-control);
  --line: var(--ob-line);
  --ink: var(--ob-text);
  --label: var(--ob-text);
  --muted: var(--ob-muted);
  --memory: var(--ob-green);
  --context: var(--ob-blue);
  --skill: #b99df1;
  --workflow: var(--ob-tigerlily);
  --entity: var(--ob-blue);
  --fact: #82b8c9;
  --note: #8f9eac;
  --edge: #6f7569;
  --correlation: var(--ob-yellow);
  --node-stroke: var(--ob-panel);
  --centroid: var(--ob-tigerlily);
  --grouping: #28beb8;
  --grouping-soft: rgba(40, 190, 184, 0.14);
  --focus: var(--ob-tigerlily);
  --focus-soft: rgba(217, 119, 87, 0.22);
  --danger: var(--ob-red);
}

:root[data-theme="dark"] {
  color-scheme: dark;
}

* { box-sizing: border-box; }

html,
body {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
  background: var(--ob-ink);
  color: var(--ob-text);
  font-family: "Segoe UI Variable", "Segoe UI", -apple-system, BlinkMacSystemFont, Inter, Roboto, Arial, sans-serif;
  font-size: 14px;
  line-height: 1.5;
  letter-spacing: 0;
}

::selection {
  background: rgba(217, 119, 87, 0.36);
  color: var(--ob-text);
}

button,
input,
select,
textarea {
  font: inherit;
  letter-spacing: 0;
}

button,
.ob-button {
  min-height: 34px;
  border: 1px solid var(--ob-line);
  border-radius: var(--ob-radius-compact);
  background: var(--ob-control);
  color: var(--ob-text);
  font-weight: 650;
  cursor: pointer;
  transition: border-color 120ms ease, background-color 120ms ease, color 120ms ease;
}

button:hover,
.ob-button:hover {
  border-color: rgba(217, 119, 87, 0.52);
  background: color-mix(in srgb, var(--ob-tigerlily) 9%, var(--ob-control));
}

button.primary,
.ob-button.primary {
  border-color: var(--ob-tigerlily);
  background: var(--ob-tigerlily);
  color: #151513;
}

button:focus,
input:focus,
select:focus,
textarea:focus,
a:focus {
  outline: none;
  box-shadow: var(--ob-shadow-focus);
}

input,
select,
textarea {
  border: 1px solid var(--ob-line);
  border-radius: var(--ob-radius-compact);
  background: var(--ob-control);
  color: var(--ob-text);
}

a {
  color: var(--ob-blue);
  text-decoration: none;
}

a:hover {
  color: var(--ob-tigerlily);
}

.ob-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 248px minmax(0, 1fr);
  background: var(--ob-ink);
}

.ob-sidebar {
  min-width: 0;
  border-right: 1px solid color-mix(in srgb, var(--ob-line) 72%, transparent);
  background: var(--ob-ink-2);
  display: flex;
  flex-direction: column;
  padding: 14px 12px;
  gap: 16px;
}

.ob-brand {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 4px 4px 10px;
}

.ob-brand-mark {
  width: 34px;
  height: 34px;
  border-radius: var(--ob-radius-compact);
  border: 1px solid color-mix(in srgb, var(--ob-tigerlily) 28%, transparent);
  background: linear-gradient(180deg, color-mix(in srgb, var(--ob-tigerlily) 18%, var(--ob-panel)), color-mix(in srgb, var(--ob-tigerlily) 7%, var(--ob-panel)));
  color: var(--ob-tigerlily);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-weight: 850;
}

.ob-brand-copy {
  min-width: 0;
}

.ob-brand-title {
  display: block;
  color: var(--ob-text);
  font-size: 15px;
  font-weight: 760;
  line-height: 1.15;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ob-brand-subtitle {
  display: block;
  color: var(--ob-muted);
  font-size: 12px;
  line-height: 1.3;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.ob-nav {
  display: grid;
  gap: 6px;
}

.ob-nav-link {
  min-height: 36px;
  display: flex;
  align-items: center;
  gap: 9px;
  border: 1px solid transparent;
  border-radius: var(--ob-radius-compact);
  padding: 0 10px;
  color: var(--ob-muted);
  background: transparent;
  text-align: left;
  font-weight: 650;
}

.ob-nav-link.active,
.ob-nav-link[data-active="true"],
.ob-nav-link:hover {
  border-color: color-mix(in srgb, var(--ob-tigerlily) 18%, var(--ob-line));
  background: color-mix(in srgb, var(--ob-tigerlily) 8%, transparent);
  color: var(--ob-text);
}

.ob-main {
  min-width: 0;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.ob-topbar {
  min-height: 58px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 10px clamp(16px, 2vw, 30px);
  border-bottom: 1px solid color-mix(in srgb, var(--ob-line) 72%, transparent);
  background: color-mix(in srgb, var(--ob-ink) 92%, transparent);
  backdrop-filter: blur(14px);
}

.ob-topbar-title {
  margin: 0;
  color: var(--ob-text);
  font-size: 18px;
  font-weight: 760;
  line-height: 1.2;
}

.ob-topbar-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.ob-topbar-meta,
.ob-muted {
  color: var(--ob-muted);
}

.ob-page {
  min-width: 0;
  flex: 1 1 auto;
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px clamp(16px, 2vw, 30px) 28px;
}

.ob-page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 22px;
  padding-bottom: 12px;
  border-bottom: 1px solid color-mix(in srgb, var(--ob-line) 58%, transparent);
}

.ob-page-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  margin: 0;
  color: var(--ob-text);
  font-size: 22px;
  line-height: 1.15;
  font-weight: 780;
}

.ob-page-subtitle {
  margin: 4px 0 0;
  color: var(--ob-muted);
  font-size: 13px;
  line-height: 1.4;
}

.ob-page-icon {
  width: 36px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border-radius: var(--ob-radius-compact);
  border: 1px solid color-mix(in srgb, var(--ob-tigerlily) 20%, transparent);
  background: linear-gradient(180deg, color-mix(in srgb, var(--ob-tigerlily) 16%, var(--ob-panel)), color-mix(in srgb, var(--ob-tigerlily) 7%, var(--ob-panel)));
  color: var(--ob-tigerlily);
  font-weight: 850;
}

.ob-page h1,
.ob-page h2,
.ob-page h3 {
  margin: 0;
  color: var(--ob-text);
  letter-spacing: 0;
}

.ob-page h1 {
  font-size: 24px;
  line-height: 1.2;
  font-weight: 740;
}

.ob-page p {
  margin: 0;
}

.ob-surface {
  border: 1px solid color-mix(in srgb, var(--ob-line) 82%, transparent);
  border-radius: var(--ob-radius-panel);
  background: linear-gradient(180deg, color-mix(in srgb, var(--ob-panel) 98%, var(--ob-panel-raised)), var(--ob-panel));
}

.ob-surface-soft {
  border: 1px solid color-mix(in srgb, var(--ob-tigerlily) 18%, var(--ob-line));
  border-radius: var(--ob-radius-panel);
  background: color-mix(in srgb, var(--ob-tigerlily) 6%, var(--ob-panel));
}

.ob-panel-block {
  padding: 14px;
}

.ob-sidebar-section {
  display: grid;
  gap: 8px;
  padding: 10px;
  border: 1px solid color-mix(in srgb, var(--ob-line) 74%, transparent);
  border-radius: var(--ob-radius-panel);
  background: color-mix(in srgb, var(--ob-panel) 64%, transparent);
}

.ob-section-title {
  display: block;
  margin-bottom: 8px;
  color: var(--ob-muted);
  font-size: 11px;
  font-weight: 800;
  line-height: 1.2;
  text-transform: uppercase;
}

.ob-kv {
  display: grid;
  grid-template-columns: minmax(0, 0.46fr) minmax(0, 1fr);
  gap: 8px;
  min-height: 30px;
  align-items: center;
  padding: 6px 0;
  border-top: 1px solid color-mix(in srgb, var(--ob-line) 52%, transparent);
}

.ob-kv:first-of-type {
  border-top: 0;
}

.ob-kv span {
  color: var(--ob-muted);
  font-size: 12px;
  font-weight: 650;
}

.ob-kv strong {
  min-width: 0;
  color: var(--ob-text);
  font-size: 12px;
  font-weight: 700;
  text-align: right;
  overflow-wrap: anywhere;
}

.ob-empty-state {
  min-height: 180px;
  display: grid;
  place-items: center;
  color: var(--ob-muted);
  text-align: center;
  padding: 18px;
}

.ob-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 34px;
  padding: 0 12px;
  white-space: nowrap;
}

.ob-button-primary {
  border-color: var(--ob-tigerlily);
  background: var(--ob-tigerlily);
  color: #151513;
}

.ob-button-ghost {
  background: color-mix(in srgb, var(--ob-panel-raised) 60%, transparent);
  color: var(--ob-text);
}

.ob-grid {
  display: grid;
  gap: 12px;
}

.ob-grid.two {
  grid-template-columns: minmax(0, 1fr) minmax(360px, 0.42fr);
}

.ob-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(92px, 1fr));
  gap: 8px;
}

.ob-metric {
  border: 1px solid var(--ob-line);
  border-radius: var(--ob-radius-compact);
  padding: 10px 12px;
  background: color-mix(in srgb, var(--ob-panel) 86%, var(--ob-ink));
}

.ob-metric strong {
  display: block;
  color: var(--ob-text);
  font-size: 20px;
  line-height: 1.1;
}

.ob-metric label {
  display: block;
  margin-top: 3px;
  color: var(--ob-muted);
  font-size: 11px;
  font-weight: 720;
  text-transform: uppercase;
}

.ob-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 24px;
  border-radius: 999px;
  padding: 0 9px;
  border: 1px solid color-mix(in srgb, var(--ob-line) 80%, transparent);
  background: color-mix(in srgb, var(--ob-panel-raised) 72%, transparent);
  color: var(--ob-muted);
  font-size: 12px;
  font-weight: 700;
}

.ob-code {
  font-family: "Cascadia Code", Consolas, "SFMono-Regular", monospace;
}

@media (max-width: 980px) {
  .ob-shell {
    grid-template-columns: 1fr;
  }

  .ob-sidebar {
    position: static;
    border-right: 0;
    border-bottom: 1px solid var(--ob-line);
  }

  .ob-nav {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .ob-grid.two {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 680px) {
  .ob-topbar,
  .ob-page-header {
    align-items: stretch;
    flex-direction: column;
  }

  .ob-nav {
    grid-template-columns: 1fr;
  }

  .ob-metrics {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
"""
