"""
SDLC Agent Pipeline — Streamlit UI  (v4)
─────────────────────────────────────────
v4 enhancements:
  • Gradient hero, design-system CSS variables, polished cards
  • Deployment visual card selector (localhost / GCP / AWS / Azure)
  • Live Status: step-dot tracker, per-agent timing, ETA, filterable log
  • Outputs: Download All as ZIP, file-type icons, total size, line counts
  • Analytics Dashboard: run-history table + charts (files, duration, agents)
"""

from __future__ import annotations

import asyncio
import io
import json
import queue as stdlib_queue
import re
import threading
import time
import uuid
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st

from config.settings import settings
from config.logging import setup_logging
from database.db import init_db
from models.pipeline_state import PipelineState, AgentStatus
from orchestrator.pipeline import PipelineOrchestrator, AGENT_SEQUENCE, TOTAL_AGENTS
from orchestrator.state_manager import PipelineStateManager
from orchestrator.events import event_bus

@st.cache_resource
def _bootstrap():
    setup_logging()
    init_db()

_bootstrap()

# ─── Constants ─────────────────────────────────────────────────────────────────

AGENT_META = [
    ("📥", "Requirements Intake",    "Extract FRs/NFRs from any format",                         "#4A90E2", "intake"),
    ("🔍", "Requirements Analysis",  "PRD, gap analysis, MoSCoW, KPIs",                          "#F5A623", "analysis"),
    ("🏗",  "Architecture & Design", "HLD, LLD, SQL schema, OpenAPI, ADRs",                      "#9C27B0", "architecture"),
    ("🔒", "Security & Compliance",  "STRIDE, OWASP Top-10, GDPR/SOC2",                          "#EF5350", "security"),
    ("💻", "Code Generation",        "Production backend source, Dockerfile, CI",                 "#43A047", "codegen"),
    ("⚛",  "Frontend Generation",   "React 18 + TypeScript SPA — full UI for the backend",       "#00BCD4", "frontend"),
    ("📖", "Documentation",          "Full-stack README, API reference, developer guide",         "#E91E63", "docs"),
    ("🧪", "QA & Testing",           "Unit, integration, E2E tests for frontend + backend",      "#00897B", "qa"),
    ("🔁", "Code Review",            "Quality gate: score, issues, coverage",                    "#FFB300", "review"),
    ("🚀", "Deployment",             "docker-compose / Terraform for complete app",               "#3F51B5", "deployment"),
    ("📊", "Monitoring",             "Prometheus, Grafana, alerts, runbooks",                    "#795548", "monitoring"),
    ("🛠",  "Support & Maintenance", "Runbooks, incident response, FAQ, SLA",                    "#7CB342", "support"),
    ("📦", "Packaging & Export",     "ZIP archive + START.sh + HOW_TO_RUN.md for instant launch","#0891b2", "packaging"),
]

DEPLOY_OPTIONS = {
    "localhost": {
        "label": "🖥  localhost",
        "subtitle": "Docker Compose",
        "color": "#00897B",
        "note": "Generates `docker-compose.yml` + startup scripts. No cloud account needed.",
        "badge": "Free · Offline",
    },
    "gcp": {
        "label": "☁️  GCP",
        "subtitle": "Google Cloud",
        "color": "#4285F4",
        "note": "Cloud Run · Cloud SQL · Memorystore · Artifact Registry + full Terraform.",
        "badge": "Serverless · Auto-scale",
    },
    "aws": {
        "label": "☁️  AWS",
        "subtitle": "Amazon Web Services",
        "color": "#FF9900",
        "note": "ECS Fargate · RDS Aurora · ElastiCache · ECR + full Terraform.",
        "badge": "Most popular",
    },
    "azure": {
        "label": "☁️  Azure",
        "subtitle": "Microsoft Azure",
        "color": "#0078D4",
        "note": "Container Apps · Azure DB · Redis Cache · Container Registry + Terraform.",
        "badge": "Enterprise ready",
    },
}

STATUS_EMOJI = {
    AgentStatus.PENDING:   "⏳",
    AgentStatus.RUNNING:   "⚡",
    AgentStatus.COMPLETED: "✅",
    AgentStatus.FAILED:    "❌",
    AgentStatus.SKIPPED:   "⏭️",
}

FILE_ICONS = {
    "py": "🐍", "yml": "⚙️", "yaml": "⚙️", "sql": "🗄️", "md": "📝",
    "json": "📋", "tf": "🏗️", "sh": "⚡", "js": "🟨", "ts": "🔷",
    "html": "🌐", "css": "🎨", "toml": "⚙️", "dockerfile": "🐳",
    "env": "🔑", "gitignore": "🙈", "txt": "📄", "feature": "🥒",
    "lock": "🔒",
}

LANG_MAP = {
    "py": "python", "yml": "yaml", "yaml": "yaml", "sql": "sql",
    "md": "markdown", "json": "json", "tf": "hcl", "sh": "bash",
    "js": "javascript", "ts": "typescript", "html": "html",
    "css": "css", "toml": "toml", "ini": "ini", "txt": "text",
    "feature": "gherkin",
}

OUTPUT_CATEGORIES = {
    "📋 Requirements":  "requirements",
    "🏛 Architecture":  "architecture",   # simple emoji — no variation selector
    "🔒 Security":      "security",
    "💻 Code":          "code",
    "🧪 Tests":         "tests",
    "📖 Docs":          "docs",
    "🚀 Deployments":   "deployments",
}

# ─── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SDLC Agent Pipeline",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Design system CSS (v5 — modern dark-accent aesthetic) ────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

:root {
  --primary:    #6366f1;   /* indigo */
  --primary-dk: #4f46e5;
  --accent:     #06b6d4;   /* cyan */
  --success:    #10b981;   /* emerald */
  --warning:    #f59e0b;
  --error:      #ef4444;
  --surface:    #ffffff;
  --surface2:   #f8fafc;
  --surface3:   #f1f5f9;
  --border:     #e2e8f0;
  --border2:    #cbd5e1;
  --text:       #0f172a;
  --text-2:     #334155;
  --text-muted: #64748b;
  --radius:     12px;
  --radius-sm:  8px;
  --shadow:     0 1px 3px rgba(0,0,0,.08), 0 1px 2px rgba(0,0,0,.06);
  --shadow-md:  0 4px 6px rgba(0,0,0,.07), 0 2px 4px rgba(0,0,0,.06);
  --shadow-lg:  0 10px 15px rgba(0,0,0,.08), 0 4px 6px rgba(0,0,0,.05);
  --glow:       0 0 20px rgba(99,102,241,.25);
}

/* Scope font only to content elements — never use * with !important here.
   Streamlit renders arrow/icon components with SVG + hidden aria spans;
   a global * font override makes those hidden spans visible as "_arr" text. */
html, body, .stApp,
h1, h2, h3, h4, h5, h6,
p, li, td, th, label, button, input, select, textarea,
.stMarkdown, .stText, .stCaption {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Explicitly keep Streamlit's internal SVG/icon elements untouched */
svg, svg *, [data-testid="stExpanderToggleIcon"],
[data-testid="stExpanderToggleIcon"] * { font-family: inherit; }

/* ── Agent cards ── */
.agent-card {
  display:flex; align-items:center; gap:12px;
  padding:11px 14px; border-radius:var(--radius-sm); margin:3px 0;
  border:1px solid var(--border); transition:all 0.2s; background:var(--surface);
  position:relative; overflow:hidden;
}
.agent-card::before {
  content:''; position:absolute; left:0; top:0; bottom:0;
  width:3px; border-radius:3px 0 0 3px;
}
.agent-pending::before   { background:#cbd5e1; }
.agent-running::before   { background:var(--primary); }
.agent-completed::before { background:var(--success); }
.agent-failed::before    { background:var(--error); }
.agent-skipped::before   { background:#94a3b8; }

.agent-pending   { opacity:.6; }
.agent-running   {
  background:linear-gradient(135deg, #eef2ff 0%, #fff 60%);
  box-shadow: var(--glow);
  animation: pulse-card 2s ease-in-out infinite;
}
.agent-completed { background:#f0fdf4; }
.agent-failed    { background:#fef2f2; }
.agent-skipped   { background:#f8fafc; opacity:.55; }

@keyframes pulse-card { 0%,100%{box-shadow:var(--glow)} 50%{box-shadow:0 0 30px rgba(99,102,241,.4)} }

.agent-icon  { font-size:18px; min-width:24px; text-align:center; }
.agent-body  { flex:1; min-width:0; }
.agent-title { font-size:12px; font-weight:700; margin:0; color:var(--text);
               white-space:nowrap; overflow:hidden; text-overflow:ellipsis; letter-spacing:-.1px; }
.agent-step  { font-size:10.5px; color:var(--primary); margin-top:2px; font-weight:500; }
.agent-summary { font-size:10.5px; color:var(--text-muted); margin-top:2px;
                 white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.agent-time  { font-size:10px; color:var(--text-muted); white-space:nowrap; margin-left:4px;
               font-variant-numeric:tabular-nums; }
.agent-badge {
  font-size:9px; font-weight:700; padding:2px 7px;
  border-radius:20px; white-space:nowrap; letter-spacing:.4px; text-transform:uppercase;
}
.badge-pending   { background:#f1f5f9; color:#64748b; }
.badge-running   { background:#eef2ff; color:#4f46e5; }
.badge-completed { background:#dcfce7; color:#15803d; }
.badge-failed    { background:#fee2e2; color:#dc2626; }
.badge-skipped   { background:#f1f5f9; color:#94a3b8; }

/* ── Pipeline timeline (horizontal) ── */
.pipeline-timeline {
  display:flex; align-items:center; gap:0;
  background:var(--surface2); border-radius:var(--radius); padding:14px 16px;
  border:1px solid var(--border); margin:12px 0; overflow-x:auto;
}
.tl-node {
  display:flex; flex-direction:column; align-items:center; gap:4px;
  flex-shrink:0; min-width:52px; cursor:default;
}
.tl-circle {
  width:32px; height:32px; border-radius:50%; display:flex; align-items:center;
  justify-content:center; font-size:12px; font-weight:800;
  border:2px solid transparent; transition:all .3s; position:relative;
}
.tl-done    { background:var(--success); color:#fff; border-color:var(--success); }
.tl-running {
  background:var(--primary); color:#fff; border-color:var(--primary);
  box-shadow:0 0 0 4px rgba(99,102,241,.3);
  animation: tl-pulse 1.5s ease-in-out infinite;
}
.tl-failed  { background:var(--error); color:#fff; border-color:var(--error); }
.tl-skipped { background:#e2e8f0; color:#94a3b8; border-color:#cbd5e1; }
.tl-pending { background:#f8fafc; color:#94a3b8; border-color:#e2e8f0; }
@keyframes tl-pulse { 0%,100%{box-shadow:0 0 0 4px rgba(99,102,241,.3)} 50%{box-shadow:0 0 0 8px rgba(99,102,241,.15)} }

.tl-label { font-size:8.5px; color:var(--text-muted); font-weight:600; text-align:center;
            letter-spacing:.2px; max-width:52px; line-height:1.3; }
.tl-connector { flex:1; height:2px; background:var(--border); min-width:8px; max-width:28px; }
.tl-connector-done { background:var(--success); }

/* ── Stats cards ── */
.stat-card {
  background:var(--surface); border-radius:var(--radius);
  padding:16px 18px; border:1px solid var(--border);
  box-shadow:var(--shadow); position:relative; overflow:hidden;
}
.stat-card::after {
  content:''; position:absolute; top:-20px; right:-20px;
  width:80px; height:80px; border-radius:50%;
  background:var(--card-color, var(--primary)); opacity:.06;
}
.stat-val  { font-size:30px; font-weight:900; line-height:1; letter-spacing:-1px; }
.stat-lbl  { font-size:10px; color:var(--text-muted); margin-top:4px;
             text-transform:uppercase; letter-spacing:.8px; font-weight:600; }
.stat-sub  { font-size:11px; color:var(--text-muted); margin-top:3px; font-weight:500; }

/* ── Hero banner ── */
.hero {
  background:linear-gradient(135deg, #1e1b4b 0%, #312e81 40%, #4338ca 75%, #6366f1 100%);
  border-radius:16px; padding:34px 40px; color:#fff; margin-bottom:24px;
  box-shadow:0 8px 32px rgba(99,102,241,.3), var(--shadow-lg);
  position:relative; overflow:hidden;
}
.hero::before {
  content:''; position:absolute; top:-60px; right:-60px;
  width:260px; height:260px; border-radius:50%;
  background:rgba(255,255,255,.05);
}
.hero::after {
  content:''; position:absolute; bottom:-40px; left:30%;
  width:180px; height:180px; border-radius:50%;
  background:rgba(6,182,212,.1);
}
.hero h1 { font-size:28px; font-weight:900; margin:0 0 10px; letter-spacing:-.5px; position:relative; z-index:1; }
.hero p  { font-size:14px; opacity:.88; margin:0; line-height:1.65; position:relative; z-index:1; }
.hero-badges { margin-top:18px; display:flex; gap:8px; flex-wrap:wrap; position:relative; z-index:1; }
.hero-badge {
  background:rgba(255,255,255,.12); border:1px solid rgba(255,255,255,.2);
  border-radius:20px; padding:4px 13px; font-size:11px; font-weight:600;
  backdrop-filter:blur(4px);
}

/* ── Deploy cards ── */
.deploy-card {
  border:2px solid var(--border); border-radius:var(--radius);
  padding:16px; cursor:pointer; transition:all .2s; background:var(--surface);
}
.deploy-card:hover { border-color:var(--primary); box-shadow:var(--shadow-md); transform:translateY(-1px); }
.deploy-selected {
  border-color:var(--primary);
  background:linear-gradient(135deg,#eef2ff,#fff);
  box-shadow:0 0 0 3px rgba(99,102,241,.15);
}
.deploy-label   { font-size:15px; font-weight:800; margin:0; }
.deploy-sub     { font-size:11px; color:var(--text-muted); margin:3px 0 0; }
.deploy-badge   { font-size:10px; font-weight:600; padding:2px 9px; border-radius:20px;
                  background:var(--surface3); color:var(--text-muted); margin-top:8px; display:inline-block; }

/* ── Log box ── */
.log-box {
  background:#0d1117; color:#c9d1d9; font-family:'Fira Code','JetBrains Mono',monospace;
  font-size:11px; padding:14px 16px; border-radius:var(--radius);
  height:380px; overflow-y:auto; line-height:1.75; border:1px solid #21262d;
}
.log-box::-webkit-scrollbar { width:4px; }
.log-box::-webkit-scrollbar-track { background:#161b22; }
.log-box::-webkit-scrollbar-thumb { background:#30363d; border-radius:4px; }
.log-info    { color:#79c0ff; }
.log-warning { color:#e3b341; }
.log-error   { color:#f85149; }
.log-success { color:#3fb950; }
.log-step    { color:#d2a8ff; font-weight:600; }
.log-cost    { color:#06b6d4; font-weight:600; }
.log-time    { color:#484f58; font-size:10px; margin-right:6px; }

/* ── Cost pill ── */
.cost-pill {
  display:inline-flex; align-items:center; gap:6px;
  background:linear-gradient(135deg,#ecfdf5,#d1fae5); border:1px solid #a7f3d0;
  border-radius:20px; padding:4px 12px; font-size:11px; font-weight:700; color:#065f46;
}

/* ── File tree ── */
.file-icon  { margin-right:4px; }
.file-info  { font-size:10px; color:#aaa; float:right; }

/* ── Section headers ── */
.section-hdr {
  font-size:10px; font-weight:800; text-transform:uppercase;
  letter-spacing:1.4px; color:#94a3b8; margin:12px 0 6px;
  padding-bottom:5px; border-bottom:1px solid var(--border);
}

/* ── Run card ── */
.run-card {
  border:1px solid var(--border); border-radius:var(--radius);
  padding:14px 18px; margin:6px 0; background:var(--surface);
  box-shadow:var(--shadow); transition:box-shadow .2s;
}
.run-card:hover { box-shadow:var(--shadow-md); }

/* ── Agent list on New Run ── */
.agent-list-item {
  padding:10px 14px; border-radius:var(--radius-sm); margin:4px 0;
  border-left:3px solid; background:var(--surface2);
  border:1px solid var(--border); border-left:3px solid;
}
.agent-list-title { font-size:12.5px; font-weight:700; margin:0; }
.agent-list-desc  { font-size:11px; color:var(--text-muted); margin-top:2px; }

/* ── Progress bar override ── */
div[data-testid="stProgress"] > div > div {
  background:linear-gradient(90deg, var(--primary), var(--accent)) !important;
}

/* ── Buttons ── */
div[data-testid="stButton"] button[kind="primary"] {
  background:linear-gradient(135deg,#6366f1,#4f46e5) !important;
  border:none !important; font-weight:700 !important; border-radius:8px !important;
  box-shadow:0 4px 12px rgba(99,102,241,.4) !important;
}
div[data-testid="stButton"] button[kind="primary"]:hover {
  background:linear-gradient(135deg,#4f46e5,#4338ca) !important;
  transform:translateY(-1px) !important;
}

div[data-testid="metric-container"] {
  background:var(--surface2); border-radius:var(--radius-sm);
  border:1px solid var(--border); padding:8px 12px;
}

/* ── Sidebar styling ── */
section[data-testid="stSidebar"] {
  background:linear-gradient(180deg, #1e1b4b 0%, #1e1b4b 100%) !important;
}
/* Don't use * — it breaks code/inline elements. Target specific tags only. */
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] div,
section[data-testid="stSidebar"] label { color:#e2e8f0; }
section[data-testid="stSidebar"] .stRadio label { color:#cbd5e1 !important; }
section[data-testid="stSidebar"] hr { border-color:#312e81 !important; }
/* Keep code/pre readable with accent colour */
section[data-testid="stSidebar"] code { color:#a5b4fc !important; background:rgba(255,255,255,.08) !important; }

/* ── Streamlit file-uploader — only style the visible drop zone border ── */
/* Do NOT target inner <button> or <span> — they have hidden accessibility
   duplicates that become visible when colour is forced on them.          */
[data-testid="stFileUploaderDropzone"] {
  border:2px dashed #cbd5e1;
  border-radius:var(--radius);
}

/* ── Metric / output-stat boxes ── */
.metric-box {
  background:var(--surface); border-radius:var(--radius);
  padding:16px 14px; text-align:center; border:1px solid var(--border);
  box-shadow:var(--shadow); transition:box-shadow .2s;
}
.metric-box:hover { box-shadow:var(--shadow-md); }
.metric-val  { font-size:26px; font-weight:900; color:var(--primary); line-height:1; }
.metric-lbl  { font-size:10px; color:var(--text-muted); margin-top:4px;
               text-transform:uppercase; letter-spacing:.8px; font-weight:700; }
.metric-sub  { font-size:11px; color:var(--text-muted); margin-top:3px; }

/* ── Tabs ── */
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
  color:var(--primary) !important; border-bottom-color:var(--primary) !important;
}
</style>
""", unsafe_allow_html=True)

# ─── Session state ──────────────────────────────────────────────────────────────

DEFAULTS: dict = {
    "pipeline_state":       None,
    "run_logs":             [],
    "running":              False,
    "dry_run_done":         False,
    "agent_substeps":       {},   # agent_id → sub-step string
    "agent_start_times":    {},   # agent_id → float (unix ts)
    "agent_durations":      {},   # agent_id → seconds
    "pipeline_start_time":  None, # float
    "selected_file":        None,
    "selected_cloud":       "gcp",
    "log_filter":           "All",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─── Helpers ───────────────────────────────────────────────────────────────────

def fmt_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{int(seconds)}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


def file_icon(path: Path) -> str:
    ext = path.suffix.lstrip(".").lower()
    if path.name.lower() == "dockerfile":
        return "🐳"
    return FILE_ICONS.get(ext, "📄")


def create_zip_bytes(files: list[Path], root: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            try:
                zf.write(f, f.relative_to(root))
            except Exception:
                pass
    buf.seek(0)
    return buf.getvalue()


def human_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    elif n < 1024 ** 2:
        return f"{n/1024:.1f} KB"
    return f"{n/1024**2:.1f} MB"


# ─── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown(
        '<div style="text-align:center;padding:16px 0 8px;">'
        '<div style="font-size:40px;filter:drop-shadow(0 0 12px rgba(99,102,241,.5))">🚀</div>'
        '<div style="font-size:16px;font-weight:900;letter-spacing:-.3px;color:#e2e8f0;margin-top:4px;">SDLC Pipeline</div>'
        '<div style="font-size:11px;color:#818cf8;margin-top:2px;">Multi-Agent · Claude AI</div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.divider()

    page = st.radio(
        "nav",
        ["🏠 New Run", "📊 Live Status", "📁 Outputs", "🚢 Deploy", "📈 Analytics", "⚙️ Settings"],
        label_visibility="collapsed",
    )
    st.divider()

    s: PipelineState | None = st.session_state.pipeline_state
    if s:
        results    = s.agent_results or []
        done       = sum(1 for r in results if r.status == AgentStatus.COMPLETED)
        failed     = sum(1 for r in results if r.status == AgentStatus.FAILED)
        skipped    = sum(1 for r in results if r.status == AgentStatus.SKIPPED)
        cloud_info = DEPLOY_OPTIONS.get(s.cloud_provider, {})

        st.markdown(f'<div style="font-size:13px;font-weight:800;color:#e2e8f0;">{s.project_name}</div>', unsafe_allow_html=True)
        st.markdown(f'<div style="font-size:10px;color:#818cf8;">{cloud_info.get("label", s.cloud_provider.upper())} · <code style="color:#94a3b8">{s.run_id[:10]}…</code></div>', unsafe_allow_html=True)
        st.progress(done / TOTAL_AGENTS, text=f"{done}/{TOTAL_AGENTS} agents done")

        if failed:
            st.markdown(f'<div style="color:#f87171;font-size:11px;">❌ {failed} failed</div>', unsafe_allow_html=True)
        if skipped:
            st.markdown(f'<div style="color:#94a3b8;font-size:11px;">⏭ {skipped} skipped</div>', unsafe_allow_html=True)

        if st.session_state.pipeline_start_time:
            elapsed = time.time() - st.session_state.pipeline_start_time
            st.markdown(f'<div style="color:#94a3b8;font-size:11px;">⏱ {fmt_duration(elapsed)}</div>', unsafe_allow_html=True)

        # Live cost counter
        try:
            from utils.claude_client import ClaudeClient
            usage = ClaudeClient.get().usage_summary()
            cost  = usage["estimated_cost_usd"]
            saved = usage["estimated_savings_usd"]
            st.markdown(
                f'<div class="cost-pill" style="margin-top:6px;">'
                f'💰 ~${cost:.4f} used · saved ${saved:.4f}</div>',
                unsafe_allow_html=True,
            )
        except Exception:
            pass
    else:
        st.markdown('<div style="color:#64748b;font-size:12px;">No pipeline active</div>', unsafe_allow_html=True)

    st.divider()
    st.markdown(f'<div style="color:#475569;font-size:10px;">Model: <code style="color:#818cf8">{settings.anthropic_model}</code></div>', unsafe_allow_html=True)
    st.markdown(f'<div style="color:#475569;font-size:10px;">Env: <code style="color:#818cf8">{settings.app_env}</code></div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: New Run
# ══════════════════════════════════════════════════════════════════════════════

if page == "🏠 New Run":
    # ── Hero ───────────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="hero">
      <h1>Multi-Agent SDLC Pipeline</h1>
      <p>Feed requirements in <strong>any format</strong> — PDF, SOP, transcript, video, audio —<br>
         and 12 AI agents build your entire software project end-to-end.</p>
      <div class="hero-badges">
        <span class="hero-badge">📥 Requirements Intake</span>
        <span class="hero-badge">🏗 Architecture</span>
        <span class="hero-badge">💻 Code Generation</span>
        <span class="hero-badge">🧪 QA &amp; Testing</span>
        <span class="hero-badge">🚀 Deployment</span>
        <span class="hero-badge">📊 Monitoring</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── Deployment Target — full-width 4-column row ────────────────────────────
    st.markdown('<div class="section-hdr">🎯 Deployment Target</div>', unsafe_allow_html=True)
    selected_cloud = st.session_state.selected_cloud
    dc1, dc2, dc3, dc4 = st.columns(4)
    deploy_cols = [dc1, dc2, dc3, dc4]

    for i, (cloud_key, info) in enumerate(DEPLOY_OPTIONS.items()):
        is_sel = selected_cloud == cloud_key
        cls    = "deploy-card deploy-selected" if is_sel else "deploy-card"
        check  = "✓ " if is_sel else ""
        with deploy_cols[i]:
            st.markdown(
                f'<div class="{cls}" style="border-color:{info["color"] if is_sel else "#e8eaed"};min-height:100px;">'
                f'<div class="deploy-label" style="color:{info["color"]}">{check}{info["label"]}</div>'
                f'<div class="deploy-sub">{info["subtitle"]}</div>'
                f'<div class="deploy-badge">{info["badge"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            if st.button("Select", key=f"deploy_{cloud_key}", use_container_width=True,
                         type="primary" if is_sel else "secondary"):
                st.session_state.selected_cloud = cloud_key
                st.rerun()

    cloud = st.session_state.selected_cloud
    st.caption(f"**{DEPLOY_OPTIONS[cloud]['label']}** — {DEPLOY_OPTIONS[cloud]['note']}")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Two-column layout: form (left) | agents (right) ───────────────────────
    col_form, col_agents = st.columns([3, 2])

    with col_form:
        st.markdown('<div class="section-hdr">📋 Project Setup</div>', unsafe_allow_html=True)

        # Detect existing projects so users can resume from a middle agent easily
        _outputs_root = Path(settings.outputs_dir)
        _existing_projects = sorted([
            d.name for d in _outputs_root.iterdir()
            if d.is_dir() and not d.name.startswith(".") and d.name != "uploads"
        ]) if _outputs_root.exists() else []

        if _existing_projects:
            _proj_opts = ["— type a new name —"] + _existing_projects
            _proj_sel = st.selectbox(
                "Resume existing project or start new",
                _proj_opts,
                help="Select an existing project to resume from a middle agent, or choose 'type a new name' to start fresh",
            )
            if _proj_sel == "— type a new name —":
                project_name = st.text_input("New Project Name", placeholder="e.g. Customer Portal v2")
            else:
                project_name = _proj_sel
                st.caption(f"Resuming **{project_name}** — outputs will be added to the existing folder.")
        else:
            project_name = st.text_input(
                "Project Name",
                placeholder="e.g. Customer Portal v2, Payment API",
            )

        uploaded_files = st.file_uploader(
            "Requirements Files",
            accept_multiple_files=True,
            type=["pdf", "docx", "txt", "md", "mp4", "mov", "mp3", "wav", "m4a"],
            help="Upload any combination: video, audio, PDFs, Word docs, SOPs, plain text",
        )

        st.markdown('<div class="section-hdr" style="margin-top:16px;">⚙️ Run Options</div>', unsafe_allow_html=True)
        col_start, col_dry = st.columns([3, 2])
        with col_start:
            start_idx = st.selectbox(
                "Start from Agent",
                range(TOTAL_AGENTS),
                format_func=lambda i: f"{i+1}. {AGENT_META[i][1]}",
                help="Resume from a specific agent",
            )
        with col_dry:
            st.markdown("<br>", unsafe_allow_html=True)
            dry_run = st.checkbox("🧪 Dry-run mode", value=False, help="Skip all Claude API calls (for testing pipeline wiring)")

        st.markdown("**⏭ Skip Optional Agents** *(saves API tokens)*")
        skip_cols = st.columns(3)
        _skippable = [
            ("agent_10_monitoring", "📊 Monitoring"),
            ("agent_11_support",    "Support"),
            ("agent_12_frontend",   "Frontend UI"),
        ]
        skip_agent_ids = []
        for i, (aid, label) in enumerate(_skippable):
            with skip_cols[i]:
                if st.checkbox(label, value=False, key=f"skip_{aid}",
                               help=f"Skip the {label.split(' ',1)[-1]} agent to save API tokens"):
                    skip_agent_ids.append(aid)
        if skip_agent_ids:
            st.caption(f"Skipping {len(skip_agent_ids)} agent(s) — saves ~{len(skip_agent_ids)*2} Claude calls")

        st.markdown("<br>", unsafe_allow_html=True)
        col_run, col_stop = st.columns([5, 1])
        with col_run:
            run_btn = st.button(
                "🚀 Launch Pipeline",
                type="primary",
                use_container_width=True,
                disabled=st.session_state.running,
            )
        with col_stop:
            if st.button("⏹", use_container_width=True, disabled=not st.session_state.running,
                         help="Stop after current agent"):
                st.session_state.running = False
                st.warning("Stop requested — halting after current agent.")

        if run_btn:
            if not project_name:
                st.error("Enter a project name.")
            elif not uploaded_files and not dry_run:
                st.error("Upload at least one requirements file, or enable dry-run mode.")
            else:
                run_id    = str(uuid.uuid4())
                upload_dir = Path(settings.outputs_dir) / "uploads" / run_id
                upload_dir.mkdir(parents=True, exist_ok=True)

                saved_paths = []
                for uf in uploaded_files:
                    dest = upload_dir / uf.name
                    dest.write_bytes(uf.read())
                    saved_paths.append(str(dest))

                new_state = PipelineState(
                    run_id=run_id,
                    project_name=project_name,
                    cloud_provider=cloud,
                    input_files=saved_paths,
                )
                st.session_state.pipeline_state      = new_state
                st.session_state.run_logs                    = []
                st.session_state.running                     = True
                st.session_state.dry_run_done                = False
                st.session_state.agent_substeps              = {}
                st.session_state.agent_start_times           = {}
                st.session_state.agent_durations             = {}
                st.session_state.pipeline_start_time         = time.time()
                st.session_state["_start_idx"]               = start_idx
                st.session_state["_dry_run"]                 = dry_run
                st.session_state["_skip_agents"]             = skip_agent_ids
                st.session_state["_pipeline_thread_started"] = False

                st.success(
                    f"✔ Pipeline queued  ·  "
                    f"Target: **{DEPLOY_OPTIONS[cloud]['label']}**  ·  "
                    f"Run: `{run_id[:12]}…`"
                )
                st.info("Switch to **📊 Live Status** to watch the pipeline run.")

    with col_agents:
        st.markdown('<div class="section-hdr">🤖 12 AI Agents</div>', unsafe_allow_html=True)
        for i, (icon, name, desc, color, _) in enumerate(AGENT_META):
            # Haiku agents (cheap/fast): Intake(0), Docs(6), QA(7), Review(8), Monitoring(10), Support(11), Packaging(12)
            tier = "H" if i in {0, 6, 7, 8, 10, 11, 12} else "S"
            tier_color = "#06b6d4" if tier == "H" else "#6366f1"
            tier_title = "Haiku (fast)" if tier == "H" else "Sonnet (powerful)"
            st.markdown(
                f'<div class="agent-list-item" style="border-left-color:{color};">'
                f'<div style="display:flex;align-items:center;justify-content:space-between;">'
                f'<div class="agent-list-title">{icon} {i+1:02d}. {name}</div>'
                f'<span title="{tier_title}" style="font-size:9px;font-weight:800;padding:1px 6px;'
                f'border-radius:10px;background:{tier_color}22;color:{tier_color};">{tier}</span>'
                f'</div>'
                f'<div class="agent-list-desc">{desc}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        st.markdown('<div class="section-hdr" style="margin-top:14px;">💡 What can it build?</div>', unsafe_allow_html=True)
        build_items = ["REST APIs & backends", "SaaS platforms", "Data pipelines",
                       "Admin dashboards", "Microservices", "E-commerce", "Healthcare / fintech"]
        st.markdown(
            '<div style="display:flex;flex-direction:column;gap:4px;">'
            + "".join(
                f'<div style="font-size:12px;padding:4px 10px;background:#f8fafc;'
                f'border-radius:6px;border-left:2px solid #6366f1;color:#334155;">{item}</div>'
                for item in build_items
            )
            + "</div>",
            unsafe_allow_html=True,
        )


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Live Status
# ══════════════════════════════════════════════════════════════════════════════

elif page == "📊 Live Status":

    state = st.session_state.get("pipeline_state")
    if not state:
        st.markdown("""
        <div style="text-align:center;padding:60px 20px;">
          <div style="font-size:56px;margin-bottom:16px;">🚀</div>
          <div style="font-size:22px;font-weight:800;color:#1e1b4b;margin-bottom:8px;">No Pipeline Running</div>
          <div style="font-size:14px;color:#64748b;">Go to <strong>🏠 New Run</strong> to start one.</div>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    results     = state.agent_results or []
    done        = sum(1 for r in results if r.status == AgentStatus.COMPLETED)
    failed      = sum(1 for r in results if r.status == AgentStatus.FAILED)
    skipped_ct  = sum(1 for r in results if r.status == AgentStatus.SKIPPED)
    running_now = 1 if state.current_agent else 0
    remaining   = TOTAL_AGENTS - done - failed - skipped_ct - running_now

    if st.session_state.pipeline_start_time:
        elapsed       = time.time() - st.session_state.pipeline_start_time
        elapsed_str   = fmt_duration(elapsed)
        avg_per_agent = elapsed / done if done > 0 else 0
        eta_secs      = avg_per_agent * max(remaining, 0)
        eta_str       = fmt_duration(eta_secs) if done > 0 and remaining > 0 else "—"
    else:
        elapsed_str, eta_str = "—", "—"

    cloud_info = DEPLOY_OPTIONS.get(state.cloud_provider, {})

    # ── Page header ────────────────────────────────────────────────────────────
    st.markdown(
        f'<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px;">'
        f'<div>'
        f'<h2 style="margin:0;font-size:22px;font-weight:900;color:#1e1b4b;">📊 Live Pipeline</h2>'
        f'<div style="font-size:12px;color:#64748b;margin-top:2px;">'
        f'<strong style="color:#334155">{state.project_name}</strong>'
        f' &nbsp;·&nbsp; {cloud_info.get("label","—")}'
        f' &nbsp;·&nbsp; <code style="color:#94a3b8">{state.run_id[:14]}…</code>'
        f'</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Stat cards ─────────────────────────────────────────────────────────────
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    _stat_cards = [
        (c1, done,        "Completed",  "#10b981", "✅"),
        (c2, running_now, "Running",    "#6366f1", "⚡"),
        (c3, remaining,   "Remaining",  "#64748b", "⏳"),
        (c4, failed,      "Failed",     "#ef4444", "❌"),
        (c5, skipped_ct,  "Skipped",    "#94a3b8", "⏭"),
        (c6, elapsed_str, "Elapsed",    "#06b6d4", "⏱"),
    ]
    for col, val, lbl, color, icon in _stat_cards:
        col.markdown(
            f'<div class="stat-card" style="--card-color:{color};">'
            f'<div class="stat-val" style="color:{color};">{val}</div>'
            f'<div class="stat-lbl">{lbl}</div>'
            f'{"<div class=stat-sub>ETA " + eta_str + "</div>" if lbl == "Elapsed" and eta_str != "—" else ""}'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ── ETA + cost row ─────────────────────────────────────────────────────────
    try:
        from utils.claude_client import ClaudeClient
        usage = ClaudeClient.get().usage_summary()
        cost_html = (
            f'<span class="cost-pill">💰 ~${usage["estimated_cost_usd"]:.4f} used'
            f' &nbsp;·&nbsp; cached saved ${usage["estimated_savings_usd"]:.4f}'
            f' &nbsp;·&nbsp; {usage["total_calls"]} API calls</span>'
        )
    except Exception:
        cost_html = ""
    st.markdown(cost_html, unsafe_allow_html=True)

    st.progress(done / TOTAL_AGENTS)

    # ── Horizontal pipeline timeline ────────────────────────────────────────────
    results_map = {r.agent_id: r for r in results}
    tl = ['<div class="pipeline-timeline">']
    for i, AgentCls in enumerate(AGENT_SEQUENCE):
        inst   = AgentCls()
        result = results_map.get(inst.agent_id)
        status = result.status if result else AgentStatus.PENDING
        icon   = AGENT_META[i][0]
        sname  = AGENT_META[i][1].split()[0]  # first word of name

        if   status == AgentStatus.COMPLETED: cls, content = "tl-done",    "✓"
        elif status == AgentStatus.RUNNING:   cls, content = "tl-running",  "⚡"
        elif status == AgentStatus.FAILED:    cls, content = "tl-failed",   "✗"
        elif status == AgentStatus.SKIPPED:   cls, content = "tl-skipped",  "⏭"
        else:                                  cls, content = "tl-pending",  str(i+1)

        tl.append(
            f'<div class="tl-node" title="{inst.name}">'
            f'<div class="tl-circle {cls}">{content}</div>'
            f'<div class="tl-label">{icon} {sname}</div>'
            f'</div>'
        )
        if i < TOTAL_AGENTS - 1:
            conn_cls = "tl-connector tl-connector-done" if status == AgentStatus.COMPLETED else "tl-connector"
            tl.append(f'<div class="{conn_cls}"></div>')
    tl.append('</div>')
    st.markdown("".join(tl), unsafe_allow_html=True)
    st.divider()

    col_agents, col_log = st.columns([3, 2])

    # ── Agent cards ────────────────────────────────────────────────────────────
    with col_agents:
        st.markdown('<div class="section-hdr">Agent Progress</div>', unsafe_allow_html=True)
        agent_cards_ph = st.empty()

        def render_agent_cards(current_state: PipelineState):
            rmap     = {r.agent_id: r for r in (current_state.agent_results or [])}
            substeps = st.session_state.get("agent_substeps", {})
            durs     = st.session_state.get("agent_durations", {})
            starts   = st.session_state.get("agent_start_times", {})
            parts    = []

            for i, AgentCls in enumerate(AGENT_SEQUENCE):
                inst   = AgentCls()
                result = rmap.get(inst.agent_id)
                status = result.status if result else AgentStatus.PENDING
                icon   = AGENT_META[i][0]
                color  = AGENT_META[i][3]
                emoji  = STATUS_EMOJI.get(status, "⏳")
                css    = f"agent-{status.value}"

                substep = substeps.get(inst.agent_id, "")
                summary = (result.summary or "") if result else ""
                error   = (result.error   or "") if result else ""

                if status == AgentStatus.RUNNING and substep:
                    sub = f'<div class="agent-step">⚡ {substep}</div>'
                elif status == AgentStatus.COMPLETED and summary:
                    t = summary[:80] + "…" if len(summary) > 80 else summary
                    sub = f'<div class="agent-summary">✔ {t}</div>'
                elif status == AgentStatus.FAILED and error:
                    t = error[:80] + "…" if len(error) > 80 else error
                    sub = f'<div class="agent-summary" style="color:#dc2626;">✗ {t}</div>'
                elif status == AgentStatus.SKIPPED:
                    sub = f'<div class="agent-summary" style="color:#94a3b8;">⏭ Skipped by user</div>'
                else:
                    sub = f'<div class="agent-summary" style="color:#94a3b8;">{AGENT_META[i][2]}</div>'

                time_str = ""
                if status == AgentStatus.COMPLETED and inst.agent_id in durs:
                    time_str = fmt_duration(durs[inst.agent_id])
                elif status == AgentStatus.RUNNING and inst.agent_id in starts:
                    running_for = time.time() - starts[inst.agent_id]
                    time_str = fmt_duration(running_for) + "…"

                # Model tier indicator
                try:
                    from agents.base_agent import BaseAgent as _BA
                    tier = getattr(inst, "model_tier", "sonnet")
                    tier_badge = f'<span style="font-size:8px;color:{"#10b981" if tier=="haiku" else "#6366f1"};font-weight:700;margin-right:4px;">{"H" if tier=="haiku" else "S"}</span>'
                except Exception:
                    tier_badge = ""

                badge_cls = f"agent-badge badge-{status.value}"
                parts.append(
                    f'<div class="agent-card {css}">'
                    f'  <div class="agent-icon">{icon}</div>'
                    f'  <div class="agent-body">'
                    f'    <div class="agent-title">{tier_badge}{i+1:02d}. {inst.name}</div>'
                    f'    {sub}'
                    f'  </div>'
                    f'  {"<div class=agent-time>" + time_str + "</div>" if time_str else ""}'
                    f'  <div class="{badge_cls}">{emoji} {status.value.upper()}</div>'
                    f'</div>'
                )
            agent_cards_ph.markdown("\n".join(parts), unsafe_allow_html=True)

        render_agent_cards(state)

    # ── Live log ───────────────────────────────────────────────────────────────
    with col_log:
        st.subheader("Live Log")
        log_filter = st.radio(
            "Filter",
            ["All", "Steps", "Errors", "Success"],
            horizontal=True,
            label_visibility="collapsed",
            key="log_filter_radio",
        )
        log_ph = st.empty()

        def render_log(logs: list[str]):
            lines = []
            for entry in logs[-80:]:
                if "✖" in entry or "FAILED" in entry or "ERROR" in entry or "error" in entry.lower():
                    cls = "log-error"
                    if log_filter not in ("All", "Errors"):
                        continue
                elif "✔" in entry or "complete" in entry.lower() or "SUCCESS" in entry:
                    cls = "log-success"
                    if log_filter not in ("All", "Success"):
                        continue
                elif "⚠" in entry or "WARNING" in entry or "Retrying" in entry:
                    cls = "log-warning"
                    if log_filter not in ("All",):
                        continue
                elif re.search(r"\(\d+/\d+\)", entry):
                    cls = "log-step"
                    if log_filter not in ("All", "Steps"):
                        continue
                else:
                    cls = "log-info"
                    if log_filter not in ("All",):
                        continue

                # Extract timestamp if present
                ts_match = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s*\|.*?\|\s*(.*)", entry)
                if ts_match:
                    ts_part  = ts_match.group(1)[11:]  # HH:MM:SS
                    msg_part = ts_match.group(2)
                else:
                    ts_part  = ""
                    msg_part = entry

                safe = msg_part.replace("<", "&lt;").replace(">", "&gt;")
                ts_html = f'<span class="log-time">{ts_part}</span>' if ts_part else ""
                lines.append(f'<div class="{cls}">{ts_html}{safe}</div>')

            log_ph.markdown(
                f'<div class="log-box">{"".join(lines) or "<div class=log-info>Waiting for events…</div>"}</div>',
                unsafe_allow_html=True,
            )

        render_log(st.session_state.run_logs)

    # ── Pipeline execution ─────────────────────────────────────────────────────
    if st.session_state.running and not st.session_state.dry_run_done:
        start_idx   = st.session_state.get("_start_idx", 0)
        dry_run     = st.session_state.get("_dry_run", False)
        skip_agents = st.session_state.get("_skip_agents", [])

        queue = event_bus.subscribe(state.run_id)

        # Run the async pipeline in a background thread with its own event loop.
        # Guard against re-launching on Streamlit reruns.
        if not st.session_state.get("_pipeline_thread_started"):
            st.session_state["_pipeline_thread_started"] = True

            _cancel = threading.Event()
            st.session_state["_cancel_event"] = _cancel

            def _run_pipeline():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                # Create asyncio.Event bound to this loop for the orchestrator
                async_cancel = asyncio.Event()
                orch = PipelineOrchestrator(cancel_event=async_cancel)

                # Forward threading cancel → asyncio cancel
                def _watch_cancel():
                    while not async_cancel.is_set():
                        if _cancel.wait(timeout=0.5):
                            loop.call_soon_threadsafe(async_cancel.set)
                            break
                threading.Thread(target=_watch_cancel, daemon=True).start()

                try:
                    loop.run_until_complete(
                        orch.run(state, start_from=start_idx, dry_run=dry_run,
                                 skip_agents=skip_agents)
                    )
                finally:
                    event_bus.send_done(state.run_id)
                    loop.close()

            threading.Thread(target=_run_pipeline, daemon=True).start()

        while True:
            try:
                event = queue.get_nowait()
            except stdlib_queue.Empty:
                time.sleep(0.35)
                st.rerun()
                break

            etype    = event.get("type", "")
            agent_id = event.get("agent_id", "")

            if etype == "log":
                msg = event.get("message", "")
                st.session_state.run_logs.append(msg)

                m = re.match(r"\[([^\]]+)\]\s+(.+)", msg)
                if m:
                    st.session_state.agent_substeps[m.group(1)] = m.group(2)

                render_log(st.session_state.run_logs)

            elif etype == "agent_started":
                st.session_state.agent_substeps[agent_id]    = "Starting…"
                st.session_state.agent_start_times[agent_id] = time.time()
                if not st.session_state.pipeline_start_time:
                    st.session_state.pipeline_start_time = time.time()

                current = PipelineStateManager.load_run(state.run_id) or state
                st.session_state.pipeline_state = current
                render_agent_cards(current)

            elif etype in ("agent_completed", "agent_failed"):
                start_t = st.session_state.agent_start_times.get(agent_id)
                if start_t:
                    st.session_state.agent_durations[agent_id] = time.time() - start_t
                st.session_state.agent_substeps.pop(agent_id, None)

                current = PipelineStateManager.load_run(state.run_id) or state
                st.session_state.pipeline_state = current
                render_agent_cards(current)

            elif etype in ("pipeline_completed", "pipeline_cancelled", "__done__"):
                st.session_state.running                     = False
                st.session_state.dry_run_done                = True
                st.session_state["_pipeline_thread_started"] = False
                event_bus.unsubscribe(state.run_id, queue)

                final = PipelineStateManager.load_run(state.run_id) or state
                st.session_state.pipeline_state = final
                render_agent_cards(final)
                st.balloons()
                st.success("🎉 Pipeline complete! Go to **📁 Outputs** to browse all generated files.")
                st.rerun()
                break

            if not st.session_state.running:
                cancel_ev = st.session_state.get("_cancel_event")
                if cancel_ev:
                    cancel_ev.set()
                event_bus.unsubscribe(state.run_id, queue)
                st.session_state["_pipeline_thread_started"] = False
                break


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Outputs
# ══════════════════════════════════════════════════════════════════════════════

elif page == "📁 Outputs":
    st.title("📁 Generated Outputs")

    base_outputs = Path(settings.outputs_dir)
    if not base_outputs.exists():
        st.info("No outputs yet — run the pipeline first.")
        st.stop()

    # ── Project selector ───────────────────────────────────────────────────────
    # Each project creates its own subfolder: outputs/{project_name}/
    # Detect project folders by looking for any folder that contains at least
    # one of the known category subdirectories.
    KNOWN_SUBDIRS = set(OUTPUT_CATEGORIES.values())

    def _is_project_folder(p: Path) -> bool:
        if not p.is_dir():
            return False
        children = {c.name for c in p.iterdir() if c.is_dir()}
        return bool(children & KNOWN_SUBDIRS)

    project_folders = sorted(
        [d for d in base_outputs.iterdir() if _is_project_folder(d)],
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )

    # Also check legacy flat layout (outputs/requirements/ etc. at root)
    has_legacy = any((base_outputs / s).exists() for s in KNOWN_SUBDIRS)
    if has_legacy:
        project_folders.append(base_outputs)   # treat root as "legacy"

    if not project_folders:
        st.info("No output files yet — run the pipeline first.")
        st.stop()

    # Build display names
    def _project_display(p: Path) -> str:
        if p == base_outputs:
            return "📂 Legacy (root outputs)"
        all_files = list(p.rglob("*"))
        n = sum(1 for f in all_files if f.is_file() and f.name != ".gitkeep")
        sz = sum(f.stat().st_size for f in all_files if f.is_file() and f.name != ".gitkeep")
        return f"📁 {p.name}  ({n} files · {human_size(sz)})"

    proj_display_map = {_project_display(p): p for p in project_folders}

    # Restore selected project from session (reset on new run)
    active_project_state = st.session_state.get("pipeline_state")
    if active_project_state and "selected_project_folder" not in st.session_state:
        # Auto-select current run's project
        import re as _re
        safe = _re.sub(r"[^\w\- ]", "", active_project_state.project_name).strip().replace(" ", "_").lower()
        candidate = base_outputs / safe
        if candidate in project_folders:
            st.session_state["selected_project_folder"] = str(candidate)

    col_sel, col_del = st.columns([5, 1])
    with col_sel:
        sel_display = st.selectbox(
            "Project",
            list(proj_display_map.keys()),
            index=0,
            key="project_folder_select",
        )
    outputs_root: Path = proj_display_map[sel_display]
    proj_name = outputs_root.name if outputs_root != base_outputs else "sdlc_outputs"

    with col_del:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🗑️ Delete", use_container_width=True, type="secondary",
                     help="Permanently delete this project's output files"):
            st.session_state["_confirm_delete_project"] = proj_name

    # ── Delete confirmation ────────────────────────────────────────────────────
    if st.session_state.get("_confirm_delete_project") == proj_name:
        st.warning(f"⚠️ This will permanently delete **all output files** for project `{proj_name}`. This cannot be undone.")
        col_yes, col_no, _ = st.columns([1, 1, 4])
        with col_yes:
            if st.button("Yes, delete", type="primary", use_container_width=True):
                import shutil
                try:
                    if outputs_root == base_outputs:
                        # Legacy: only delete known category subfolders
                        for s in KNOWN_SUBDIRS:
                            p = base_outputs / s
                            if p.exists():
                                shutil.rmtree(p)
                                p.mkdir(parents=True, exist_ok=True)
                                (p / ".gitkeep").touch()
                    else:
                        shutil.rmtree(outputs_root)
                    st.session_state.pop("_confirm_delete_project", None)
                    st.success(f"✅ Deleted project `{proj_name}`")
                    st.rerun()
                except Exception as e:
                    st.error(f"Delete failed: {e}")
        with col_no:
            if st.button("Cancel", use_container_width=True):
                st.session_state.pop("_confirm_delete_project", None)
                st.rerun()

    st.divider()

    # ── Gather files per category ──────────────────────────────────────────────
    all_cats: dict[str, list[Path]] = {}
    all_files_flat: list[Path] = []
    total_size = 0

    for label, subdir in OUTPUT_CATEGORIES.items():
        folder = outputs_root / subdir
        if not folder.exists():
            continue
        files = sorted(f for f in folder.rglob("*") if f.is_file() and f.name != ".gitkeep")
        if files:
            all_cats[label] = files
            all_files_flat.extend(files)
            total_size += sum(f.stat().st_size for f in files)

    if not all_cats:
        st.info(f"No output files found in project **{proj_name}** yet.")
        st.stop()

    # ── Header stats + ZIP download ────────────────────────────────────────────
    hcols = st.columns([1] * len(all_cats) + [2])
    for col, (label, files) in zip(hcols, all_cats.items()):
        icon_c = label.split()[0]
        name_c = " ".join(label.split()[1:])
        sz     = sum(f.stat().st_size for f in files)
        col.markdown(
            f'<div class="metric-box">'
            f'<div style="font-size:18px">{icon_c}</div>'
            f'<div class="metric-val" style="font-size:22px">{len(files)}</div>'
            f'<div class="metric-lbl">{name_c}</div>'
            f'<div class="metric-sub">{human_size(sz)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    with hcols[-1]:
        st.markdown("<br>", unsafe_allow_html=True)
        zip_bytes = create_zip_bytes(all_files_flat, outputs_root)
        st.download_button(
            f"📦 Download {proj_name} as ZIP",
            data=zip_bytes,
            file_name=f"{proj_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.zip",
            mime="application/zip",
            use_container_width=True,
        )

    st.markdown(
        f"**Project:** `{proj_name}` &nbsp;·&nbsp; "
        f"**{len(all_files_flat)} files** &nbsp;·&nbsp; "
        f"**{human_size(total_size)} total**",
        unsafe_allow_html=True,
    )
    st.divider()

    # ── Two-column layout: file browser | file viewer ──────────────────────────
    col_tree, col_viewer = st.columns([1, 2])

    with col_tree:
        st.markdown('<div class="section-hdr">📂 File Browser</div>', unsafe_allow_html=True)
        search = st.text_input("🔍", placeholder="Filter files…", label_visibility="collapsed")

        for label, files in all_cats.items():
            filtered = [f for f in files if search.lower() in f.name.lower()] if search else files
            if not filtered:
                continue
            cat_size  = sum(f.stat().st_size for f in filtered)
            # Use plain ASCII name in expander title — emojis break in st.expander() on some platforms
            cat_name  = " ".join(label.split()[1:])   # e.g. "Requirements", "Architecture"
            with st.expander(
                f"{cat_name}  ({len(filtered)} · {human_size(cat_size)})",
                expanded=not search and cat_name in ["Code", "Architecture"],
            ):
                for f in filtered[:60]:
                    rel    = str(f.relative_to(outputs_root))
                    icon_f = file_icon(f)
                    is_sel = st.session_state.selected_file == str(f)
                    try:
                        sz_str = human_size(f.stat().st_size)
                    except Exception:
                        sz_str = ""

                    if st.button(
                        f"{icon_f} {'▶ ' if is_sel else ''}{f.name}",
                        key=f"file_{f}",
                        use_container_width=True,
                        help=f"{rel}  ·  {sz_str}",
                        type="primary" if is_sel else "secondary",
                    ):
                        st.session_state.selected_file = str(f)
                        st.rerun()

    with col_viewer:
        selected = st.session_state.get("selected_file")
        if not selected:
            st.markdown("""
            <div style="display:flex;flex-direction:column;align-items:center;
                        justify-content:center;height:420px;color:#bbb;">
              <div style="font-size:52px">📄</div>
              <div style="font-size:15px;margin-top:12px;color:#888;">Select a file to view</div>
              <div style="font-size:12px;margin-top:6px;color:#bbb;">Click any file in the browser on the left</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            fp = Path(selected)
            if not fp.exists():
                st.warning("File not found.")
                st.session_state.selected_file = None
            else:
                try:
                    rel = str(fp.relative_to(outputs_root))
                except ValueError:
                    rel = fp.name
                ext  = fp.suffix.lstrip(".")
                lang = LANG_MAP.get(ext, "text")
                icon_f = file_icon(fp)

                st.markdown(f"### {icon_f} `{fp.name}`")
                st.caption(f"📁 `{proj_name}/{rel}`")

                try:
                    stat    = fp.stat()
                    mtime   = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
                    content = fp.read_text(errors="ignore")
                    lines_n = content.count("\n") + 1
                    info_row, dl_row = st.columns([3, 1])
                    info_row.caption(
                        f"Size: **{human_size(stat.st_size)}** · "
                        f"Lines: **{lines_n}** · "
                        f"Modified: {mtime} · "
                        f"Type: `.{ext}`"
                    )
                    dl_row.download_button(
                        "⬇ Download",
                        data=content,
                        file_name=fp.name,
                        mime="text/plain",
                        use_container_width=True,
                    )
                except Exception as e:
                    st.error(f"Cannot read file: {e}")
                    st.stop()

                if ext == "md":
                    view_mode = st.radio(
                        "View",
                        ["📖 Rendered", "🔤 Raw"],
                        horizontal=True,
                        label_visibility="collapsed",
                    )
                    if view_mode == "📖 Rendered":
                        st.markdown(content)
                    else:
                        st.code(content, language="markdown")
                elif len(content) > 60_000:
                    st.warning(f"Large file — showing first 60 KB")
                    st.code(content[:60_000], language=lang)
                else:
                    st.code(content, language=lang)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Deploy
# ══════════════════════════════════════════════════════════════════════════════

elif page == "🚢 Deploy":
    import queue as _q
    import threading as _th
    from deployer.executor import check_prerequisites, deploy as _do_deploy, push_to_github, get_project_code_path
    from deployer.base import DeployError
    from config.credentials import load_credentials, save_credentials, AllCredentials

    st.title("🚢 Deploy")
    st.caption("Authenticate once, deploy your generated app to any target from here.")

    # ── Project selector ───────────────────────────────────────────────────────
    base_outputs = Path(settings.outputs_dir)
    project_dirs = sorted(
        [d for d in base_outputs.iterdir() if d.is_dir()] if base_outputs.exists() else [],
        key=lambda d: d.stat().st_mtime, reverse=True,
    )
    proj_names = [d.name for d in project_dirs]

    active = st.session_state.get("pipeline_state")
    default_idx = 0
    if active and active.project_name:
        import re as _re
        safe = _re.sub(r"[^\w\- ]", "", active.project_name).strip().replace(" ", "_").lower()
        if safe in proj_names:
            default_idx = proj_names.index(safe)

    if not proj_names:
        st.info("No projects found — run the pipeline first.")
        st.stop()

    col_proj, col_prov = st.columns(2)
    with col_proj:
        selected_proj = st.selectbox("Project", proj_names, index=default_idx)
    with col_prov:
        cloud_display = {
            "🖥 localhost (Docker Compose)": "localhost",
            "☁️ GCP — Cloud Run":           "gcp",
            "☁️ AWS — ECS Fargate":         "aws",
            "☁️ Azure — Container Apps":    "azure",
        }
        cloud_label = st.selectbox("Deployment Target", list(cloud_display.keys()))
        deploy_to = cloud_display[cloud_label]

    st.divider()

    # ── Prerequisite checker ───────────────────────────────────────────────────
    st.subheader("🔍 Prerequisites")
    prereqs = check_prerequisites(deploy_to)
    all_ok  = all(prereqs.values())

    pcols = st.columns(len(prereqs))
    for col, (tool, ok) in zip(pcols, prereqs.items()):
        col.markdown(
            f'<div class="metric-box">'
            f'<div style="font-size:20px">{"✅" if ok else "❌"}</div>'
            f'<div class="metric-lbl">{tool}</div>'
            f'<div style="font-size:10px;color:{"#2e7d32" if ok else "#c62828"};">'
            f'{"found" if ok else "not found"}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    if not all_ok:
        missing = [t for t, ok in prereqs.items() if not ok]
        st.warning(f"Missing tools: **{', '.join(missing)}**. Install them and restart.")

    st.divider()

    # ── Credentials check ──────────────────────────────────────────────────────
    st.subheader("🔑 Credentials")
    creds = load_credentials()
    cred_map = {
        "localhost": None,
        "gcp":       creds.gcp,
        "aws":       creds.aws,
        "azure":     creds.azure,
    }
    cred_obj = cred_map[deploy_to]
    creds_ok = True

    if deploy_to == "localhost":
        st.success("No credentials needed for localhost deployment.")
    elif deploy_to == "gcp":
        creds_ok = bool(creds.gcp.project_id and creds.gcp.service_account_json)
        if creds_ok:
            st.success(f"✅ GCP: project `{creds.gcp.project_id}` · region `{creds.gcp.region}`")
        else:
            st.error("❌ GCP credentials missing — set them in **⚙️ Settings → Credentials**.")
    elif deploy_to == "aws":
        creds_ok = bool(creds.aws.access_key_id and creds.aws.secret_access_key and creds.aws.account_id)
        if creds_ok:
            st.success(f"✅ AWS: region `{creds.aws.region}` · account `{creds.aws.account_id[-4:]}…`")
        else:
            st.error("❌ AWS credentials missing — set them in **⚙️ Settings → Credentials**.")
    elif deploy_to == "azure":
        creds_ok = bool(creds.azure.tenant_id and creds.azure.client_id and creds.azure.client_secret and creds.azure.subscription_id)
        if creds_ok:
            st.success(f"✅ Azure: subscription `{creds.azure.subscription_id[:8]}…` · region `{creds.azure.location}`")
        else:
            st.error("❌ Azure credentials missing — set them in **⚙️ Settings → Credentials**.")

    github_ok = bool(creds.github.token and creds.github.repo_url)
    if github_ok:
        st.success(f"✅ GitHub: `{creds.github.repo_url}`")
    else:
        st.info("ℹ️ GitHub credentials not set — push to GitHub will be unavailable.")

    # ── Terraform toggle ───────────────────────────────────────────────────────
    use_tf = False
    if deploy_to != "localhost":
        use_tf = st.checkbox(
            "Use Terraform (full infra) instead of direct CLI deploy",
            value=False,
            help="Terraform creates the full cloud infrastructure (DB, cache, networking). Direct deploy just runs the container.",
        )

    st.divider()

    # ── Deploy buttons ─────────────────────────────────────────────────────────
    col_dep, col_gh, col_stop = st.columns([3, 3, 1])

    deploy_running   = st.session_state.get("deploy_running", False)
    with col_dep:
        deploy_btn = st.button(
            f"🚀 Deploy to {cloud_label.split('—')[0].strip()}",
            type="primary",
            use_container_width=True,
            disabled=deploy_running or not all_ok or not creds_ok,
        )
    with col_gh:
        github_btn = st.button(
            "🐙 Push to GitHub",
            use_container_width=True,
            disabled=deploy_running or not github_ok,
        )
    with col_stop:
        if st.button("⏹", use_container_width=True, disabled=not deploy_running):
            st.session_state["deploy_running"] = False
            st.warning("Stop requested.")

    # ── Live deploy log ────────────────────────────────────────────────────────
    st.subheader("📋 Deploy Log")
    log_ph = st.empty()

    if "deploy_logs" not in st.session_state:
        st.session_state["deploy_logs"] = []

    def _render_deploy_log():
        lines = []
        for entry in st.session_state["deploy_logs"][-120:]:
            if entry.startswith("✅") or "complete" in entry.lower():
                cls = "log-success"
            elif entry.startswith("❌") or "error" in entry.lower() or "failed" in entry.lower():
                cls = "log-error"
            elif entry.startswith("$"):
                cls = "log-step"
            elif entry.startswith("⚠"):
                cls = "log-warning"
            else:
                cls = "log-info"
            safe = entry.replace("<", "&lt;").replace(">", "&gt;")
            lines.append(f'<div class="{cls}">{safe}</div>')
        log_ph.markdown(
            f'<div class="log-box">{"".join(lines) or "<div class=log-info>Waiting…</div>"}</div>',
            unsafe_allow_html=True,
        )

    _render_deploy_log()

    # ── Execute deploy in background thread ────────────────────────────────────
    def _start_deploy(action: str):
        st.session_state["deploy_logs"] = []
        st.session_state["deploy_running"] = True
        _log_q: _q.Queue = _q.Queue()

        def _log_cb(msg: str):
            _log_q.put(msg)

        def _worker():
            try:
                if action == "deploy":
                    url = _do_deploy(selected_proj, deploy_to, log_cb=_log_cb, use_terraform=use_tf)
                    _log_q.put(f"✅ Deployment complete! → {url}")
                    st.session_state["deploy_url"] = url
                elif action == "github":
                    url = push_to_github(selected_proj, log_cb=_log_cb)
                    _log_q.put(f"✅ Pushed to GitHub! → {url}")
            except DeployError as e:
                _log_q.put(f"❌ Deploy failed: {e}")
            except Exception as e:
                _log_q.put(f"❌ Unexpected error: {e}")
            finally:
                _log_q.put("__DONE__")

        _th.Thread(target=_worker, daemon=True).start()

        while True:
            try:
                msg = _log_q.get(timeout=0.5)
            except _q.Empty:
                st.session_state["deploy_logs"].append("…")
                _render_deploy_log()
                time.sleep(0.3)
                st.rerun()
                break
            if msg == "__DONE__":
                st.session_state["deploy_running"] = False
                _render_deploy_log()
                st.rerun()
                break
            st.session_state["deploy_logs"].append(msg)
            _render_deploy_log()

    if deploy_btn:
        _start_deploy("deploy")
    elif github_btn:
        _start_deploy("github")

    # Show deployed URL if available
    if st.session_state.get("deploy_url"):
        st.success(f"🌐 **Live URL:** {st.session_state['deploy_url']}")
        st.link_button("Open App", st.session_state["deploy_url"])


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Analytics
# ══════════════════════════════════════════════════════════════════════════════

elif page == "📈 Analytics":
    st.title("📈 Analytics & Run History")

    runs = PipelineStateManager.list_runs()
    if not runs:
        st.info("No pipeline runs yet.")
        st.stop()

    # ── Summary metrics across ALL runs ────────────────────────────────────────
    total_runs = len(runs)
    all_states = []
    for run in runs:
        s = PipelineStateManager.load_run(run["run_id"])
        if s:
            all_states.append(s)

    total_agents_done  = sum(
        sum(1 for r in (s.agent_results or []) if r.status == AgentStatus.COMPLETED)
        for s in all_states
    )
    total_files_gen = 0
    outputs_root    = Path(settings.outputs_dir)
    if outputs_root.exists():
        total_files_gen = sum(1 for f in outputs_root.rglob("*") if f.is_file() and f.name != ".gitkeep")

    a1, a2, a3, a4 = st.columns(4)
    for col, val, lbl in [
        (a1, total_runs,        "Total Runs"),
        (a2, total_agents_done, "Agents Executed"),
        (a3, total_files_gen,   "Files Generated"),
        (a4, f"{total_runs * 11}", "Agent Invocations"),
    ]:
        col.markdown(
            f'<div class="metric-box"><div class="metric-val">{val}</div>'
            f'<div class="metric-lbl">{lbl}</div></div>',
            unsafe_allow_html=True,
        )

    st.divider()

    # ── Per-run table ──────────────────────────────────────────────────────────
    st.subheader("Run History")

    for state in all_states:
        results  = state.agent_results or []
        done_c   = sum(1 for r in results if r.status == AgentStatus.COMPLETED)
        fail_c   = sum(1 for r in results if r.status == AgentStatus.FAILED)
        cloud    = DEPLOY_OPTIONS.get(state.cloud_provider, {}).get("label", state.cloud_provider.upper())
        run_date = runs[[r["run_id"] for r in runs].index(state.run_id)].get("created_at", "")[:16]

        # Status color
        if done_c == TOTAL_AGENTS:
            status_badge = "✅ Complete"
            card_border  = "#43A047"
        elif fail_c > 0:
            status_badge = f"⚠️ {fail_c} Failed"
            card_border  = "#FFB300"
        else:
            status_badge = f"🔄 {done_c}/{TOTAL_AGENTS}"
            card_border  = "#2196F3"

        with st.expander(
            f"{state.project_name}  ·  {cloud}  ·  {run_date}  ·  {status_badge}",
            expanded=False,
        ):
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Completed", f"{done_c}/{TOTAL_AGENTS}")
            c2.metric("Failed",    fail_c)
            c3.metric("Target",    cloud.strip())
            c4.metric("Run ID",    state.run_id[:10] + "…")

            if done_c > 0:
                st.progress(done_c / TOTAL_AGENTS)

            # Agent-by-agent breakdown
            if results:
                st.markdown("**Agent Results:**")
                rows = []
                for r in results:
                    emoji = STATUS_EMOJI.get(r.status, "⏳")
                    rows.append(
                        f"{emoji} `{r.agent_id}` — "
                        + (r.summary[:80] + "…" if r.summary and len(r.summary) > 80 else (r.summary or r.status.value))
                    )
                for row in rows:
                    st.markdown(row)

            col_resume, col_gap = st.columns([2, 5])
            with col_resume:
                if st.button("▶ Resume this run", key=f"res_{state.run_id}"):
                    st.session_state.pipeline_state                  = state
                    st.session_state["_start_idx"]                   = PipelineStateManager.get_resume_index(state)
                    st.session_state["_dry_run"]                     = False
                    st.session_state.running                         = True
                    st.session_state.run_logs                        = []
                    st.session_state.agent_substeps                  = {}
                    st.session_state.agent_start_times               = {}
                    st.session_state.agent_durations                 = {}
                    st.session_state.pipeline_start_time             = time.time()
                    st.session_state["_pipeline_thread_started"]     = False
                    st.success("Resuming — switch to **📊 Live Status**")

    # ── File breakdown chart ────────────────────────────────────────────────────
    if outputs_root.exists():
        st.divider()
        st.subheader("Output Files by Category")

        chart_data: dict[str, int] = {}
        for label, subdir in OUTPUT_CATEGORIES.items():
            folder = outputs_root / subdir
            if folder.exists():
                n = sum(1 for f in folder.rglob("*") if f.is_file() and f.name != ".gitkeep")
                if n:
                    chart_data[" ".join(label.split()[1:])] = n

        if chart_data:
            import pandas as pd
            df = pd.DataFrame(
                {"Category": list(chart_data.keys()), "Files": list(chart_data.values())}
            ).sort_values("Files", ascending=False)
            st.bar_chart(df.set_index("Category"), height=250)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: Settings
# ══════════════════════════════════════════════════════════════════════════════

elif page == "⚙️ Settings":
    st.title("⚙️ Settings")
    st.info("Edit `.env` in the project root to change settings, then restart the app.")

    st.subheader("Current Configuration")
    c1, c2, c3 = st.columns(3)
    c1.metric("Model",       settings.anthropic_model)
    c1.metric("Environment", settings.app_env)
    c2.metric("Max Tokens",  settings.anthropic_max_tokens)
    c2.metric("Whisper",     settings.whisper_model)
    c3.metric("Outputs Dir", str(settings.outputs_dir).split("/")[-2] + "/" + str(settings.outputs_dir).split("/")[-1])
    c3.metric("DB",          settings.database_url.split(":///")[-1])

    st.divider()
    st.subheader("System Health")
    checks = [
        ("ANTHROPIC_API_KEY configured",  bool(settings.anthropic_api_key and settings.anthropic_api_key != "test")),
        ("Outputs directory exists",      Path(settings.outputs_dir).exists()),
        ("Database accessible",           True),
    ]
    for label, ok in checks:
        st.markdown(f"{'✅' if ok else '❌'} {label}")

    st.divider()

    # ── Credentials management ─────────────────────────────────────────────────
    st.subheader("🔑 Credentials")
    st.caption("Credentials are stored locally in `.credentials.json` (never committed to git).")

    from config.credentials import load_credentials, save_credentials, AllCredentials

    _creds = load_credentials()

    tab_gcp, tab_aws, tab_az, tab_gh = st.tabs(["☁️ GCP", "☁️ AWS", "☁️ Azure", "🐙 GitHub"])

    with tab_gcp:
        with st.form("gcp_creds_form"):
            st.markdown("**Google Cloud Platform — Cloud Run deployment**")
            gcp_proj   = st.text_input("Project ID",              value=_creds.gcp.project_id,          placeholder="my-gcp-project")
            gcp_region = st.text_input("Region",                  value=_creds.gcp.region,              placeholder="us-central1")
            gcp_ar     = st.text_input("Artifact Registry (host)",value=_creds.gcp.artifact_registry,   placeholder="us-central1-docker.pkg.dev/project/repo")
            gcp_sa     = st.text_area("Service Account JSON",     value=_creds.gcp.service_account_json,
                                      placeholder='{ "type": "service_account", "project_id": "...", ... }',
                                      height=200)
            if st.form_submit_button("💾 Save GCP Credentials", type="primary"):
                _creds.gcp.project_id           = gcp_proj.strip()
                _creds.gcp.region               = gcp_region.strip()
                _creds.gcp.artifact_registry    = gcp_ar.strip()
                _creds.gcp.service_account_json = gcp_sa.strip()
                save_credentials(_creds)
                st.success("✅ GCP credentials saved.")

    with tab_aws:
        with st.form("aws_creds_form"):
            st.markdown("**Amazon Web Services — ECS Fargate deployment**")
            aws_key    = st.text_input("Access Key ID",     value=_creds.aws.access_key_id,     type="password", placeholder="AKIA…")
            aws_secret = st.text_input("Secret Access Key", value=_creds.aws.secret_access_key, type="password", placeholder="wJalr…")
            aws_region = st.text_input("Region",            value=_creds.aws.region,             placeholder="us-east-1")
            aws_acct   = st.text_input("Account ID",        value=_creds.aws.account_id,         placeholder="123456789012")
            if st.form_submit_button("💾 Save AWS Credentials", type="primary"):
                _creds.aws.access_key_id     = aws_key.strip()
                _creds.aws.secret_access_key = aws_secret.strip()
                _creds.aws.region            = aws_region.strip()
                _creds.aws.account_id        = aws_acct.strip()
                save_credentials(_creds)
                st.success("✅ AWS credentials saved.")

    with tab_az:
        with st.form("azure_creds_form"):
            st.markdown("**Microsoft Azure — Container Apps deployment**")
            az_tenant  = st.text_input("Tenant ID",       value=_creds.azure.tenant_id,       type="password", placeholder="xxxxxxxx-xxxx-…")
            az_client  = st.text_input("Client ID",       value=_creds.azure.client_id,       placeholder="xxxxxxxx-xxxx-…")
            az_secret  = st.text_input("Client Secret",   value=_creds.azure.client_secret,   type="password", placeholder="your-client-secret")
            az_sub     = st.text_input("Subscription ID", value=_creds.azure.subscription_id, placeholder="xxxxxxxx-xxxx-…")
            az_rg      = st.text_input("Resource Group",  value=_creds.azure.resource_group,  placeholder="my-app-rg (auto-created if blank)")
            az_loc     = st.text_input("Location",        value=_creds.azure.location,        placeholder="eastus")
            if st.form_submit_button("💾 Save Azure Credentials", type="primary"):
                _creds.azure.tenant_id       = az_tenant.strip()
                _creds.azure.client_id       = az_client.strip()
                _creds.azure.client_secret   = az_secret.strip()
                _creds.azure.subscription_id = az_sub.strip()
                _creds.azure.resource_group  = az_rg.strip()
                _creds.azure.location        = az_loc.strip()
                save_credentials(_creds)
                st.success("✅ Azure credentials saved.")

    with tab_gh:
        with st.form("github_creds_form"):
            st.markdown("**GitHub — push generated code to a repo**")
            gh_token    = st.text_input("Personal Access Token", value=_creds.github.token,    type="password", placeholder="ghp_…")
            gh_username = st.text_input("Username",              value=_creds.github.username,  placeholder="your-github-username")
            gh_repo     = st.text_input("Repository URL",        value=_creds.github.repo_url,  placeholder="https://github.com/username/my-app")
            st.caption("Token needs `repo` scope. The repo can be empty — the pipeline will force-push.")
            if st.form_submit_button("💾 Save GitHub Credentials", type="primary"):
                _creds.github.token    = gh_token.strip()
                _creds.github.username = gh_username.strip()
                _creds.github.repo_url = gh_repo.strip()
                save_credentials(_creds)
                st.success("✅ GitHub credentials saved.")

    st.divider()
    st.subheader("Deployment Target Guide")
    st.markdown("""
| Target | What Gets Generated | Prerequisites |
|---|---|---|
| 🖥 **localhost** | `docker-compose.yml`, Makefile, startup scripts, `.env.example` | Docker Desktop |
| ☁️ **GCP** | Terraform (Cloud Run, Cloud SQL, Memorystore), K8s manifests, CI/CD | GCP project + `gcloud` CLI |
| ☁️ **AWS** | Terraform (ECS Fargate, RDS Aurora, ElastiCache), K8s manifests, CI/CD | AWS account + `aws` CLI |
| ☁️ **Azure** | Terraform (Container Apps, Azure DB, Redis Cache), K8s manifests, CI/CD | Azure subscription + `az` CLI |
""")

    st.divider()
    st.subheader("Output Directory Structure")
    st.code("""outputs/
├── requirements/   ← PRD, gap analysis JSON
├── architecture/   ← HLD/LLD docs, schema.sql, openapi.yaml
├── security/       ← threat model, security report
├── code/           ← production source code
├── tests/          ← unit, integration, E2E, BDD
├── docs/           ← README, API reference, runbooks
└── deployments/    ← Terraform, K8s, CI/CD, monitoring
""", language="text")
