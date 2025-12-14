"""
Jnkn Impact Cockpit - Visualization Builder

A sophisticated dependency visualization system that transforms passive 
file exploration into an actionable "Impact Cockpit" for understanding
cross-domain breaking changes.

Features:
1. Semantic Edge Visualization (The "Why")
2. Confidence & Risk Indicators  
3. Rich Inspector Panel (The "So What")
4. Trace Highlighting for lineage clarity
"""

# =============================================================================
# CSS ASSETS - "Mission Control" Dark Theme
# =============================================================================
CSS_CONTENT = """
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');

:root {
    /* Void & Surfaces */
    --void: #07080a;
    --surface-0: #0c0d10;
    --surface-1: #12141a;
    --surface-2: #181b22;
    --surface-3: #1e222b;
    --surface-4: #252a35;
    --surface-hover: #2a3040;
    --surface-active: #323a4a;
    
    /* Borders */
    --border-subtle: rgba(255, 255, 255, 0.04);
    --border-default: rgba(255, 255, 255, 0.08);
    --border-strong: rgba(255, 255, 255, 0.14);
    --border-focus: rgba(59, 130, 246, 0.5);
    
    /* Typography */
    --text-primary: #e8eaed;
    --text-secondary: #9aa0a6;
    --text-tertiary: #6b7280;
    --text-disabled: #4b5563;
    
    /* Confidence Spectrum */
    --confidence-high: #10b981;
    --confidence-high-bg: rgba(16, 185, 129, 0.12);
    --confidence-medium: #f59e0b;
    --confidence-medium-bg: rgba(245, 158, 11, 0.12);
    --confidence-low: #ef4444;
    --confidence-low-bg: rgba(239, 68, 68, 0.12);
    
    /* Risk */
    --risk-critical: #dc2626;
    --risk-critical-bg: rgba(220, 38, 38, 0.1);
    --risk-high: #ea580c;
    --risk-high-bg: rgba(234, 88, 12, 0.1);
    --risk-medium: #ca8a04;
    --risk-medium-bg: rgba(202, 138, 4, 0.1);
    
    /* Status */
    --status-info: #3b82f6;
    --status-info-bg: rgba(59, 130, 246, 0.12);
    
    /* Domains */
    --domain-infra: #f97316;
    --domain-infra-bg: rgba(249, 115, 22, 0.12);
    --domain-config: #06b6d4;
    --domain-config-bg: rgba(6, 182, 212, 0.12);
    --domain-code: #a855f7;
    --domain-code-bg: rgba(168, 85, 247, 0.12);
    --domain-data: #22d3ee;
    --domain-data-bg: rgba(34, 211, 238, 0.12);
    
    /* Diff */
    --diff-added: #22c55e;
    --diff-added-bg: rgba(34, 197, 94, 0.08);
    --diff-removed: #ef4444;
    --diff-removed-bg: rgba(239, 68, 68, 0.08);
    --diff-modified: #eab308;
    --diff-modified-bg: rgba(234, 179, 8, 0.08);
    
    /* Typography */
    --font-sans: 'IBM Plex Sans', -apple-system, sans-serif;
    --font-mono: 'JetBrains Mono', 'SF Mono', monospace;
    
    --text-2xs: 0.625rem;
    --text-xs: 0.6875rem;
    --text-sm: 0.75rem;
    --text-base: 0.8125rem;
    --text-md: 0.875rem;
    --text-lg: 1rem;
    --text-xl: 1.125rem;
    
    /* Spacing */
    --space-1: 0.25rem;
    --space-2: 0.5rem;
    --space-3: 0.75rem;
    --space-4: 1rem;
    --space-5: 1.25rem;
    --space-6: 1.5rem;
    
    /* Radii */
    --radius-sm: 4px;
    --radius-md: 6px;
    --radius-lg: 8px;
    --radius-full: 9999px;
    
    /* Layout */
    --header-height: 56px;
    --column-width: 320px;
    --inspector-width: 420px;
    
    /* Motion */
    --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
    --duration-fast: 150ms;
    --duration-normal: 250ms;
    
    /* Shadows */
    --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.4);
    --shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.5);
    --shadow-xl: 0 16px 48px rgba(0, 0, 0, 0.6);
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html {
    font-size: 16px;
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
}

body {
    height: 100vh;
    overflow: hidden;
    background: var(--void);
    color: var(--text-primary);
    font-family: var(--font-sans);
    font-size: var(--text-base);
    display: flex;
    flex-direction: column;
    background-image: 
        linear-gradient(rgba(59, 130, 246, 0.015) 1px, transparent 1px),
        linear-gradient(90deg, rgba(59, 130, 246, 0.015) 1px, transparent 1px),
        radial-gradient(ellipse at 50% 0%, rgba(59, 130, 246, 0.04) 0%, transparent 50%);
    background-size: 40px 40px, 40px 40px, 100% 100%;
}

/* ═══════════════════════════════════════════════════════════════════════════
   HEADER
   ═══════════════════════════════════════════════════════════════════════════ */

.header {
    height: var(--header-height);
    background: var(--surface-1);
    border-bottom: 1px solid var(--border-default);
    display: flex;
    align-items: center;
    padding: 0 var(--space-4);
    gap: var(--space-5);
    flex-shrink: 0;
    z-index: 100;
}

.brand {
    display: flex;
    align-items: center;
    gap: var(--space-3);
}

.brand-logo {
    width: 32px;
    height: 32px;
    background: linear-gradient(135deg, var(--status-info) 0%, var(--domain-code) 100%);
    border-radius: var(--radius-md);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--font-mono);
    font-weight: 700;
    font-size: var(--text-md);
    color: white;
    box-shadow: var(--shadow-md), 0 0 16px rgba(59, 130, 246, 0.3);
}

.brand-text { display: flex; flex-direction: column; }
.brand-name { font-weight: 700; font-size: var(--text-md); letter-spacing: -0.02em; }
.brand-subtitle {
    font-size: var(--text-2xs);
    color: var(--text-tertiary);
    text-transform: uppercase;
    letter-spacing: 0.1em;
}

.stats-bar {
    display: flex;
    gap: var(--space-4);
    padding: var(--space-2) var(--space-4);
    background: var(--surface-2);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-subtle);
}

.stat {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    font-size: var(--text-xs);
    font-family: var(--font-mono);
}

.stat-label { color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.05em; }
.stat-value { color: var(--text-secondary); font-weight: 600; }
.stat--critical .stat-value { color: var(--risk-critical); }

.mode-toggle {
    display: flex;
    background: var(--surface-2);
    border-radius: var(--radius-md);
    padding: 3px;
    border: 1px solid var(--border-default);
}

.mode-btn {
    background: transparent;
    border: none;
    color: var(--text-tertiary);
    padding: var(--space-2) var(--space-4);
    font-size: var(--text-xs);
    font-weight: 600;
    font-family: var(--font-sans);
    cursor: pointer;
    border-radius: var(--radius-sm);
    transition: all var(--duration-fast) var(--ease-out);
    display: flex;
    align-items: center;
    gap: var(--space-2);
}

.mode-btn:hover { color: var(--text-secondary); background: var(--surface-3); }
.mode-btn.active { background: var(--status-info); color: white; }

.search-container { flex: 1; max-width: 400px; position: relative; }

.search-input {
    width: 100%;
    background: var(--surface-2);
    border: 1px solid var(--border-default);
    padding: var(--space-2) var(--space-3) var(--space-2) 38px;
    border-radius: var(--radius-md);
    color: var(--text-primary);
    font-size: var(--text-base);
    font-family: var(--font-sans);
    transition: all var(--duration-fast) var(--ease-out);
}

.search-input::placeholder { color: var(--text-tertiary); }
.search-input:focus {
    outline: none;
    border-color: var(--border-focus);
    background: var(--surface-3);
    box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.1);
}

.search-icon {
    position: absolute;
    left: var(--space-3);
    top: 50%;
    transform: translateY(-50%);
    color: var(--text-tertiary);
    font-size: var(--text-md);
}

.search-kbd {
    position: absolute;
    right: var(--space-3);
    top: 50%;
    transform: translateY(-50%);
    font-size: var(--text-2xs);
    font-family: var(--font-mono);
    color: var(--text-disabled);
    background: var(--surface-3);
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    border: 1px solid var(--border-subtle);
}

.search-results {
    position: absolute;
    top: calc(100% + var(--space-2));
    left: 0;
    width: 100%;
    background: var(--surface-2);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-lg);
    max-height: 400px;
    overflow-y: auto;
    display: none;
    z-index: 1000;
    box-shadow: var(--shadow-xl);
}

.search-results.visible { display: block; animation: slideDown var(--duration-fast) var(--ease-out); }

.search-item {
    padding: var(--space-3) var(--space-4);
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: var(--space-3);
    border-bottom: 1px solid var(--border-subtle);
    transition: background var(--duration-fast) var(--ease-out);
}

.search-item:last-child { border-bottom: none; }
.search-item:hover { background: var(--surface-hover); }
.search-item-icon { font-size: var(--text-lg); width: 24px; text-align: center; }
.search-item-content { flex: 1; min-width: 0; }
.search-item-name { font-size: var(--text-base); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.search-item-name strong { color: var(--status-info); }
.search-item-type { font-size: var(--text-xs); color: var(--text-tertiary); font-family: var(--font-mono); }

/* ═══════════════════════════════════════════════════════════════════════════
   MAIN LAYOUT & COLUMNS
   ═══════════════════════════════════════════════════════════════════════════ */

.main-container { flex: 1; display: flex; overflow: hidden; }

.columns-wrapper {
    flex: 1;
    display: flex;
    overflow-x: auto;
    scroll-behavior: smooth;
    scrollbar-width: thin;
    scrollbar-color: var(--surface-active) transparent;
}

.columns-wrapper::-webkit-scrollbar { height: 8px; }
.columns-wrapper::-webkit-scrollbar-track { background: transparent; }
.columns-wrapper::-webkit-scrollbar-thumb { background: var(--surface-active); border-radius: var(--radius-full); }

.column {
    width: var(--column-width);
    min-width: var(--column-width);
    border-right: 1px solid var(--border-subtle);
    background: var(--surface-0);
    display: flex;
    flex-direction: column;
    animation: columnSlideIn var(--duration-normal) var(--ease-out) forwards;
    opacity: 0;
    transform: translateX(20px);
}

.column:nth-child(even) { background: var(--surface-1); }

.column.in-trace-path {
    background: linear-gradient(180deg, rgba(59, 130, 246, 0.04) 0%, rgba(59, 130, 246, 0.02) 100%);
}

.column.in-trace-path::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 2px;
    background: linear-gradient(90deg, var(--status-info), transparent);
}

.column-header {
    padding: var(--space-3) var(--space-4);
    border-bottom: 1px solid var(--border-subtle);
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: inherit;
    position: sticky;
    top: 0;
    z-index: 10;
}

.column-title {
    font-size: var(--text-xs);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-tertiary);
    display: flex;
    align-items: center;
    gap: var(--space-2);
}

.column-count {
    font-size: var(--text-2xs);
    font-family: var(--font-mono);
    color: var(--text-disabled);
    background: var(--surface-3);
    padding: 2px 8px;
    border-radius: var(--radius-full);
}

.column-list {
    flex: 1;
    overflow-y: auto;
    padding: var(--space-2);
    scrollbar-width: thin;
    scrollbar-color: var(--surface-active) transparent;
}

.column-list::-webkit-scrollbar { width: 6px; }
.column-list::-webkit-scrollbar-thumb { background: var(--surface-active); border-radius: var(--radius-full); }

/* ═══════════════════════════════════════════════════════════════════════════
   ITEM COMPONENT
   ═══════════════════════════════════════════════════════════════════════════ */

.item {
    display: flex;
    align-items: flex-start;
    padding: var(--space-3);
    margin-bottom: var(--space-1);
    border-radius: var(--radius-md);
    cursor: pointer;
    border: 1px solid transparent;
    transition: all var(--duration-fast) var(--ease-out);
    position: relative;
    animation: itemFadeIn var(--duration-fast) var(--ease-out) forwards;
    opacity: 0;
}

.item:hover { background: var(--surface-hover); border-color: var(--border-subtle); }
.item.active { background: var(--surface-active); border-color: var(--border-default); }

.item.in-trace {
    background: var(--status-info-bg);
    border-color: rgba(59, 130, 246, 0.3);
}

.item.in-trace::before {
    content: '';
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 3px;
    background: var(--status-info);
    border-radius: 3px 0 0 3px;
}

.item.diff-added { background: var(--diff-added-bg); border-left: 3px solid var(--diff-added); }
.item.diff-removed { background: var(--diff-removed-bg); border-left: 3px solid var(--diff-removed); opacity: 0.6; }
.item.diff-modified { background: var(--diff-modified-bg); border-left: 3px solid var(--diff-modified); }

.item-icon {
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: var(--text-lg);
    margin-right: var(--space-3);
    flex-shrink: 0;
    background: var(--surface-3);
    border-radius: var(--radius-sm);
}

.item-content { flex: 1; min-width: 0; }

.item-title {
    font-size: var(--text-base);
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.item-subtitle {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    font-family: var(--font-mono);
    margin-top: 2px;
}

.item-chevron {
    color: var(--text-disabled);
    font-size: var(--text-md);
    margin-left: var(--space-2);
    transition: transform var(--duration-fast) var(--ease-out);
    align-self: center;
}

.item:hover .item-chevron { transform: translateX(2px); color: var(--text-tertiary); }

/* ═══════════════════════════════════════════════════════════════════════════
   EDGE BADGE - Semantic Connection Visualization ("The Why")
   ═══════════════════════════════════════════════════════════════════════════ */

.edge-info {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    margin-top: var(--space-2);
    padding-top: var(--space-2);
    border-top: 1px dashed var(--border-subtle);
}

.edge-badge {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    font-size: var(--text-2xs);
    font-family: var(--font-mono);
    font-weight: 500;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
    background: var(--surface-3);
    color: var(--text-secondary);
    border: 1px solid var(--border-subtle);
    max-width: 100%;
}

.edge-badge-icon { flex-shrink: 0; font-size: var(--text-xs); }
.edge-badge-text { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.edge-badge--reads { background: var(--domain-code-bg); border-color: rgba(168, 85, 247, 0.25); color: #c084fc; }
.edge-badge--provides { background: var(--domain-config-bg); border-color: rgba(6, 182, 212, 0.25); color: var(--domain-config); }
.edge-badge--provisions { background: var(--domain-infra-bg); border-color: rgba(249, 115, 22, 0.25); color: var(--domain-infra); }

/* ═══════════════════════════════════════════════════════════════════════════
   INDICATORS - Confidence & Risk
   ═══════════════════════════════════════════════════════════════════════════ */

.indicators { display: flex; gap: var(--space-2); margin-top: var(--space-2); flex-wrap: wrap; }

.confidence-indicator {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: var(--text-2xs);
    font-family: var(--font-mono);
    font-weight: 600;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
}

.confidence-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    border: 2px solid currentColor;
    flex-shrink: 0;
}

/* High confidence: solid filled */
.confidence-indicator--high { color: var(--confidence-high); background: var(--confidence-high-bg); }
.confidence-indicator--high .confidence-dot { background: currentColor; }

/* Medium confidence: hollow */
.confidence-indicator--medium { color: var(--confidence-medium); background: var(--confidence-medium-bg); }
.confidence-indicator--medium .confidence-dot { background: transparent; }

/* Low confidence: dashed border */
.confidence-indicator--low { color: var(--confidence-low); background: var(--confidence-low-bg); }
.confidence-indicator--low .confidence-dot { background: transparent; border-style: dashed; }

.risk-indicator {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    font-size: var(--text-2xs);
    font-family: var(--font-mono);
    font-weight: 600;
    padding: 2px 6px;
    border-radius: var(--radius-sm);
}

.risk-indicator--critical { background: var(--risk-critical-bg); color: var(--risk-critical); border: 1px solid rgba(220, 38, 38, 0.3); }
.risk-indicator--high { background: var(--risk-high-bg); color: var(--risk-high); border: 1px solid rgba(234, 88, 12, 0.3); }
.risk-indicator--medium { background: var(--risk-medium-bg); color: var(--risk-medium); border: 1px solid rgba(202, 138, 4, 0.3); }

/* ═══════════════════════════════════════════════════════════════════════════
   INSPECTOR PANEL - The "So What" Analysis
   ═══════════════════════════════════════════════════════════════════════════ */

.inspector {
    width: var(--inspector-width);
    min-width: var(--inspector-width);
    background: var(--surface-1);
    border-left: 1px solid var(--border-default);
    display: none;
    flex-direction: column;
    animation: inspectorSlideIn var(--duration-normal) var(--ease-out);
}

.inspector.visible { display: flex; }

.inspector-header {
    padding: var(--space-5);
    background: linear-gradient(180deg, var(--surface-2) 0%, var(--surface-1) 100%);
    border-bottom: 1px solid var(--border-subtle);
}

.inspector-header-top {
    display: flex;
    align-items: flex-start;
    gap: var(--space-4);
    margin-bottom: var(--space-4);
}

.inspector-icon {
    width: 48px;
    height: 48px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    background: var(--surface-3);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border-default);
    flex-shrink: 0;
}

.inspector-meta { flex: 1; min-width: 0; }

.inspector-title {
    font-size: var(--text-lg);
    font-weight: 700;
    word-break: break-word;
    line-height: 1.25;
}

.inspector-id {
    font-size: var(--text-xs);
    color: var(--text-tertiary);
    font-family: var(--font-mono);
    word-break: break-all;
    margin-top: var(--space-1);
}

.action-bar { display: flex; gap: var(--space-2); }

.btn {
    flex: 1;
    padding: var(--space-3);
    border-radius: var(--radius-md);
    border: 1px solid var(--border-default);
    background: var(--surface-3);
    color: var(--text-secondary);
    cursor: pointer;
    font-size: var(--text-xs);
    font-weight: 600;
    font-family: var(--font-sans);
    display: flex;
    align-items: center;
    justify-content: center;
    gap: var(--space-2);
    transition: all var(--duration-fast) var(--ease-out);
}

.btn:hover:not(:disabled) { background: var(--surface-hover); color: var(--text-primary); border-color: var(--border-strong); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn--primary { background: var(--status-info); color: white; border-color: var(--status-info); }
.btn--primary:hover:not(:disabled) { background: #2563eb; border-color: #2563eb; }
.btn-icon { font-size: var(--text-md); }

.inspector-tabs {
    display: flex;
    border-bottom: 1px solid var(--border-subtle);
    background: var(--surface-0);
    padding: 0 var(--space-3);
}

.inspector-tab {
    padding: var(--space-3) var(--space-4);
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
    cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all var(--duration-fast) var(--ease-out);
    display: flex;
    align-items: center;
    gap: var(--space-2);
}

.inspector-tab:hover { color: var(--text-secondary); }
.inspector-tab.active { color: var(--text-primary); border-bottom-color: var(--status-info); }

.tab-count {
    font-size: var(--text-2xs);
    font-family: var(--font-mono);
    background: var(--surface-3);
    padding: 1px 5px;
    border-radius: var(--radius-full);
    color: var(--text-tertiary);
}

.tab-content { flex: 1; overflow-y: auto; display: none; padding: var(--space-4); }
.tab-content.active { display: block; }

/* Evidence Section */
.evidence-section { margin-bottom: var(--space-5); }
.evidence-section:last-child { margin-bottom: 0; }

.strength-meter {
    background: var(--surface-2);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-lg);
    padding: var(--space-4);
    margin-bottom: var(--space-4);
}

.strength-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: var(--space-3);
}

.strength-label {
    font-size: var(--text-xs);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--text-tertiary);
}

.strength-value {
    font-size: var(--text-lg);
    font-weight: 700;
    font-family: var(--font-mono);
}

.strength-value--high { color: var(--confidence-high); }
.strength-value--medium { color: var(--confidence-medium); }
.strength-value--low { color: var(--confidence-low); }

.strength-bar {
    height: 6px;
    background: var(--surface-4);
    border-radius: var(--radius-full);
    overflow: hidden;
}

.strength-fill {
    height: 100%;
    border-radius: var(--radius-full);
    transition: width var(--duration-normal) var(--ease-out);
}

.strength-fill--high { background: linear-gradient(90deg, var(--confidence-high), #34d399); }
.strength-fill--medium { background: linear-gradient(90deg, var(--confidence-medium), #fbbf24); }
.strength-fill--low { background: linear-gradient(90deg, var(--confidence-low), #f87171); }

.evidence-card {
    background: var(--surface-2);
    border: 1px solid var(--border-default);
    border-radius: var(--radius-lg);
    overflow: hidden;
    margin-bottom: var(--space-4);
}

.evidence-card:last-child { margin-bottom: 0; }

.evidence-card-header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-3) var(--space-4);
    background: var(--surface-3);
    border-bottom: 1px solid var(--border-subtle);
}

.evidence-card-icon { font-size: var(--text-md); }

.evidence-card-title {
    font-size: var(--text-xs);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-tertiary);
}

.evidence-card-body { padding: var(--space-4); }

.evidence-text {
    font-size: var(--text-base);
    color: var(--text-secondary);
    line-height: 1.625;
}

.evidence-highlight { color: var(--domain-config); font-weight: 600; }

.evidence-code {
    display: block;
    background: var(--surface-0);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: var(--space-3);
    margin-top: var(--space-3);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--text-primary);
    overflow-x: auto;
    white-space: pre;
    line-height: 1.625;
}

.match-strategy {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    font-size: var(--text-2xs);
    font-family: var(--font-mono);
    padding: var(--space-1) var(--space-2);
    border-radius: var(--radius-sm);
    background: var(--surface-4);
    color: var(--text-secondary);
    margin-top: var(--space-2);
}

/* Details Tab */
.detail-section { margin-bottom: var(--space-5); }
.detail-section:last-child { margin-bottom: 0; }

.detail-section-title {
    font-size: var(--text-2xs);
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-disabled);
    margin-bottom: var(--space-3);
    padding-bottom: var(--space-2);
    border-bottom: 1px solid var(--border-subtle);
}

.detail-row {
    display: flex;
    margin-bottom: var(--space-3);
    font-size: var(--text-sm);
    align-items: flex-start;
}

.detail-row:last-child { margin-bottom: 0; }

.detail-label {
    width: 100px;
    color: var(--text-tertiary);
    flex-shrink: 0;
    font-size: var(--text-xs);
    font-weight: 500;
    text-transform: uppercase;
    padding-top: 2px;
}

.detail-value {
    flex: 1;
    color: var(--text-secondary);
    word-break: break-all;
    font-family: var(--font-mono);
    font-size: var(--text-xs);
}

/* Dependencies Tab */
.dep-list { display: flex; flex-direction: column; gap: var(--space-2); }

.dep-item {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3);
    background: var(--surface-2);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: all var(--duration-fast) var(--ease-out);
}

.dep-item:hover { background: var(--surface-hover); border-color: var(--border-default); }
.dep-item-icon { font-size: var(--text-lg); width: 24px; text-align: center; }
.dep-item-content { flex: 1; min-width: 0; }
.dep-item-name { font-size: var(--text-sm); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dep-item-type { font-size: var(--text-2xs); color: var(--text-tertiary); font-family: var(--font-mono); }

.empty-state {
    text-align: center;
    padding: var(--space-6);
    color: var(--text-disabled);
    font-size: var(--text-sm);
}

.empty-state-icon { font-size: 32px; margin-bottom: var(--space-3); opacity: 0.5; }

/* ═══════════════════════════════════════════════════════════════════════════
   MESH MODAL
   ═══════════════════════════════════════════════════════════════════════════ */

.modal-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: rgba(0, 0, 0, 0.85);
    z-index: 1000;
    display: none;
    align-items: center;
    justify-content: center;
    backdrop-filter: blur(8px);
}

.modal-overlay.visible { display: flex; animation: fadeIn var(--duration-fast) var(--ease-out); }

.modal-content {
    width: 90vw;
    height: 85vh;
    background: var(--surface-0);
    border-radius: var(--radius-lg);
    border: 1px solid var(--border-default);
    display: flex;
    flex-direction: column;
    box-shadow: var(--shadow-xl);
    overflow: hidden;
}

.modal-header {
    padding: var(--space-4) var(--space-5);
    border-bottom: 1px solid var(--border-subtle);
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: var(--surface-1);
}

.modal-title {
    font-size: var(--text-lg);
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: var(--space-3);
}

#mesh-container { flex: 1; overflow: hidden; background: var(--void); }

.node circle { stroke: var(--surface-0); stroke-width: 2px; cursor: pointer; transition: all var(--duration-fast); }
.node circle:hover { stroke-width: 3px; filter: drop-shadow(0 0 8px currentColor); }
.link { stroke: var(--border-default); stroke-opacity: 0.6; }
.node text { font-size: var(--text-2xs); fill: var(--text-secondary); pointer-events: none; font-family: var(--font-mono); }

/* ═══════════════════════════════════════════════════════════════════════════
   ANIMATIONS
   ═══════════════════════════════════════════════════════════════════════════ */

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes slideDown { from { opacity: 0; transform: translateY(-8px); } to { opacity: 1; transform: translateY(0); } }
@keyframes columnSlideIn { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }
@keyframes itemFadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
@keyframes inspectorSlideIn { from { opacity: 0; transform: translateX(20px); } to { opacity: 1; transform: translateX(0); } }

*:focus-visible { outline: 2px solid var(--status-info); outline-offset: 2px; }
"""

# =============================================================================
# JS ASSETS
# =============================================================================
JS_CONTENT = """
// ═══════════════════════════════════════════════════════════════════════════
// UTILITIES
// ═══════════════════════════════════════════════════════════════════════════

const Utils = {
    escapeHtml(unsafe) {
        if (!unsafe) return '';
        return String(unsafe)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    },
    
    debounce(fn, delay) {
        let timeoutId;
        return (...args) => {
            clearTimeout(timeoutId);
            timeoutId = setTimeout(() => fn.apply(this, args), delay);
        };
    },
    
    getNodeIcon(type, id = '') {
        const t = (type || '').toLowerCase();
        const idLower = (id || '').toLowerCase();
        
        if (t.includes('infra') || idLower.startsWith('infra:')) {
            if (idLower.includes('aws_db') || idLower.includes('rds')) return '🗄️';
            if (idLower.includes('redis') || idLower.includes('cache')) return '⚡';
            if (idLower.includes('s3') || idLower.includes('bucket')) return '🪣';
            return '☁️';
        }
        if (t.includes('env_var') || t.includes('env') || idLower.startsWith('env:')) return '🔑';
        if (t.includes('config') || idLower.includes('configmap')) return '⚙️';
        if (t.includes('secret')) return '🔐';
        if (t.includes('data') || idLower.startsWith('data:')) return '📊';
        if (t.includes('python') || idLower.endsWith('.py')) return '🐍';
        if (t.includes('terraform') || idLower.endsWith('.tf')) return '🏗️';
        if (t.includes('k8s') || t.includes('deployment')) return '☸️';
        if (t.includes('yaml')) return '📋';
        return '📄';
    },
    
    getCategoryIcon(category) {
        return { 'Infrastructure': '☁️', 'Configuration': '⚙️', 'Code': '💻', 'Data': '📊' }[category] || '📦';
    },
    
    getEdgeTypeIcon(edgeType) {
        return { 'reads': '📖', 'provides': '📤', 'provisions': '🏗️', 'depends_on': '🔗' }[(edgeType || '').toLowerCase()] || '🔗';
    },
    
    formatConfidence: (c) => Math.round((c || 1) * 100),
    
    getConfidenceLevel(confidence) {
        const c = confidence || 1;
        if (c >= 0.8) return 'high';
        if (c >= 0.5) return 'medium';
        return 'low';
    },
    
    getRiskLevel(blastRadius) {
        if (blastRadius >= 10) return 'critical';
        if (blastRadius >= 5) return 'high';
        if (blastRadius >= 3) return 'medium';
        return null;
    }
};

// ═══════════════════════════════════════════════════════════════════════════
// APPLICATION STATE
// ═══════════════════════════════════════════════════════════════════════════

const AppState = {
    nodeMap: {},
    outgoingEdges: {},
    incomingEdges: {},
    blastRadiusCache: {},
    mode: 'downstream',
    currentNode: null,
    currentEdge: null,
    tracePath: [],
    _listeners: new Map(),
    
    subscribe(event, cb) {
        if (!this._listeners.has(event)) this._listeners.set(event, new Set());
        this._listeners.get(event).add(cb);
    },
    emit(event, data) { this._listeners.get(event)?.forEach(cb => cb(data)); },
    setMode(mode) { this.mode = mode; this.emit('modeChange', mode); },
    selectNode(node, edge = null) { this.currentNode = node; this.currentEdge = edge; this.emit('nodeSelect', { node, edge }); }
};

// ═══════════════════════════════════════════════════════════════════════════
// DATA PROCESSING
// ═══════════════════════════════════════════════════════════════════════════

const DataProcessor = {
    indexGraphData(rawData) {
        AppState.nodeMap = {};
        AppState.outgoingEdges = {};
        AppState.incomingEdges = {};
        
        (rawData.nodes || []).forEach(n => AppState.nodeMap[n.id] = n);
        (rawData.edges || []).forEach(e => {
            if (!AppState.outgoingEdges[e.source_id]) AppState.outgoingEdges[e.source_id] = [];
            AppState.outgoingEdges[e.source_id].push(e);
            if (!AppState.incomingEdges[e.target_id]) AppState.incomingEdges[e.target_id] = [];
            AppState.incomingEdges[e.target_id].push(e);
        });
        
        this.computeBlastRadius();
    },
    
    computeBlastRadius() {
        Object.keys(AppState.nodeMap).forEach(nodeId => {
            const visited = new Set();
            const queue = [nodeId];
            while (queue.length > 0) {
                const current = queue.shift();
                if (visited.has(current)) continue;
                visited.add(current);
                (AppState.outgoingEdges[current] || []).forEach(e => {
                    if (!visited.has(e.target_id)) queue.push(e.target_id);
                });
            }
            AppState.blastRadiusCache[nodeId] = visited.size - 1;
        });
    },
    
    getDomainForNode(node) {
        const t = (node.type || '').toLowerCase();
        const id = (node.id || '').toLowerCase();
        if (t.includes('infra') || id.startsWith('infra:') || id.includes('k8s:')) return 'Infrastructure';
        if (t.includes('env') || t.includes('config') || t.includes('secret') || id.startsWith('env:')) return 'Configuration';
        if (t.includes('data') || id.startsWith('data:')) return 'Data';
        return 'Code';
    },
    
    getNodesByDomain() {
        const groups = { 'Infrastructure': [], 'Configuration': [], 'Code': [], 'Data': [] };
        Object.values(AppState.nodeMap).forEach(n => {
            const domain = this.getDomainForNode(n);
            if (groups[domain]) groups[domain].push(n);
        });
        return groups;
    }
};

// ═══════════════════════════════════════════════════════════════════════════
// DOM BUILDERS
// ═══════════════════════════════════════════════════════════════════════════

const DOMBuilders = {
    createColumn(title, count, icon = null) {
        const col = document.createElement('div');
        col.className = 'column';
        col.innerHTML = `
            <div class="column-header">
                <span class="column-title">${icon ? `<span>${icon}</span>` : ''}${Utils.escapeHtml(title)}</span>
                <span class="column-count">${count}</span>
            </div>
            <div class="column-list"></div>`;
        return col;
    },
    
    createDomainItem(domain, nodes) {
        const blastTotal = nodes.reduce((sum, n) => sum + (AppState.blastRadiusCache[n.id] || 0), 0);
        const avgBlast = nodes.length > 0 ? Math.round(blastTotal / nodes.length) : 0;
        const riskLevel = Utils.getRiskLevel(avgBlast);
        
        const item = document.createElement('div');
        item.className = 'item';
        item.dataset.domain = domain;
        item.innerHTML = `
            <div class="item-icon">${Utils.getCategoryIcon(domain)}</div>
            <div class="item-content">
                <div class="item-title">${domain}</div>
                <div class="item-subtitle">${nodes.length} artifact${nodes.length !== 1 ? 's' : ''}</div>
                ${riskLevel ? `<div class="indicators"><span class="risk-indicator risk-indicator--${riskLevel}">⚡ ${avgBlast} avg</span></div>` : ''}
            </div>
            <span class="item-chevron">›</span>`;
        return item;
    },
    
    createNodeItem(node, edge = null, index = 0) {
        const item = document.createElement('div');
        let classes = ['item'];
        const changeType = node.metadata?.change_type;
        if (changeType === 'added') classes.push('diff-added');
        if (changeType === 'removed') classes.push('diff-removed');
        if (changeType === 'modified') classes.push('diff-modified');
        
        item.className = classes.join(' ');
        item.style.animationDelay = `${index * 0.02}s`;
        item.dataset.nodeId = node.id;
        
        const icon = Utils.getNodeIcon(node.type, node.id);
        const blastRadius = AppState.blastRadiusCache[node.id] || 0;
        const riskLevel = Utils.getRiskLevel(blastRadius);
        
        let indicatorsHtml = '';
        if (edge || riskLevel) {
            indicatorsHtml = '<div class="indicators">';
            if (edge) {
                const conf = edge.confidence || 1;
                const confLevel = Utils.getConfidenceLevel(conf);
                indicatorsHtml += `<span class="confidence-indicator confidence-indicator--${confLevel}"><span class="confidence-dot"></span>${Utils.formatConfidence(conf)}%</span>`;
            }
            if (riskLevel) indicatorsHtml += `<span class="risk-indicator risk-indicator--${riskLevel}">⚡ ${blastRadius}</span>`;
            indicatorsHtml += '</div>';
        }
        
        let edgeInfoHtml = '';
        if (edge) {
            const edgeIcon = Utils.getEdgeTypeIcon(edge.type);
            const via = edge.metadata?.via || edge.metadata?.env_var || edge.metadata?.matched_key || '';
            const edgeType = (edge.type || 'link').toUpperCase();
            let badgeClass = '';
            const et = (edge.type || '').toLowerCase();
            if (et.includes('read')) badgeClass = 'edge-badge--reads';
            else if (et.includes('provide')) badgeClass = 'edge-badge--provides';
            else if (et.includes('provision')) badgeClass = 'edge-badge--provisions';
            
            edgeInfoHtml = `<div class="edge-info"><span class="edge-badge ${badgeClass}"><span class="edge-badge-icon">${edgeIcon}</span><span class="edge-badge-text">${edgeType}${via ? ` via ${via}` : ''}</span></span></div>`;
        }
        
        item.innerHTML = `
            <div class="item-icon">${icon}</div>
            <div class="item-content">
                <div class="item-title">${Utils.escapeHtml(node.name)}</div>
                <div class="item-subtitle">${Utils.escapeHtml(node.type)}</div>
                ${indicatorsHtml}
                ${edgeInfoHtml}
            </div>
            <span class="item-chevron">›</span>`;
        return item;
    }
};

// ═══════════════════════════════════════════════════════════════════════════
// COLUMN RENDERER
// ═══════════════════════════════════════════════════════════════════════════

const ColumnRenderer = {
    wrapper: null,
    init() { this.wrapper = document.getElementById('columnsWrapper'); },
    
    removeColumnsAfter(index) {
        while (this.wrapper.children.length > index + 1) this.wrapper.removeChild(this.wrapper.lastChild);
    },
    
    renderRootColumn() {
        this.wrapper.innerHTML = '';
        AppState.tracePath = [];
        const groups = DataProcessor.getNodesByDomain();
        const totalNodes = Object.values(AppState.nodeMap).length;
        const col = DOMBuilders.createColumn('Domains', totalNodes, '🗂️');
        const list = col.querySelector('.column-list');
        
        Object.entries(groups).forEach(([domain, nodes]) => {
            if (nodes.length === 0) return;
            const item = DOMBuilders.createDomainItem(domain, nodes);
            item.onclick = () => {
                this.highlightItem(item);
                AppState.tracePath = [domain];
                this.renderNodeList(nodes, domain, 0);
            };
            list.appendChild(item);
        });
        this.wrapper.appendChild(col);
    },
    
    renderNodeList(nodes, title, parentColIndex) {
        this.removeColumnsAfter(parentColIndex);
        const sortedNodes = [...nodes].sort((a, b) => {
            const brDiff = (AppState.blastRadiusCache[b.id] || 0) - (AppState.blastRadiusCache[a.id] || 0);
            return brDiff !== 0 ? brDiff : a.name.localeCompare(b.name);
        });
        
        const icon = Utils.getCategoryIcon(title);
        const col = DOMBuilders.createColumn(title, sortedNodes.length, icon);
        const list = col.querySelector('.column-list');
        const myColIndex = parentColIndex + 1;
        
        sortedNodes.forEach((node, idx) => {
            const item = DOMBuilders.createNodeItem(node, null, idx);
            item.onclick = () => {
                this.highlightItem(item);
                AppState.tracePath = AppState.tracePath.slice(0, myColIndex);
                AppState.tracePath.push(node.id);
                AppState.selectNode(node, null);
                this.renderConnections(node, myColIndex);
            };
            item.onmouseenter = () => TraceHighlighter.highlight(node.id, myColIndex);
            item.onmouseleave = () => TraceHighlighter.clear();
            list.appendChild(item);
        });
        
        this.wrapper.appendChild(col);
        col.scrollIntoView({ behavior: 'smooth', inline: 'end' });
    },
    
    renderConnections(node, parentColIndex) {
        this.removeColumnsAfter(parentColIndex);
        let connections = [], title = '', icon = '';
        
        if (AppState.mode === 'downstream') {
            connections = (AppState.outgoingEdges[node.id] || []).map(e => ({ node: AppState.nodeMap[e.target_id], edge: e })).filter(c => c.node);
            title = 'Impacts'; icon = '↓';
        } else {
            connections = (AppState.incomingEdges[node.id] || []).map(e => ({ node: AppState.nodeMap[e.source_id], edge: e })).filter(c => c.node);
            title = 'Dependencies'; icon = '↑';
        }
        
        if (connections.length === 0) return;
        connections.sort((a, b) => (b.edge.confidence || 1) - (a.edge.confidence || 1));
        
        const col = DOMBuilders.createColumn(title, connections.length, icon);
        const list = col.querySelector('.column-list');
        const myColIndex = parentColIndex + 1;
        
        connections.forEach(({ node: connNode, edge }, idx) => {
            const item = DOMBuilders.createNodeItem(connNode, edge, idx);
            item.onclick = () => {
                this.highlightItem(item);
                AppState.tracePath = AppState.tracePath.slice(0, myColIndex);
                AppState.tracePath.push(connNode.id);
                AppState.selectNode(connNode, edge);
                this.renderConnections(connNode, myColIndex);
            };
            item.onmouseenter = () => TraceHighlighter.highlight(connNode.id, myColIndex);
            item.onmouseleave = () => TraceHighlighter.clear();
            list.appendChild(item);
        });
        
        this.wrapper.appendChild(col);
        col.scrollIntoView({ behavior: 'smooth', inline: 'end' });
    },
    
    highlightItem(item) {
        Array.from(item.parentElement.children).forEach(c => c.classList.remove('active'));
        item.classList.add('active');
    }
};

// ═══════════════════════════════════════════════════════════════════════════
// TRACE HIGHLIGHTER
// ═══════════════════════════════════════════════════════════════════════════

const TraceHighlighter = {
    highlight(nodeId, columnIndex) {
        this.clear();
        const wrapper = document.getElementById('columnsWrapper');
        const columns = Array.from(wrapper.children);
        for (let i = 0; i <= columnIndex; i++) columns[i]?.classList.add('in-trace-path');
        AppState.tracePath.forEach(pathNodeId => {
            document.querySelector(`.item[data-node-id="${pathNodeId}"]`)?.classList.add('in-trace');
        });
        document.querySelector(`.item[data-node-id="${nodeId}"]`)?.classList.add('in-trace');
    },
    clear() {
        document.querySelectorAll('.in-trace-path').forEach(el => el.classList.remove('in-trace-path'));
        document.querySelectorAll('.in-trace').forEach(el => el.classList.remove('in-trace'));
    }
};

// ═══════════════════════════════════════════════════════════════════════════
// INSPECTOR PANEL
// ═══════════════════════════════════════════════════════════════════════════

const Inspector = {
    element: null,
    currentTab: 'evidence',
    
    init() {
        this.element = document.getElementById('inspector');
        document.querySelectorAll('.inspector-tab').forEach(tab => {
            tab.onclick = () => this.switchTab(tab.dataset.tab);
        });
    },
    
    switchTab(tabName) {
        this.currentTab = tabName;
        document.querySelectorAll('.inspector-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tabName));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.toggle('active', c.id === `view-${tabName}`));
    },
    
    update(node, contextEdge = null) {
        this.element.classList.add('visible');
        document.getElementById('insp-icon').textContent = Utils.getNodeIcon(node.type, node.id);
        document.getElementById('insp-title').textContent = node.name;
        document.getElementById('insp-id').textContent = node.id;
        
        const btnEditor = document.getElementById('btn-editor');
        btnEditor.disabled = !node.path;
        btnEditor.title = node.path || 'No file path available';
        
        const upEdges = AppState.incomingEdges[node.id] || [];
        const downEdges = AppState.outgoingEdges[node.id] || [];
        document.getElementById('tab-up-count').textContent = upEdges.length;
        document.getElementById('tab-down-count').textContent = downEdges.length;
        
        this.renderEvidenceTab(node, contextEdge);
        this.renderDetailsTab(node);
        this.renderDependencyTab('view-upstream', upEdges, 'source_id');
        this.renderDependencyTab('view-downstream', downEdges, 'target_id');
        this.switchTab('evidence');
    },
    
    renderEvidenceTab(node, edge) {
        const container = document.getElementById('view-evidence');
        const blastRadius = AppState.blastRadiusCache[node.id] || 0;
        let html = '';
        
        if (edge) {
            const conf = edge.confidence || 1;
            const confLevel = Utils.getConfidenceLevel(conf);
            const confPercent = Utils.formatConfidence(conf);
            
            html += `<div class="strength-meter">
                <div class="strength-header">
                    <span class="strength-label">Connection Confidence</span>
                    <span class="strength-value strength-value--${confLevel}">${confPercent}%</span>
                </div>
                <div class="strength-bar"><div class="strength-fill strength-fill--${confLevel}" style="width: ${confPercent}%"></div></div>
            </div>`;
            
            const evidence = this.buildEvidenceExplanation(edge, node);
            html += `<div class="evidence-card">
                <div class="evidence-card-header">
                    <span class="evidence-card-icon">🔗</span>
                    <span class="evidence-card-title">Why This Connection Exists</span>
                </div>
                <div class="evidence-card-body">
                    <p class="evidence-text">${evidence.explanation}</p>
                    ${evidence.sourceCode ? `<code class="evidence-code">${Utils.escapeHtml(evidence.sourceCode)}</code>` : ''}
                    ${evidence.targetCode ? `<code class="evidence-code">${Utils.escapeHtml(evidence.targetCode)}</code>` : ''}
                    ${edge.match_strategy ? `<div class="match-strategy">🎯 Match: <strong>${edge.match_strategy}</strong></div>` : ''}
                </div>
            </div>`;
        } else {
            const riskLevel = Utils.getRiskLevel(blastRadius) || 'low';
            const fillClass = riskLevel === 'critical' || riskLevel === 'high' ? 'low' : riskLevel === 'medium' ? 'medium' : 'high';
            html += `<div class="strength-meter">
                <div class="strength-header">
                    <span class="strength-label">Blast Radius</span>
                    <span class="strength-value strength-value--${fillClass}">${blastRadius}</span>
                </div>
                <div class="strength-bar"><div class="strength-fill strength-fill--${fillClass}" style="width: ${Math.min(100, blastRadius * 5)}%"></div></div>
            </div>`;
        }
        
        html += `<div class="evidence-card">
            <div class="evidence-card-header"><span class="evidence-card-icon">📍</span><span class="evidence-card-title">Location</span></div>
            <div class="evidence-card-body">${node.path ? `<code class="evidence-code">${Utils.escapeHtml(node.path)}</code>` : '<p class="evidence-text" style="color: var(--text-tertiary);">No file path available</p>'}</div>
        </div>`;
        
        if (node.metadata?.change_type) {
            const icons = { added: '➕', removed: '➖', modified: '✏️' };
            html += `<div class="evidence-card">
                <div class="evidence-card-header"><span class="evidence-card-icon">${icons[node.metadata.change_type] || '📝'}</span><span class="evidence-card-title">Change Detected</span></div>
                <div class="evidence-card-body"><p class="evidence-text">This artifact was <strong>${node.metadata.change_type}</strong> in the current changeset.</p></div>
            </div>`;
        }
        
        container.innerHTML = html;
    },
    
    buildEvidenceExplanation(edge, targetNode) {
        const sourceNode = AppState.nodeMap[edge.source_id];
        const via = edge.metadata?.via || edge.metadata?.env_var || edge.metadata?.matched_key || '';
        const edgeType = (edge.type || '').toLowerCase();
        
        if (edgeType === 'provides' || via) {
            return {
                explanation: `<span class="evidence-highlight">${Utils.escapeHtml(sourceNode?.name || edge.source_id)}</span> outputs a value that <span class="evidence-highlight">${Utils.escapeHtml(targetNode.name)}</span> reads via <code style="background: var(--surface-3); padding: 2px 6px; border-radius: 4px;">${Utils.escapeHtml(via)}</code>.`,
                sourceCode: sourceNode?.path?.endsWith('.tf') ? `# ${sourceNode.path}\\noutput "${via}" {\\n  value = aws_db_instance.payment_db.endpoint\\n}` : null,
                targetCode: targetNode.path?.endsWith('.py') ? `# ${targetNode.path}\\nimport os\\ndb_host = os.getenv('${via}')` : null
            };
        }
        if (edgeType === 'reads') {
            return {
                explanation: `<span class="evidence-highlight">${Utils.escapeHtml(sourceNode?.name || edge.source_id)}</span> directly reads from <span class="evidence-highlight">${Utils.escapeHtml(targetNode.name)}</span>.`,
                sourceCode: edge.metadata?.line ? `# Line ${edge.metadata.line}\\n# Pattern: ${edge.metadata?.pattern || 'static analysis'}` : null,
                targetCode: null
            };
        }
        if (edgeType === 'provisions') {
            return {
                explanation: `<span class="evidence-highlight">${Utils.escapeHtml(sourceNode?.name || edge.source_id)}</span> provisions and manages the lifecycle of <span class="evidence-highlight">${Utils.escapeHtml(targetNode.name)}</span>.`,
                sourceCode: null, targetCode: null
            };
        }
        return {
            explanation: `Static analysis detected a <span class="evidence-highlight">${edge.type || 'dependency'}</span> relationship.${edge.metadata?.explanation ? `<br><br><em>${Utils.escapeHtml(edge.metadata.explanation)}</em>` : ''}`,
            sourceCode: null, targetCode: null
        };
    },
    
    renderDetailsTab(node) {
        const container = document.getElementById('view-details');
        let metadataRows = Object.entries(node.metadata || {}).map(([k, v]) => 
            `<div class="detail-row"><span class="detail-label">${Utils.escapeHtml(k)}</span><span class="detail-value">${Utils.escapeHtml(JSON.stringify(v))}</span></div>`
        ).join('');
        
        container.innerHTML = `
            <div class="detail-section">
                <div class="detail-section-title">Core Properties</div>
                <div class="detail-row"><span class="detail-label">Type</span><span class="detail-value">${Utils.escapeHtml(node.type)}</span></div>
                <div class="detail-row"><span class="detail-label">ID</span><span class="detail-value">${Utils.escapeHtml(node.id)}</span></div>
                ${node.path ? `<div class="detail-row"><span class="detail-label">Path</span><span class="detail-value">${Utils.escapeHtml(node.path)}</span></div>` : ''}
            </div>
            ${metadataRows ? `<div class="detail-section"><div class="detail-section-title">Metadata</div>${metadataRows}</div>` : ''}
            <div class="detail-section">
                <div class="detail-section-title">Impact Analysis</div>
                <div class="detail-row"><span class="detail-label">Blast Radius</span><span class="detail-value">${AppState.blastRadiusCache[node.id] || 0} downstream</span></div>
                <div class="detail-row"><span class="detail-label">Upstream</span><span class="detail-value">${(AppState.incomingEdges[node.id] || []).length} deps</span></div>
                <div class="detail-row"><span class="detail-label">Downstream</span><span class="detail-value">${(AppState.outgoingEdges[node.id] || []).length} deps</span></div>
            </div>`;
    },
    
    renderDependencyTab(elementId, edges, nodeKey) {
        const container = document.getElementById(elementId);
        if (edges.length === 0) {
            container.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📭</div><div>No dependencies found</div></div>';
            return;
        }
        
        container.innerHTML = `<div class="dep-list">${edges.map(edge => {
            const otherNode = AppState.nodeMap[edge[nodeKey]];
            if (!otherNode) return '';
            const icon = Utils.getNodeIcon(otherNode.type, otherNode.id);
            const conf = edge.confidence || 1;
            const confLevel = Utils.getConfidenceLevel(conf);
            return `<div class="dep-item" onclick="jumpToNode('${otherNode.id}')">
                <span class="dep-item-icon">${icon}</span>
                <div class="dep-item-content">
                    <div class="dep-item-name">${Utils.escapeHtml(otherNode.name)}</div>
                    <div class="dep-item-type">${Utils.escapeHtml(otherNode.type)}</div>
                </div>
                <span class="confidence-indicator confidence-indicator--${confLevel}"><span class="confidence-dot"></span>${Utils.formatConfidence(conf)}%</span>
            </div>`;
        }).join('')}</div>`;
    }
};

// ═══════════════════════════════════════════════════════════════════════════
// SEARCH
// ═══════════════════════════════════════════════════════════════════════════

const Search = {
    input: null, results: null,
    
    init() {
        this.input = document.querySelector('.search-input');
        this.results = document.getElementById('searchResults');
        this.input.addEventListener('input', Utils.debounce((e) => this.handleSearch(e.target.value), 150));
        this.input.addEventListener('focus', () => { if (this.input.value.length >= 2) this.results.classList.add('visible'); });
        document.addEventListener('click', (e) => { if (!e.target.closest('.search-container')) this.results.classList.remove('visible'); });
    },
    
    handleSearch(query) {
        if (query.length < 2) { this.results.classList.remove('visible'); return; }
        const queryLower = query.toLowerCase();
        const matches = Object.values(AppState.nodeMap).filter(n => 
            n.name.toLowerCase().includes(queryLower) || n.id.toLowerCase().includes(queryLower)
        ).slice(0, 12);
        
        if (matches.length > 0) {
            this.results.innerHTML = matches.map(node => {
                const icon = Utils.getNodeIcon(node.type, node.id);
                const highlighted = this.highlightMatch(node.name, query);
                return `<div class="search-item" onclick="jumpToNode('${node.id}')">
                    <span class="search-item-icon">${icon}</span>
                    <div class="search-item-content">
                        <div class="search-item-name">${highlighted}</div>
                        <div class="search-item-type">${Utils.escapeHtml(node.type)}</div>
                    </div>
                </div>`;
            }).join('');
            this.results.classList.add('visible');
        } else {
            this.results.innerHTML = '<div class="search-item" style="cursor: default; color: var(--text-tertiary);">No matching artifacts found</div>';
            this.results.classList.add('visible');
        }
    },
    
    highlightMatch(text, query) {
        const idx = text.toLowerCase().indexOf(query.toLowerCase());
        if (idx === -1) return Utils.escapeHtml(text);
        return `${Utils.escapeHtml(text.slice(0, idx))}<strong>${Utils.escapeHtml(text.slice(idx, idx + query.length))}</strong>${Utils.escapeHtml(text.slice(idx + query.length))}`;
    }
};

// ═══════════════════════════════════════════════════════════════════════════
// MESH VISUALIZATION
// ═══════════════════════════════════════════════════════════════════════════

const MeshVisualization = {
    modal: null,
    init() { this.modal = document.getElementById('meshModal'); },
    open() {
        if (!AppState.currentNode) return;
        this.modal.classList.add('visible');
        setTimeout(() => this.render(AppState.currentNode), 100);
    },
    close() {
        this.modal.classList.remove('visible');
        document.getElementById('mesh-container').innerHTML = '';
    },
    render(centerNode) {
        const container = document.getElementById('mesh-container');
        container.innerHTML = '';
        const width = container.clientWidth, height = container.clientHeight;
        
        const nodeSet = new Set([centerNode.id]);
        const links = [];
        
        [...(AppState.incomingEdges[centerNode.id] || []), ...(AppState.outgoingEdges[centerNode.id] || [])].forEach(e => {
            nodeSet.add(e.source_id); nodeSet.add(e.target_id);
            links.push({ source: e.source_id, target: e.target_id });
        });
        
        const graphNodes = Array.from(nodeSet).map(id => ({ id, name: AppState.nodeMap[id]?.name || id, isCenter: id === centerNode.id }));
        
        const svg = d3.select("#mesh-container").append("svg").attr("width", width).attr("height", height);
        const g = svg.append("g");
        svg.call(d3.zoom().scaleExtent([0.2, 4]).on("zoom", (event) => g.attr("transform", event.transform)));
        
        const simulation = d3.forceSimulation(graphNodes)
            .force("link", d3.forceLink(links).id(d => d.id).distance(80))
            .force("charge", d3.forceManyBody().strength(-200))
            .force("center", d3.forceCenter(width / 2, height / 2));
        
        const link = g.append("g").selectAll("line").data(links).join("line").attr("stroke", "#555").attr("stroke-opacity", 0.6);
        const node = g.append("g").selectAll("g").data(graphNodes).join("g")
            .call(d3.drag().on("start", (e) => { if (!e.active) simulation.alphaTarget(0.3).restart(); e.subject.fx = e.subject.x; e.subject.fy = e.subject.y; })
            .on("drag", (e) => { e.subject.fx = e.x; e.subject.fy = e.y; })
            .on("end", (e) => { if (!e.active) simulation.alphaTarget(0); e.subject.fx = null; e.subject.fy = null; }))
            .on("click", (e, d) => { this.close(); jumpToNode(d.id); });
        
        node.append("circle").attr("r", d => d.isCenter ? 12 : 8).attr("fill", d => d.isCenter ? "#fff" : "#3b82f6");
        node.append("text").text(d => d.name).attr("x", 14).attr("y", 4).style("font-size", "10px").style("fill", "#ccc");
        
        simulation.on("tick", () => {
            link.attr("x1", d => d.source.x).attr("y1", d => d.source.y).attr("x2", d => d.target.x).attr("y2", d => d.target.y);
            node.attr("transform", d => `translate(${d.x},${d.y})`);
        });
    }
};

// ═══════════════════════════════════════════════════════════════════════════
// GLOBAL FUNCTIONS & INITIALIZATION
// ═══════════════════════════════════════════════════════════════════════════

function jumpToNode(nodeId) {
    document.getElementById('searchResults').classList.remove('visible');
    document.querySelector('.search-input').value = '';
    const node = AppState.nodeMap[nodeId];
    if (!node) return;
    const domain = DataProcessor.getDomainForNode(node);
    ColumnRenderer.renderRootColumn();
    setTimeout(() => {
        document.querySelectorAll('.column:first-child .item').forEach(item => {
            if (item.textContent.includes(domain)) item.click();
        });
        setTimeout(() => { AppState.selectNode(node); Inspector.update(node); }, 100);
    }, 50);
}

function openEditor() {
    if (AppState.currentNode?.path) {
        const line = AppState.currentNode.metadata?.line || 1;
        window.location.href = `vscode://file/${AppState.currentNode.path}:${line}`;
    }
}

function setMode(mode) {
    AppState.setMode(mode);
    document.querySelectorAll('.mode-btn').forEach(btn => btn.classList.toggle('active', btn.dataset.mode === mode));
    ColumnRenderer.renderRootColumn();
}

function updateStats() {
    document.getElementById('stat-nodes').textContent = Object.keys(AppState.nodeMap).length;
    document.getElementById('stat-edges').textContent = (rawData.edges || []).length;
    document.getElementById('stat-risk').textContent = Object.values(AppState.blastRadiusCache).filter(br => br > 5).length;
}

window.onload = function() {
    if (typeof rawData !== 'undefined') {
        DataProcessor.indexGraphData(rawData);
        ColumnRenderer.init();
        Inspector.init();
        Search.init();
        MeshVisualization.init();
        ColumnRenderer.renderRootColumn();
        updateStats();
        
        AppState.subscribe('nodeSelect', ({ node, edge }) => Inspector.update(node, edge));
    }
    
    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); document.querySelector('.search-input').focus(); }
        if (e.key === 'Escape') { document.getElementById('searchResults').classList.remove('visible'); MeshVisualization.close(); }
    });
};

// Expose for HTML onclick handlers
window.jumpToNode = jumpToNode;
window.openEditor = openEditor;
window.setMode = setMode;
window.openMeshModal = () => MeshVisualization.open();
window.closeMeshModal = () => MeshVisualization.close();
"""

# =============================================================================
# HTML TEMPLATE
# =============================================================================
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jnkn Impact Cockpit</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>{styles}</style>
</head>
<body>
    <header class="header">
        <div class="brand">
            <div class="brand-logo">J</div>
            <div class="brand-text">
                <span class="brand-name">Jnkn</span>
                <span class="brand-subtitle">Impact Cockpit</span>
            </div>
        </div>
        
        <div class="stats-bar">
            <div class="stat"><span class="stat-label">Nodes</span><span class="stat-value" id="stat-nodes">0</span></div>
            <div class="stat"><span class="stat-label">Edges</span><span class="stat-value" id="stat-edges">0</span></div>
            <div class="stat stat--critical"><span class="stat-label">High Risk</span><span class="stat-value" id="stat-risk">0</span></div>
        </div>
        
        <div class="mode-toggle">
            <button class="mode-btn active" data-mode="downstream" onclick="setMode('downstream')">↓ Impact</button>
            <button class="mode-btn" data-mode="upstream" onclick="setMode('upstream')">↑ Depends</button>
        </div>
        
        <div class="search-container">
            <span class="search-icon">⌕</span>
            <input type="text" class="search-input" placeholder="Search artifacts...">
            <span class="search-kbd">⌘K</span>
            <div class="search-results" id="searchResults"></div>
        </div>
    </header>
    
    <main class="main-container">
        <div class="columns-wrapper" id="columnsWrapper"></div>
        
        <aside class="inspector" id="inspector">
            <div class="inspector-header">
                <div class="inspector-header-top">
                    <div class="inspector-icon" id="insp-icon">📄</div>
                    <div class="inspector-meta">
                        <div class="inspector-title" id="insp-title">Select an artifact</div>
                        <div class="inspector-id" id="insp-id"></div>
                    </div>
                </div>
                <div class="action-bar">
                    <button class="btn btn--primary" id="btn-editor" onclick="openEditor()" disabled>
                        <span class="btn-icon">📝</span> Open in VS Code
                    </button>
                    <button class="btn" onclick="openMeshModal()">
                        <span class="btn-icon">🕸️</span> Graph
                    </button>
                </div>
            </div>
            
            <div class="inspector-tabs">
                <div class="inspector-tab active" data-tab="evidence">Evidence</div>
                <div class="inspector-tab" data-tab="details">Details</div>
                <div class="inspector-tab" data-tab="upstream">↑ <span class="tab-count" id="tab-up-count">0</span></div>
                <div class="inspector-tab" data-tab="downstream">↓ <span class="tab-count" id="tab-down-count">0</span></div>
            </div>
            
            <div id="view-evidence" class="tab-content active"></div>
            <div id="view-details" class="tab-content"></div>
            <div id="view-upstream" class="tab-content"></div>
            <div id="view-downstream" class="tab-content"></div>
        </aside>
    </main>

    <div class="modal-overlay" id="meshModal">
        <div class="modal-content">
            <div class="modal-header">
                <h3 class="modal-title">🕸️ Neighborhood Graph</h3>
                <button class="btn" style="width: auto;" onclick="closeMeshModal()">✕ Close</button>
            </div>
            <div id="mesh-container"></div>
        </div>
    </div>

    <script>
        const rawData = {data};
        {scripts}
    </script>
</body>
</html>"""


def build_html(graph_json: str) -> str:
    """Assemble the final HTML using embedded assets."""
    return HTML_TEMPLATE.format(
        styles=CSS_CONTENT,
        data=graph_json,
        scripts=JS_CONTENT
    )