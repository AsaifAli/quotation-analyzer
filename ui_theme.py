"""Premium visual system for QuoteSense.

Presentation-only. Business logic and model behavior remain in the existing app.
"""
from __future__ import annotations

import html
import streamlit as st


def apply_theme() -> None:
    """Apply a QuoteSense-specific system-aware visual theme."""
    try:
        streamlit_theme = (st.context.theme.type or "light").lower()
    except Exception:
        streamlit_theme = "light"

    if streamlit_theme == "dark":
        tokens = {
            "page": "#080c14",
            "surface": "#0f1420",
            "surface2": "#151c2b",
            "text": "#f4f7fb",
            "text2": "#d7deea",
            "muted": "#97a3b6",
            "border": "rgba(148,163,184,.18)",
            "accent": "#f59e0b",
            "accent2": "#f97316",
            "sidebar": "#0c121d",
            "field": "#111827",
            "success": "#34d399",
            "warning": "#fbbf24",
            "danger": "#fb7185",
        }
    else:
        tokens = {
            "page": "#f5f7fb",
            "surface": "#ffffff",
            "surface2": "#f1f4f8",
            "text": "#172033",
            "text2": "#334155",
            "muted": "#64748b",
            "border": "rgba(100,116,139,.18)",
            "accent": "#f59e0b",
            "accent2": "#f97316",
            "sidebar": "#f7f8fc",
            "field": "#ffffff",
            "success": "#059669",
            "warning": "#b45309",
            "danger": "#dc2626",
        }

    def e(value: str) -> str:
        return html.escape(value)

    css = f"""
<style>
:root {{
  --qs-page:{tokens['page']};
  --qs-surface:{tokens['surface']};
  --qs-surface-2:{tokens['surface2']};
  --qs-text:{tokens['text']};
  --qs-text-2:{tokens['text2']};
  --qs-muted:{tokens['muted']};
  --qs-border:{tokens['border']};
  --qs-accent:{tokens['accent']};
  --qs-accent-2:{tokens['accent2']};
  --qs-sidebar:{tokens['sidebar']};
  --qs-field:{tokens['field']};
  --qs-success:{tokens['success']};
  --qs-warning:{tokens['warning']};
  --qs-danger:{tokens['danger']};
}}

/* Live system theme. */
:root {{ color-scheme: light dark; }}
@media (prefers-color-scheme: light) {{
  :root, html {{
    color-scheme: light !important;
    --qs-page:#f5f7fb; --qs-surface:#ffffff; --qs-surface-2:#f1f4f8;
    --qs-text:#172033; --qs-text-2:#334155; --qs-muted:#64748b;
    --qs-border:rgba(100,116,139,.18); --qs-sidebar:#f7f8fc; --qs-field:#ffffff;
    --qs-success:#059669; --qs-warning:#b45309; --qs-danger:#dc2626;
  }}
}}
@media (prefers-color-scheme: dark) {{
  :root, html {{
    color-scheme: dark !important;
    --qs-page:#080c14; --qs-surface:#0f1420; --qs-surface-2:#151c2b;
    --qs-text:#f4f7fb; --qs-text-2:#d7deea; --qs-muted:#97a3b6;
    --qs-border:rgba(148,163,184,.18); --qs-sidebar:#0c121d; --qs-field:#111827;
    --qs-success:#34d399; --qs-warning:#fbbf24; --qs-danger:#fb7185;
  }}
}}

html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMainBlockContainer"] {{
  background:var(--qs-page)!important;
  color:var(--qs-text)!important;
}}
body {{ overflow-x:hidden!important; }}
.stApp, [data-testid="stAppViewContainer"] {{
  background:
    radial-gradient(820px 470px at 2% -8%, color-mix(in srgb,var(--qs-accent) 9%,transparent), transparent 62%),
    radial-gradient(740px 430px at 98% 0%, color-mix(in srgb,var(--qs-accent-2) 7%,transparent), transparent 58%),
    var(--qs-page)!important;
}}

#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], .stDeployButton, [data-testid="stAppDeployButton"] {{
  display:none!important;
}}
header[data-testid="stHeader"] {{ background:transparent!important; }}

[data-testid="stAppViewContainer"]>.main .block-container {{
  max-width:1500px!important;
  padding-top:1.05rem!important;
  padding-bottom:6.25rem!important;
  padding-left:clamp(1rem,3vw,3rem)!important;
  padding-right:clamp(1rem,3vw,3rem)!important;
}}

.stMarkdown, .stMarkdown p, .stMarkdown li, [data-testid="stCaptionContainer"], label,
[data-testid="stFileUploader"] small, input, textarea, [data-baseweb="select"] * {{
  color:var(--qs-text)!important;
}}
[data-testid="stCaptionContainer"], .stCaption {{ color:var(--qs-muted)!important; }}
h1,h2,h3,h4,h5,h6 {{ color:var(--qs-text)!important; }}

/* Sidebar */
section[data-testid="stSidebar"] {{
  background:linear-gradient(180deg, color-mix(in srgb,var(--qs-accent) 4%,transparent), transparent 22%), var(--qs-sidebar)!important;
  border-right:1px solid var(--qs-border)!important;
}}
section[data-testid="stSidebar"]>div {{ background:transparent!important; }}
section[data-testid="stSidebar"] * {{ color:var(--qs-text-2)!important; }}

/* Buttons */
.stButton>button, .stDownloadButton>button, [data-testid="stFormSubmitButton"] button {{
  min-height:40px!important;
  border-radius:11px!important;
  border:1px solid var(--qs-border)!important;
  background:var(--qs-surface)!important;
  color:var(--qs-text)!important;
  box-shadow:0 7px 20px rgba(15,23,42,.06)!important;
  font-weight:700!important;
  transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease!important;
}}
.stButton>button:hover, .stDownloadButton>button:hover, [data-testid="stFormSubmitButton"] button:hover {{
  transform:translateY(-1px);
  border-color:color-mix(in srgb,var(--qs-accent) 44%,var(--qs-border))!important;
  box-shadow:0 12px 28px color-mix(in srgb,var(--qs-accent) 10%,transparent)!important;
}}
.stButton>button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"] {{
  background:linear-gradient(135deg,var(--qs-accent),var(--qs-accent-2))!important;
  color:#fff!important;
  border-color:transparent!important;
}}

/* Inputs + selects */
input,textarea,[data-baseweb="select"]>div {{
  border-radius:11px!important;
  border:1px solid var(--qs-border)!important;
  background:var(--qs-field)!important;
  color:var(--qs-text)!important;
}}
textarea::placeholder,input::placeholder {{ color:var(--qs-muted)!important; opacity:1!important; }}
input:focus,textarea:focus,[data-baseweb="select"]>div:hover {{
  border-color:var(--qs-accent)!important;
  box-shadow:0 0 0 3px color-mix(in srgb,var(--qs-accent) 10%,transparent)!important;
}}
[data-baseweb="menu"] {{ background:var(--qs-surface)!important; border:1px solid var(--qs-border)!important; }}
[data-baseweb="menu"] li {{ color:var(--qs-text)!important; }}

/* Upload */
[data-testid="stFileUploaderDropzone"] {{
  border:1px dashed color-mix(in srgb,var(--qs-accent) 50%,var(--qs-border))!important;
  border-radius:16px!important;
  background:linear-gradient(180deg,color-mix(in srgb,var(--qs-accent) 5%,var(--qs-surface)),var(--qs-surface))!important;
  transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease!important;
}}
[data-testid="stFileUploaderDropzone"] * {{ color:var(--qs-text)!important; }}
[data-testid="stFileUploaderDropzone"] small {{ color:var(--qs-muted)!important; }}
[data-testid="stFileUploaderDropzone"] button {{ background:var(--qs-surface-2)!important;color:var(--qs-text)!important;border-color:var(--qs-border)!important; }}
[data-testid="stFileUploaderDropzone"]:hover {{ transform:translateY(-1px);border-color:var(--qs-accent)!important;box-shadow:0 14px 34px color-mix(in srgb,var(--qs-accent) 9%,transparent)!important; }}

/* Criteria chips: selected values should read as deliberate inputs, not validation errors. */
[data-baseweb="tag"] {{
  background:color-mix(in srgb,var(--qs-accent) 13%,var(--qs-surface))!important;
  border:1px solid color-mix(in srgb,var(--qs-accent) 28%,var(--qs-border))!important;
  color:var(--qs-text-2)!important;
  border-radius:9px!important;
  box-shadow:none!important;
}}
[data-baseweb="tag"] span {{ color:var(--qs-text-2)!important; }}
[data-baseweb="tag"] button {{
  color:var(--qs-accent)!important;
  background:transparent!important;
  border:0!important;
  box-shadow:none!important;
}}


/* Tabs / tables / expanders */
[data-testid="stTabs"] [role="tablist"] {{ gap:.3rem;border-bottom:1px solid var(--qs-border); }}
[data-testid="stTabs"] button {{ color:var(--qs-muted)!important;border-radius:10px 10px 0 0!important;font-weight:700!important; }}
[data-testid="stTabs"] button[aria-selected="true"] {{ color:var(--qs-accent)!important;background:color-mix(in srgb,var(--qs-accent) 8%,transparent)!important; }}
[data-testid="stExpander"] {{ border:1px solid var(--qs-border)!important;border-radius:14px!important;background:var(--qs-surface)!important;overflow:hidden; }}
[data-testid="stExpander"] summary:hover {{ background:color-mix(in srgb,var(--qs-accent) 7%,transparent)!important; }}
[data-testid="stDataFrame"] {{ border:1px solid var(--qs-border)!important;border-radius:14px!important;overflow:hidden;box-shadow:0 8px 24px rgba(15,23,42,.05)!important; }}
[data-testid="stAlert"] {{ border-radius:14px!important;border:1px solid var(--qs-border)!important;background:var(--qs-surface)!important; }}

/* Product shell */
.qs-product-bar {{
  display:flex;align-items:center;gap:.7rem;margin:0 0 1rem;padding:.78rem .9rem;
  border:1px solid var(--qs-border);border-radius:15px;
  background:linear-gradient(135deg,color-mix(in srgb,var(--qs-accent) 9%,var(--qs-surface)),var(--qs-surface));
  box-shadow:0 12px 34px color-mix(in srgb,var(--qs-accent) 6%,transparent);
}}
.qs-brand-dot {{ width:10px;height:10px;border-radius:999px;background:var(--qs-accent);box-shadow:0 0 0 5px color-mix(in srgb,var(--qs-accent) 13%,transparent);flex:0 0 auto; }}
.qs-brand-copy {{ flex:1;min-width:0; }}
.qs-brand-title {{ font-weight:850;color:var(--qs-text);font-size:1rem; }}
.qs-brand-sub {{ color:var(--qs-muted);font-size:.81rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis; }}
.qs-ready-pill {{ display:inline-flex;align-items:center;gap:.35rem;padding:.28rem .55rem;border:1px solid var(--qs-border);border-radius:999px;font-size:.75rem;font-weight:800;color:var(--qs-text-2); }}
.qs-ready-pill span {{ width:7px;height:7px;border-radius:999px;background:var(--qs-success);display:inline-block; }}
.qs-ready-pill.warn {{ color:var(--qs-warning);border-color:color-mix(in srgb,var(--qs-warning) 30%,var(--qs-border));background:color-mix(in srgb,var(--qs-warning) 8%,var(--qs-surface)); }}
.qs-ready-pill.warn span {{ background:var(--qs-warning); }}
.qs-session-chip {{ color:var(--qs-text-2); }}
.qs-session-chip.warn {{ color:var(--qs-warning); }}
.qs-session-card {{ margin:.35rem 0 1rem;padding:1rem 1.15rem;border:1px solid color-mix(in srgb,var(--qs-warning) 30%,var(--qs-border));border-radius:16px;background:linear-gradient(135deg,color-mix(in srgb,var(--qs-warning) 8%,var(--qs-surface)),var(--qs-surface));box-shadow:0 12px 28px color-mix(in srgb,var(--qs-warning) 7%,transparent); }}
.qs-session-kicker {{ color:var(--qs-warning);font-size:.68rem;font-weight:900;letter-spacing:.16em;text-transform:uppercase; }}
.qs-session-title {{ color:var(--qs-text);font-weight:850;font-size:1.02rem;margin-top:.3rem; }}
.qs-session-copy {{ color:var(--qs-muted);font-size:.88rem;line-height:1.55;margin-top:.3rem;max-width:880px; }}
.qs-kicker,.qs-sidebar-kicker,.qs-section-kicker {{ color:var(--qs-accent);font-size:.72rem;font-weight:850;letter-spacing:.16em;text-transform:uppercase; }}
.qs-hero-title {{ font-size:clamp(2rem,4vw,3rem);line-height:1.02;font-weight:850;letter-spacing:-.035em;color:var(--qs-text);margin:.55rem 0 .55rem; }}
.qs-hero-sub {{ color:var(--qs-muted);font-size:1rem;max-width:960px;line-height:1.6;margin-bottom:1rem; }}
.qs-upload-label {{ font-size:.88rem;font-weight:800;color:var(--qs-text-2);margin:.45rem 0 .45rem; }}

/* Upload header */
.qs-upload-head {{
  display:flex;align-items:flex-end;justify-content:space-between;gap:1rem;margin:.55rem 0 .5rem;padding:.15rem .1rem .05rem;
}}
.qs-upload-kicker {{ color:var(--qs-accent);font-size:.66rem;font-weight:900;letter-spacing:.15em;text-transform:uppercase; }}
.qs-upload-title {{ color:var(--qs-text);font-size:1.02rem;font-weight:850;margin-top:.18rem; }}
.qs-upload-copy {{ color:var(--qs-muted);font-size:.74rem;line-height:1.45;margin-top:.18rem;max-width:820px; }}
.qs-upload-badge {{ display:flex;gap:.32rem;flex-wrap:wrap;justify-content:flex-end; }}
.qs-upload-badge span {{ padding:.22rem .42rem;border:1px solid var(--qs-border);border-radius:999px;background:var(--qs-surface);color:var(--qs-muted);font-size:.61rem;font-weight:850;letter-spacing:.04em; }}

/* Empty / ready */
.qs-empty-card {{
  margin:.75rem 0 1rem;padding:1.1rem 1.2rem;border:1px solid var(--qs-border);border-radius:17px;
  background:linear-gradient(135deg,color-mix(in srgb,var(--qs-accent) 7%,var(--qs-surface)),var(--qs-surface));
  box-shadow:0 16px 40px color-mix(in srgb,#0f172a 6%,transparent);animation:qsFadeUp .4s ease both;
}}
.qs-empty-kicker {{ color:var(--qs-accent);font-size:.7rem;font-weight:850;letter-spacing:.15em; }}
.qs-empty-title {{ color:var(--qs-text);font-size:1.2rem;font-weight:820;margin-top:.2rem; }}
.qs-empty-copy {{ color:var(--qs-muted);line-height:1.55;margin-top:.3rem; }}
.qs-empty-actions {{ display:flex;gap:.45rem;flex-wrap:wrap;margin-top:.7rem;color:var(--qs-text-2);font-size:.8rem;font-weight:750; }}
.qs-empty-actions span:nth-child(2n) {{ color:var(--qs-accent); }}
.qs-file-state {{ display:flex;align-items:center;gap:.7rem;padding:.6rem .8rem;margin:.5rem 0 1rem;border-radius:12px;background:var(--qs-surface);border:1px solid var(--qs-border); }}
.qs-file-state span {{ color:var(--qs-muted);font-size:.82rem; }}

/* Pipeline */
.qs-step {{ padding:.8rem .85rem;border:1px solid var(--qs-border);border-radius:14px;background:var(--qs-surface);box-shadow:0 8px 24px rgba(15,23,42,.05);margin-bottom:1rem; }}
.qs-step.done {{ border-color:color-mix(in srgb,var(--qs-success) 28%,var(--qs-border)); }}
.qs-step.pending {{ opacity:.88; }}
.qs-step-head {{ display:flex;align-items:center;gap:.5rem;color:var(--qs-text); }}
.qs-step-num {{ width:26px;height:26px;border-radius:8px;background:color-mix(in srgb,var(--qs-accent) 12%,var(--qs-surface-2));display:inline-flex;align-items:center;justify-content:center;font-weight:850;color:var(--qs-accent);font-size:.76rem; }}
.qs-step-state {{ margin-left:auto;color:var(--qs-success);font-weight:900; }}
.qs-step-sub {{ color:var(--qs-muted);font-size:.78rem;margin-top:.35rem;line-height:1.45; }}

/* Metrics */
.qs-metric {{ background:var(--qs-surface);border:1px solid var(--qs-border);border-radius:16px;padding:.9rem 1rem;box-shadow:0 10px 30px rgba(15,23,42,.05);animation:qsFadeUp .35s ease both; }}
.qs-metric.good {{ border-color:color-mix(in srgb,var(--qs-success) 28%,var(--qs-border)); }}
.qs-metric.warn {{ border-color:color-mix(in srgb,var(--qs-warning) 32%,var(--qs-border)); }}
.qs-metric-value {{ color:var(--qs-text);font-size:1.55rem;font-weight:850;letter-spacing:-.02em; }}
.qs-metric-label {{ color:var(--qs-text-2);font-size:.78rem;font-weight:800;margin-top:.05rem; }}
.qs-metric-sub {{ color:var(--qs-muted);font-size:.72rem;margin-top:.2rem; }}
.qs-results-title {{ margin:1.2rem 0 .65rem;color:var(--qs-text);font-size:1.05rem;font-weight:830; }}

/* Recommendation / risk */
.qs-recommendation-card {{ background:linear-gradient(135deg,color-mix(in srgb,var(--qs-accent) 12%,var(--qs-surface)),var(--qs-surface));border:1px solid color-mix(in srgb,var(--qs-accent) 28%,var(--qs-border));border-radius:18px;padding:1rem 1.1rem;box-shadow:0 16px 38px color-mix(in srgb,var(--qs-accent) 8%,transparent); }}
.qs-reco-kicker {{ color:var(--qs-accent);font-size:.7rem;font-weight:850;letter-spacing:.15em; }}
.qs-reco-title {{ color:var(--qs-text);font-size:1.45rem;font-weight:860;margin:.2rem 0 .25rem; }}
.qs-reco-copy {{ color:var(--qs-text-2);line-height:1.55; }}
.qs-reco-foot {{ color:var(--qs-muted);font-size:.74rem;margin-top:.6rem; }}
.qs-success-card {{ display:flex;gap:.7rem;align-items:flex-start;padding:.9rem 1rem;border:1px solid color-mix(in srgb,var(--qs-success) 28%,var(--qs-border));background:color-mix(in srgb,var(--qs-success) 5%,var(--qs-surface));border-radius:14px; }}
.qs-success-card>span {{ color:var(--qs-success);font-weight:900;font-size:1.1rem; }}
.qs-success-card div div {{ color:var(--qs-muted);font-size:.82rem;margin-top:.15rem; }}
.qs-risk-card {{ padding:.85rem 1rem;border:1px solid var(--qs-border);border-radius:15px;background:var(--qs-surface);margin-bottom:.7rem;box-shadow:0 8px 24px rgba(15,23,42,.04); }}
.qs-risk-card.danger {{ border-color:color-mix(in srgb,var(--qs-danger) 32%,var(--qs-border));background:color-mix(in srgb,var(--qs-danger) 4%,var(--qs-surface)); }}
.qs-risk-card.warn {{ border-color:color-mix(in srgb,var(--qs-warning) 32%,var(--qs-border));background:color-mix(in srgb,var(--qs-warning) 4%,var(--qs-surface)); }}
.qs-risk-top {{ display:flex;align-items:center;justify-content:space-between;gap:.7rem;color:var(--qs-text); }}
.qs-risk-top span {{ font-size:.7rem;font-weight:850;color:var(--qs-text-2);padding:.25rem .45rem;border:1px solid var(--qs-border);border-radius:999px; }}
.qs-risk-card ul {{ color:var(--qs-muted);margin:.5rem 0 0 1rem;padding:0; }}
.qs-section-spaced {{ margin-top:1rem; }}
.qs-sidebar-title {{ color:var(--qs-text);font-size:1.05rem;font-weight:850;margin-bottom:.35rem; }}
.qs-meta-chips {{ display:flex;gap:.35rem;flex-wrap:wrap;margin:.35rem 0 .65rem; }}
.qs-meta-chips span {{ display:inline-flex;padding:.26rem .5rem;border-radius:999px;background:color-mix(in srgb,var(--qs-accent) 10%,var(--qs-surface-2));border:1px solid var(--qs-border);font-size:.72rem;font-weight:800;color:var(--qs-text-2); }}
.qs-side-step {{ padding:.52rem .6rem;margin:.3rem 0;border-radius:10px;background:var(--qs-surface);border:1px solid var(--qs-border);color:var(--qs-text-2);font-size:.78rem; }}

@keyframes qsFadeUp {{ from {{ opacity:0;transform:translateY(6px); }} to {{ opacity:1;transform:none; }} }}
@media (max-width:980px) {{
  .qs-brand-sub {{ display:none; }}
  .qs-hero-title {{ font-size:2.15rem; }}
  [data-testid="stAppViewContainer"]>.main .block-container {{ padding-left:.9rem!important;padding-right:.9rem!important; }}
}}
@media (prefers-reduced-motion:reduce) {{ *,*::before,*::after {{ animation-duration:.001ms!important;transition-duration:.001ms!important; }} }}

/* Sidebar control parity with the proven AI Automation implementation. */
[data-testid="stSidebarCollapseButton"], [data-testid="stSidebarCollapseButton"] button,
[data-testid="stSidebarCollapsedControl"], [data-testid="stSidebarCollapsedControl"] button,
[data-testid="collapsedControl"], [data-testid="collapsedControl"] button {{
  opacity:1!important; visibility:visible!important; pointer-events:auto!important; z-index:100001!important;
}}
.qs-product-meta {{ display:flex; gap:.38rem; align-items:center; flex-wrap:wrap; }}
.qs-brand-mark {{ width:34px; height:34px; border-radius:11px; display:grid; place-items:center; background:linear-gradient(135deg,var(--qs-accent),var(--qs-accent-2)); color:#fff; font-weight:900; box-shadow:0 9px 24px color-mix(in srgb,var(--qs-accent) 20%,transparent); flex:0 0 auto; }}
.qs-mini-chip {{ padding:.22rem .48rem; border:1px solid var(--qs-border); border-radius:999px; font-size:.65rem; color:var(--qs-text-2); background:var(--qs-surface); font-weight:800; }}
.qs-hero {{ display:grid; grid-template-columns:minmax(0,1.45fr) minmax(310px,.75fr); gap:1rem; margin:0 0 1.05rem; padding:1.15rem; border:1px solid var(--qs-border); border-radius:20px; background:linear-gradient(135deg,color-mix(in srgb,var(--qs-accent) 7%,var(--qs-surface)),var(--qs-surface)); box-shadow:0 18px 48px rgba(15,23,42,.06); }}
.qs-hero-copy {{ padding:.35rem .35rem .25rem; }}
.qs-hero-panel {{ border:1px solid var(--qs-border); border-radius:16px; padding:.85rem; background:var(--qs-surface); }}
.qs-hero-panel-kicker,.qs-card-kicker {{ color:var(--qs-accent); font-size:.68rem; font-weight:900; letter-spacing:.14em; text-transform:uppercase; margin-bottom:.55rem; }}
.qs-flow-item {{ display:flex; gap:.6rem; padding:.56rem .45rem; border-top:1px solid var(--qs-border); }}
.qs-flow-item:first-of-type {{ border-top:0; }}
.qs-flow-item>span {{ width:25px; height:25px; display:grid; place-items:center; border-radius:8px; background:color-mix(in srgb,var(--qs-accent) 12%,var(--qs-surface-2)); color:var(--qs-accent); font-size:.67rem; font-weight:900; }}
.qs-flow-item strong {{ display:block; color:var(--qs-text); font-size:.8rem; }}
.qs-flow-item small {{ display:block; color:var(--qs-muted); font-size:.68rem; margin-top:.1rem; line-height:1.4; }}
.qs-hero-chips {{ display:flex; gap:.4rem; flex-wrap:wrap; margin-top:.85rem; }}
.qs-hero-chips span {{ padding:.3rem .55rem; border:1px solid var(--qs-border); border-radius:999px; background:var(--qs-surface); color:var(--qs-text-2); font-size:.68rem; font-weight:800; }}
.qs-ready-grid {{ display:grid; grid-template-columns:2fr 1fr 1fr; gap:.75rem; margin:.2rem 0 1rem; }}
.qs-ready-card {{ min-height:116px; padding:.95rem 1rem; border:1px solid var(--qs-border); border-radius:16px; background:var(--qs-surface); box-shadow:0 10px 28px rgba(15,23,42,.045); }}
.qs-ready-card.main {{ background:linear-gradient(135deg,color-mix(in srgb,var(--qs-accent) 8%,var(--qs-surface)),var(--qs-surface)); }}
.qs-ready-card strong {{ display:block; color:var(--qs-text); font-size:.86rem; }}
.qs-ready-card small {{ display:block; color:var(--qs-muted); line-height:1.45; margin-top:.3rem; font-size:.72rem; }}
.qs-workspace-strip {{ display:flex; align-items:center; gap:.6rem; flex-wrap:wrap; margin:.1rem 0 .8rem; padding:.62rem .78rem; border:1px solid var(--qs-border); border-radius:13px; background:var(--qs-surface); box-shadow:0 7px 20px rgba(15,23,42,.035); }}
.qs-workspace-strip>div {{ display:flex; align-items:center; gap:.38rem; margin-right:auto; }}
.qs-workspace-strip>span {{ color:var(--qs-muted); font-size:.68rem; padding:.24rem .48rem; border-radius:999px; background:var(--qs-surface-2); }}
.qs-workspace-strip.ready {{ border-color:color-mix(in srgb,var(--qs-accent) 28%,var(--qs-border)); background:linear-gradient(90deg,color-mix(in srgb,var(--qs-accent) 4%,var(--qs-surface)),var(--qs-surface)); }}
.qs-workspace-strip.complete {{ border-color:color-mix(in srgb,var(--qs-success) 28%,var(--qs-border)); background:linear-gradient(90deg,color-mix(in srgb,var(--qs-success) 4%,var(--qs-surface)),var(--qs-surface)); }}
.qs-workspace-strip.waiting {{ border-color:var(--qs-border); }}
.qs-status-dot {{ width:7px; height:7px; border-radius:999px; display:inline-block; background:var(--qs-success); box-shadow:0 0 0 4px color-mix(in srgb,var(--qs-success) 10%,transparent); }}
.qs-workspace-strip.ready .qs-status-dot {{ background:var(--qs-accent); box-shadow:0 0 0 4px color-mix(in srgb,var(--qs-accent) 10%,transparent); }}
.qs-sidebar-brand {{ display:flex; align-items:center; gap:.62rem; padding:.25rem 0 1rem; }}
.qs-sidebar-mark {{ width:34px; height:34px; display:grid; place-items:center; border-radius:11px; background:linear-gradient(135deg,var(--qs-accent),var(--qs-accent-2)); color:#fff; font-weight:900; box-shadow:0 8px 22px color-mix(in srgb,var(--qs-accent) 20%,transparent); }}
.qs-sidebar-brand strong {{ display:block; color:var(--qs-text); font-size:.78rem; letter-spacing:.08em; }}
.qs-sidebar-brand small {{ display:block; color:var(--qs-muted); font-size:.58rem; letter-spacing:.1em; margin-top:.08rem; }}
.qs-sidebar-note {{ color:var(--qs-muted); font-size:.72rem; line-height:1.5; margin-bottom:.8rem; }}
.qs-sidebar-health {{ display:grid; gap:.28rem; padding:.7rem .75rem; border:1px solid var(--qs-border); border-radius:13px; background:var(--qs-surface); margin:.45rem 0 .85rem; }}
.qs-sidebar-health div {{ display:flex; align-items:center; gap:.35rem; color:var(--qs-text-2); font-size:.72rem; font-weight:800; }}
.qs-sidebar-health small {{ color:var(--qs-muted); font-size:.62rem; }}
.qs-sidebar-workflow {{ margin-top:.3rem; }}
.qs-section-spaced {{ margin-top:.9rem; }}
.qs-risk-card {{ border:1px solid var(--qs-border); border-radius:15px; padding:.85rem 1rem; background:var(--qs-surface); margin:.55rem 0; }}
.qs-risk-card.danger {{ border-color:color-mix(in srgb,var(--qs-danger) 26%,var(--qs-border)); background:color-mix(in srgb,var(--qs-danger) 4%,var(--qs-surface)); }}
.qs-risk-card.warn {{ border-color:color-mix(in srgb,var(--qs-warning) 28%,var(--qs-border)); background:color-mix(in srgb,var(--qs-warning) 4%,var(--qs-surface)); }}
.qs-risk-top {{ display:flex; justify-content:space-between; gap:1rem; color:var(--qs-text); }}
.qs-risk-top span {{ color:var(--qs-warning); font-size:.67rem; font-weight:900; letter-spacing:.08em; }}
.qs-risk-card ul {{ margin:.4rem 0 0 1rem; color:var(--qs-text-2); }}
@media (max-width: 900px) {{ .qs-hero,.qs-ready-grid {{ grid-template-columns:1fr; }} .qs-product-meta {{ display:none; }} .qs-upload-head {{ align-items:flex-start; flex-direction:column; }} .qs-upload-badge {{ justify-content:flex-start; }} }}

.qs-decision-hero {{ display:grid; grid-template-columns:minmax(0,1.5fr) minmax(250px,.55fr); gap:.8rem; margin:.8rem 0 .75rem; }}
.qs-decision-main {{ padding:1.15rem 1.2rem; border:1px solid color-mix(in srgb,var(--qs-accent) 24%,var(--qs-border)); border-radius:18px; background:linear-gradient(135deg,color-mix(in srgb,var(--qs-accent) 9%,var(--qs-surface)),var(--qs-surface)); box-shadow:0 16px 42px color-mix(in srgb,var(--qs-accent) 7%,transparent); }}
.qs-decision-supplier {{ margin:.2rem 0 .35rem; font-size:1.55rem; font-weight:900; color:var(--qs-text); }}
.qs-decision-reason {{ color:var(--qs-text-2); line-height:1.55; max-width:75ch; }}
.qs-reason-row {{ display:flex; gap:.4rem; flex-wrap:wrap; margin-top:.8rem; }}
.qs-reason-chip {{ display:inline-flex; align-items:center; gap:.3rem; padding:.3rem .5rem; border-radius:999px; border:1px solid color-mix(in srgb,var(--qs-accent) 20%,var(--qs-border)); background:var(--qs-surface); color:var(--qs-text-2); font-size:.68rem; font-weight:800; }}
.qs-reason-chip span {{ color:var(--qs-success); font-weight:900; }}
.qs-score-panel {{ display:flex; flex-direction:column; justify-content:center; min-height:170px; padding:1rem; border-radius:18px; border:1px solid var(--qs-border); background:var(--qs-surface); box-shadow:0 12px 32px rgba(15,23,42,.05); }}
.qs-score-panel.good {{ border-color:color-mix(in srgb,var(--qs-success) 34%,var(--qs-border)); background:linear-gradient(160deg,color-mix(in srgb,var(--qs-success) 5%,var(--qs-surface)),var(--qs-surface)); }}
.qs-score-panel.warn {{ border-color:color-mix(in srgb,var(--qs-warning) 34%,var(--qs-border)); }}
.qs-score-label {{ color:var(--qs-muted); font-size:.68rem; font-weight:900; letter-spacing:.13em; }}
.qs-score-value {{ margin:.2rem 0 .2rem; color:var(--qs-text); font-size:2rem; font-weight:950; letter-spacing:-.04em; }}
.qs-score-sub {{ color:var(--qs-muted); font-size:.72rem; line-height:1.45; }}
.qs-decision-meta-grid {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.65rem; margin-bottom:.7rem; }}
.qs-decision-meta-card {{ padding:.78rem .82rem; border:1px solid var(--qs-border); border-radius:14px; background:var(--qs-surface); }}
.qs-decision-meta-card.good {{ border-color:color-mix(in srgb,var(--qs-success) 26%,var(--qs-border)); }}
.qs-decision-meta-card.warn {{ border-color:color-mix(in srgb,var(--qs-warning) 26%,var(--qs-border)); }}
.qs-decision-meta-card.danger {{ border-color:color-mix(in srgb,var(--qs-danger) 28%,var(--qs-border)); }}
.qs-decision-meta-card>span {{ display:block; color:var(--qs-muted); font-size:.61rem; font-weight:900; letter-spacing:.11em; }}
.qs-decision-meta-card>strong {{ display:block; color:var(--qs-text); font-size:1.05rem; font-weight:900; margin:.18rem 0 .12rem; }}
.qs-decision-meta-card>small {{ display:block; color:var(--qs-muted); font-size:.66rem; line-height:1.35; }}
.qs-score-breakdown {{ padding:.75rem .78rem; border:1px solid var(--qs-border); border-radius:14px; background:var(--qs-surface); min-height:88px; }}
.qs-score-breakdown-top {{ display:flex; justify-content:space-between; gap:.5rem; align-items:center; color:var(--qs-text); font-size:.72rem; }}
.qs-score-breakdown-top span {{ font-weight:900; font-size:.9rem; }}
.qs-score-track {{ height:6px; margin:.45rem 0 .35rem; border-radius:999px; overflow:hidden; background:var(--qs-surface-2); }}
.qs-score-track span {{ display:block; height:100%; border-radius:999px; background:linear-gradient(90deg,var(--qs-accent),var(--qs-accent-2)); }}
.qs-score-breakdown small {{ color:var(--qs-muted); font-size:.6rem; }}
.qs-why-card {{ min-height:94px; padding:.78rem .82rem; border:1px solid var(--qs-border); border-radius:14px; background:var(--qs-surface); }}
.qs-why-card>span {{ color:var(--qs-success); font-weight:900; margin-right:.35rem; }}
.qs-why-card>strong {{ color:var(--qs-text); font-size:.76rem; }}
.qs-why-card>small {{ display:block; color:var(--qs-muted); font-size:.66rem; line-height:1.4; margin-top:.3rem; }}
.qs-risk-inline {{ display:flex; justify-content:flex-end; margin:.55rem 0 .15rem; }}
.qs-risk-count {{ display:inline-flex; align-items:center; gap:.25rem; padding:.32rem .52rem; border-radius:999px; background:color-mix(in srgb,var(--qs-success) 7%,var(--qs-surface)); border:1px solid color-mix(in srgb,var(--qs-success) 24%,var(--qs-border)); color:var(--qs-success); font-size:.67rem; font-weight:850; }}
.qs-risk-count.danger {{ background:color-mix(in srgb,var(--qs-danger) 6%,var(--qs-surface)); border-color:color-mix(in srgb,var(--qs-danger) 26%,var(--qs-border)); color:var(--qs-danger); }}
@media (max-width:1000px) {{ .qs-decision-hero {{ grid-template-columns:1fr; }} .qs-decision-meta-grid {{ grid-template-columns:repeat(2,minmax(0,1fr)); }} }}
@media (max-width:700px) {{ .qs-decision-meta-grid {{ grid-template-columns:1fr; }} }}
</style>
"""
    st.markdown(css, unsafe_allow_html=True)
