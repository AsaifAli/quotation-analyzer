"""Portfolio-ready Streamlit dashboard for quotation intelligence."""
import json
import os
import tempfile
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from modules.ai_agent import QuotationIntelligenceAgent
import config
from ui_theme import apply_theme

st.set_page_config(
    page_title="QuoteSense · Procurement Intelligence",
    page_icon="📑",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()

# Portfolio handoff: bind the temporary gateway JWT to this Streamlit execution.
portfolio_token = str(st.query_params.get("portfolio_llm_session", "")).strip()
if portfolio_token:
    from llm_gateway_context import set_llm_gateway_token

    set_llm_gateway_token(portfolio_token)
    try:
        del st.query_params["portfolio_llm_session"]
    except Exception:
        pass


@st.cache_resource
def get_agent():
    return QuotationIntelligenceAgent()


def money(v, currency=""):
    try:
        return f"{currency or ''} {float(v):,.2f}".strip()
    except (TypeError, ValueError):
        return "N/A"


def _safe_score(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _supplier_name(quote: dict) -> str:
    return str(quote.get("supplier") or quote.get("vendor") or "Unknown supplier")


def _top_score(scores: list[dict]) -> dict | None:
    return scores[0] if scores else None


def _render_header(agent: QuotationIntelligenceAgent) -> None:
    st.markdown(
        f"""
        <div class="qs-product-bar">
          <div class="qs-brand-dot"></div>
          <div class="qs-brand-copy">
            <div class="qs-brand-title">QuoteSense</div>
            <div class="qs-brand-sub">Procurement intelligence · structured extraction · deterministic scoring · evidence-backed recommendation</div>
          </div>
          <div class="qs-ready-pill"><span></span> Ready</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_hero() -> None:
    st.markdown(
        """
        <div class="qs-kicker">QUOTATION INTELLIGENCE</div>
        <div class="qs-hero-title">Turn supplier quotations into a decision.</div>
        <div class="qs-hero-sub">Extract commercial terms, validate completeness, compare suppliers, surface risk, and explain the strongest option.</div>
        """,
        unsafe_allow_html=True,
    )


def _render_pipeline(has_result: bool) -> None:
    states = [
        ("1", "Extract", "Structured fields + source evidence.", True),
        ("2", "Score", "Deterministic multi-criteria ranking.", has_result),
        ("3", "Decide", "Risks, trade-offs + recommendation.", has_result),
    ]
    cols = st.columns(3, gap="medium")
    for col, (num, title, sub, done) in zip(cols, states):
        with col:
            state_class = "done" if done else "pending"
            icon = "✓" if done else "·"
            st.markdown(
                f"""
                <div class="qs-step {state_class}">
                  <div class="qs-step-head"><span class="qs-step-num">{num}</span><strong>{title}</strong><span class="qs-step-state">{icon}</span></div>
                  <div class="qs-step-sub">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_empty_state(uploaded: list | None) -> None:
    if uploaded:
        return
    st.markdown(
        """
        <div class="qs-empty-card">
          <div class="qs-empty-kicker">READY TO ANALYZE</div>
          <div class="qs-empty-title">Add quotations to start</div>
          <div class="qs-empty-copy">Upload one or more supplier files. QuoteSense will extract the commercial terms, compare suppliers, flag risk, and produce an evidence-linked recommendation.</div>
          <div class="qs-empty-actions">
            <span>Upload quotations</span><span>•</span><span>Set criteria</span><span>•</span><span>Analyze</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_summary_metrics(result: dict) -> None:
    quotes = result.get("quotations", [])
    scores = result.get("scores", [])
    validation = result.get("validation", [])
    avg = sum(float(x.get("completeness_score", 0) or 0) for x in validation) / len(validation) if validation else 0
    best = _top_score(scores)
    best_label = f"{best.get('score', 0):.1f}/100" if best and _safe_score(best.get("score")) is not None else "N/A"
    primary = (result.get("recommendation", {}) or {}).get("recommendations", {}).get("primary_recommendation", {}) or {}
    primary_name = primary.get("supplier") or (best.get("supplier") if best else "Pending")

    cards = [
        (str(len(quotes)), "Quotations", "Documents analyzed", "neutral"),
        (str(len(result.get("documents", []))), "Documents", "Source files", "neutral"),
        (f"{avg:.1f}%", "Completeness", "Average extracted coverage", "good" if avg >= 85 else "warn"),
        (best_label, "Top score", str(primary_name), "good" if best else "neutral"),
    ]
    cols = st.columns(4, gap="small")
    for col, (value, label, sub, tone) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="qs-metric {tone}">
                  <div class="qs-metric-value">{value}</div>
                  <div class="qs-metric-label">{label}</div>
                  <div class="qs-metric-sub">{sub}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_supplier_snapshot(result: dict) -> None:
    scores = result.get("scores", [])
    quotes = result.get("quotations", [])
    if not scores and not quotes:
        return
    quote_map = {_supplier_name(q): q for q in quotes}
    rows = []
    for rank, item in enumerate(scores or [], start=1):
        supplier = str(item.get("supplier") or "Unknown")
        quote = quote_map.get(supplier, {})
        rows.append(
            {
                "#": rank,
                "Supplier": supplier,
                "Score": round(float(item.get("score") or 0), 1),
                "Cost": money(quote.get("total_cost"), quote.get("currency")),
                "Timeline": quote.get("delivery_timeline") or "—",
                "Validity": quote.get("validity_period") or "—",
            }
        )
    if not rows:
        return
    st.markdown('<div class="qs-section-kicker">DECISION SNAPSHOT</div>', unsafe_allow_html=True)
    left, right = st.columns([1.35, 1], gap="large")
    with left:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with right:
        df = pd.DataFrame([{"Supplier": x["supplier"], "Score": x.get("score") or 0} for x in scores])
        fig = px.bar(df, x="Supplier", y="Score", range_y=[0, 100], title="Deterministic procurement score")
        fig.update_layout(
            margin=dict(l=8, r=8, t=42, b=8),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            font=dict(size=12),
        )
        fig.update_traces(marker_line_width=0)
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


def _render_recommendation(result: dict) -> None:
    rec = (result.get("recommendation", {}) or {}).get("recommendations", {}) or {}
    primary = rec.get("primary_recommendation", {}) or {}
    if not primary:
        st.info("No qualitative recommendation was requested or generated.")
        return
    supplier = primary.get("supplier") or "Recommended supplier"
    reason = primary.get("reason") or "Recommendation details are available below."
    st.markdown(
        f"""
        <div class="qs-recommendation-card">
          <div class="qs-reco-kicker">RECOMMENDED OPTION</div>
          <div class="qs-reco-title">{supplier}</div>
          <div class="qs-reco-copy">{reason}</div>
          <div class="qs-reco-foot">Evidence-backed qualitative recommendation · numeric ranking remains deterministic</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    with st.expander("Why this supplier?", expanded=True):
        st.json(rec)


def _render_risks(result: dict) -> None:
    risks = result.get("risks", []) or []
    validation = result.get("validation", []) or []
    if not risks:
        st.markdown(
            """
            <div class="qs-success-card"><span>✓</span><div><strong>No material risks surfaced.</strong><div>Validation data is still available below for inspection.</div></div></div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for risk in risks:
            level = str(risk.get("level") or "medium").lower()
            tone = "danger" if level in {"critical", "high"} else "warn"
            items = "".join(f"<li>{x}</li>" for x in (risk.get("items") or []))
            st.markdown(
                f"""
                <div class="qs-risk-card {tone}">
                  <div class="qs-risk-top"><strong>{risk.get('supplier', 'Supplier')}</strong><span>{level.upper()}</span></div>
                  <ul>{items}</ul>
                </div>
                """,
                unsafe_allow_html=True,
            )
    if validation:
        st.markdown('<div class="qs-section-kicker qs-section-spaced">VALIDATION</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(validation), use_container_width=True, hide_index=True)


def _render_evidence(result: dict) -> None:
    evidence = result.get("evidence", []) or []
    if not evidence:
        st.info("No evidence records were returned for this analysis.")
        return
    for item in evidence:
        location = item.get("location", "Source")
        source = item.get("source", "Evidence")
        with st.expander(f"{location} · {source}", expanded=False):
            st.markdown(item.get("text", ""))


def main():
    agent = get_agent()
    _render_header(agent)
    _render_hero()

    with st.sidebar:
        st.markdown('<div class="qs-sidebar-title">Analysis workspace</div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="qs-meta-chips"><span>Provider · {agent.llm.provider}</span><span>Model · {agent.llm.model}</span></div>',
            unsafe_allow_html=True,
        )
        st.caption("Configure the decision criteria, then upload one or more supplier quotations.")
        query = st.text_area(
            "Analysis request",
            "Compare the quotations, explain trade-offs, identify risks, and recommend the strongest option.",
            height=120,
        )
        criteria = st.multiselect(
            "Criteria",
            ["cost", "completeness", "timeline", "terms", "risk"],
            ["cost", "completeness", "timeline", "terms", "risk"],
        )
        run = st.button("🚀 Analyze quotations", type="primary", use_container_width=True)
        st.divider()
        st.markdown('<div class="qs-sidebar-kicker">WORKFLOW</div>', unsafe_allow_html=True)
        st.markdown('<div class="qs-side-step">01 · Extract supplier terms</div>', unsafe_allow_html=True)
        st.markdown('<div class="qs-side-step">02 · Score deterministically</div>', unsafe_allow_html=True)
        st.markdown('<div class="qs-side-step">03 · Explain risk + recommendation</div>', unsafe_allow_html=True)

    st.markdown('<div class="qs-upload-label">Upload one or more supplier quotations</div>', unsafe_allow_html=True)
    uploaded = st.file_uploader(
        "",
        type=[x.lstrip('.') for x in config.SUPPORTED_FORMATS],
        accept_multiple_files=True,
        help="Upload PDF, DOCX, TXT or XLSX supplier quotation files.",
    )

    result = st.session_state.get("result")
    _render_pipeline(bool(result))

    if not uploaded:
        _render_empty_state(uploaded)
        if result:
            st.info("No documents are currently selected. Showing the results from the last completed analysis.")
            if st.button("Clear previous results", icon=":material/delete_sweep:"):
                st.session_state.pop("result", None)
                st.rerun()
    else:
        st.markdown(
            f'<div class="qs-file-state"><strong>{len(uploaded)} quotation(s) ready</strong><span>Review the files, then run analysis.</span></div>',
            unsafe_allow_html=True,
        )
        current_files = [item.name for item in uploaded]
        previous_files = result.get("uploaded_files", []) if result else []
        if result and current_files != previous_files and not run:
            st.warning("These documents have not been analyzed yet. Click Analyze quotations to replace the previous result set.")

    if run:
        if not uploaded:
            st.warning("Please upload at least one quotation before starting an analysis.")
        else:
            paths = []
            metadata = []
            try:
                for item in uploaded:
                    suffix = os.path.splitext(item.name)[1].lower()
                    fd, path = tempfile.mkstemp(suffix=suffix)
                    with os.fdopen(fd, "wb") as tmp:
                        tmp.write(item.getvalue())
                    paths.append(path)
                    metadata.append(item.name)
                progress = st.progress(0, text="Extracting quotations…")
                with st.spinner("Running multi-document quotation pipeline…"):
                    progress.progress(35, text="Extracting structured fields…")
                    result = agent.process_documents(paths, query=query, criteria=criteria)
                    progress.progress(78, text="Scoring suppliers and validating terms…")
                    result["uploaded_files"] = metadata
                    st.session_state["result"] = result
                    progress.progress(100, text="Recommendation ready")
                progress.empty()
                st.toast("Quotation analysis complete", icon="✅")
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")
            finally:
                for path in paths:
                    if os.path.exists(path):
                        os.unlink(path)

    result = st.session_state.get("result")
    if not result:
        return

    st.markdown('<div class="qs-results-title">Analysis results</div>', unsafe_allow_html=True)
    _render_summary_metrics(result)
    _render_supplier_snapshot(result)

    tabs = st.tabs([
        "Overview",
        "Quotations",
        "Scoring",
        "Risks & Validation",
        "Recommendation",
        "Evidence",
        "Raw",
    ])

    with tabs[0]:
        _render_recommendation(result)
        if result.get("metrics"):
            with st.expander("Execution metrics", expanded=False):
                st.json(result["metrics"])

    with tabs[1]:
        quotes = result.get("quotations", [])
        rows = [
            {
                "Supplier": _supplier_name(q),
                "Cost": money(q.get("total_cost"), q.get("currency")),
                "Timeline": q.get("delivery_timeline") or "—",
                "Validity": q.get("validity_period") or "—",
                "Features": ", ".join(q.get("key_features", []) or []),
            }
            for q in quotes
        ]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.download_button(
            "Download extracted quotations",
            json.dumps(quotes, indent=2),
            "quotations.json",
            "application/json",
            icon=":material/download:",
        )

    with tabs[2]:
        scores = result.get("scores", [])
        if scores:
            st.dataframe(pd.DataFrame(scores), use_container_width=True, hide_index=True)
            st.caption("The ranking is deterministic. The LLM does not directly control the numeric score.")
        else:
            st.info("No scoring records returned.")

    with tabs[3]:
        _render_risks(result)

    with tabs[4]:
        _render_recommendation(result)

    with tabs[5]:
        _render_evidence(result)

    with tabs[6]:
        st.json(result)


if __name__ == "__main__":
    main()
