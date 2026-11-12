
"""Portfolio-ready Streamlit dashboard for quotation intelligence."""

import base64
import json
import math
import os
import tempfile
import time
import html
from typing import Any

import pandas as pd
import plotly.express as px
import requests
import streamlit as st

from modules.ai_agent import QuotationIntelligenceAgent
from modules.scoring import count_risk_findings
from modules.report import analysis_json, analysis_xlsx, quotations_csv
import config
from ui_theme import apply_theme
from sidebar_toggle import render_sidebar_toggle

st.set_page_config(
    page_title="QuoteSense · Procurement Intelligence",
    page_icon="📑",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()
render_sidebar_toggle()

# Portfolio handoff: persist the temporary gateway JWT in Streamlit session state.
# Keep the query parameter so full-page refreshes can reconstruct the session.
from llm_gateway_context import set_llm_gateway_token

_HANDOFF_PARAM = "portfolio_llm_session"
_GATEWAY_STATUS_CACHE_SECONDS = 8


def _clear_gateway_session() -> None:
    """Remove an invalid portfolio token from session state and the URL."""
    st.session_state.pop("portfolio_llm_session", None)
    st.session_state.pop("gateway_status", None)
    st.session_state.pop("gateway_session", None)
    st.session_state.pop("gateway_status_checked_at", None)

    try:
        if _HANDOFF_PARAM in st.query_params:
            del st.query_params[_HANDOFF_PARAM]
    except Exception:
        # Session cleanup must still succeed if query parameters are unavailable.
        pass

    set_llm_gateway_token("")


def _decode_jwt_claims(token: str) -> dict[str, Any]:
    """Decode JWT payload for display-only metadata; never trust these claims for auth."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        return json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
    except Exception:
        return {}


def _gateway_status(token: str) -> tuple[bool, dict[str, Any]]:
    if not token or not config.LLM_GATEWAY_URL.strip():
        return False, {}

    now = time.time()
    cached_at = float(
        st.session_state.get("gateway_status_checked_at", 0) or 0
    )

    if (
        now - cached_at < _GATEWAY_STATUS_CACHE_SECONDS
        and "gateway_status" in st.session_state
    ):
        return (
            bool(st.session_state["gateway_status"]),
            dict(st.session_state.get("gateway_session", {}) or {}),
        )

    url = (
        f"{config.LLM_GATEWAY_URL.strip().rstrip('/')}"
        "/demo/session/status"
    )

    try:
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            },
            timeout=5,
        )

        # Temporary gateway diagnostic metadata.
        st.session_state["gateway_debug"] = {
            "status_code": response.status_code,
        }

        if response.ok:
            data = response.json()
            st.session_state["gateway_status"] = True
            st.session_state["gateway_session"] = data
            st.session_state["gateway_status_checked_at"] = now
            return True, data

        if response.status_code in {401, 403}:
            _clear_gateway_session()

        st.session_state["gateway_status"] = False
        st.session_state["gateway_session"] = {}
        st.session_state["gateway_status_checked_at"] = now
        return False, {}
    except (requests.RequestException, ValueError):
        st.session_state["gateway_debug"] = {
            "status_code": None,
        }

        # Keep the local token available if the status endpoint is temporarily
        # unavailable. The actual completion request remains authoritative.
        st.session_state["gateway_status"] = bool(token)
        st.session_state["gateway_session"] = {}
        st.session_state["gateway_status_checked_at"] = now
        return bool(token), {}


portfolio_token = str(
    st.query_params.get(_HANDOFF_PARAM, "") or ""
).strip()

if portfolio_token:
    st.session_state["portfolio_llm_session"] = portfolio_token
    st.session_state.pop("gateway_status_checked_at", None)
    st.session_state.pop("gateway_status", None)
    st.session_state.pop("gateway_session", None)

    # Keep the handoff token in the URL so a browser refresh can reconstruct
    # the same portfolio-backed session. The gateway remains authoritative
    # via /demo/session/status and does not extend the token lifetime.

portfolio_token = str(
    st.session_state.get("portfolio_llm_session", "") or ""
).strip()

set_llm_gateway_token(portfolio_token)

gateway_mode = bool(config.LLM_GATEWAY_URL.strip())
local_claims = _decode_jwt_claims(portfolio_token) if portfolio_token else {}

server_session_active, server_session = (
    _gateway_status(portfolio_token)
    if gateway_mode and portfolio_token
    else (False, {})
)

if (
    gateway_mode
    and portfolio_token
    and not server_session_active
    and not st.session_state.get("portfolio_llm_session")
):
    portfolio_token = ""
    local_claims = {}

session_active = (
    server_session_active
    if gateway_mode
    else bool(portfolio_token)
)

session_provider = str(
    server_session.get("provider")
    or local_claims.get("provider")
    or ""
)

session_model = str(
    server_session.get("model")
    or local_claims.get("model")
    or ""
)


def get_agent(gateway_token: str = ""):
    """Build an agent with explicit gateway-session injection."""
    return QuotationIntelligenceAgent(
        gateway_token=gateway_token
    )


def money(v, currency=""):
    try:
        amount = float(v)
        if not math.isfinite(amount):
            return "N/A"
        return f"{currency or ''} {amount:,.2f}".strip()
    except (TypeError, ValueError, OverflowError):
        return "N/A"


def _safe_score(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _supplier_name(quote: dict) -> str:
    return str(
        quote.get("supplier")
        or quote.get("vendor")
        or "Unknown supplier"
    )


def _top_score(scores: list[dict]) -> dict | None:
    return scores[0] if scores else None



def _render_header(
    agent: QuotationIntelligenceAgent,
    session_active: bool,
    gateway_mode: bool,
    session_provider: str = "",
    session_model: str = "",
) -> None:
    status_label = (
        "Session active"
        if session_active
        else (
            "Session invalid"
            if gateway_mode and portfolio_token
            else (
                "Session required"
                if gateway_mode
                else "Ready"
            )
        )
    )

    status_class = "" if session_active else (
        " warn" if gateway_mode else ""
    )

    st.markdown(
        f"""
        <div class="qs-product-bar">
          <div class="qs-brand-mark">$</div>
          <div class="qs-brand-copy">
            <div class="qs-brand-title">QuoteSense</div>
            <div class="qs-brand-sub">
              Procurement intelligence · evidence-backed quotation decisions
            </div>
          </div>
          <div class="qs-product-meta">
            <span class="qs-mini-chip">Structured extraction</span>
            <span class="qs-mini-chip">Deterministic scoring</span>
            <span class="qs-mini-chip">Risk + recommendation</span>
          </div>
          <div class="qs-ready-pill{status_class}">
            <span></span> {status_label}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_hero() -> None:
    st.markdown(
        """
        <div class="qs-hero">
          <div class="qs-hero-copy">
            <div class="qs-kicker">QUOTATION INTELLIGENCE</div>
            <div class="qs-hero-title">
              Turn supplier quotations into a decision.
            </div>
            <div class="qs-hero-sub">
              Extract commercial terms, normalize suppliers, score trade-offs,
              surface risk, and produce an evidence-backed recommendation —
              without hiding the deterministic logic behind the ranking.
            </div>
            <div class="qs-hero-chips">
              <span>Evidence-backed</span>
              <span>Deterministic ranking</span>
              <span>Multi-document</span>
              <span>Human-review friendly</span>
            </div>
          </div>
          <div class="qs-hero-panel">
            <div class="qs-hero-panel-kicker">DECISION FLOW</div>
            <div class="qs-flow-item">
              <span>01</span>
              <div><strong>Extract</strong>
                <small>Terms, prices, timelines, validity</small>
              </div>
            </div>
            <div class="qs-flow-item">
              <span>02</span>
              <div><strong>Score</strong>
                <small>Transparent multi-criteria ranking</small>
              </div>
            </div>
            <div class="qs-flow-item">
              <span>03</span>
              <div><strong>Decide</strong>
                <small>Risks, trade-offs and recommendation</small>
              </div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_pipeline(has_result: bool) -> None:
    states = [
        ("01", "Extract", "Structured terms + source evidence.", True),
        ("02", "Score", "Deterministic multi-criteria ranking.", has_result),
        ("03", "Decide", "Risks, trade-offs + recommendation.", has_result),
    ]

    cols = st.columns(3, gap="medium")

    for col, (num, title, sub, done) in zip(cols, states):
        with col:
            state_class = "done" if done else "pending"
            icon = "✓" if done else "○"

            st.markdown(
                f"""
                <div class="qs-step {state_class}">
                  <div class="qs-step-head">
                    <span class="qs-step-num">{num}</span>
                    <strong>{title}</strong>
                    <span class="qs-step-state">{icon}</span>
                  </div>
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
        <div class="qs-ready-grid">
          <div class="qs-ready-card main">
            <div class="qs-empty-kicker">READY TO ANALYZE</div>
            <div class="qs-empty-title">
              Bring the quotations. Keep the decision logic visible.
            </div>
            <div class="qs-empty-copy">
              Upload supplier files, choose the criteria that matter,
              and QuoteSense will turn unstructured quotations into a
              transparent procurement comparison.
            </div>
            <div class="qs-empty-actions">
              <span>Upload</span><span>→</span>
              <span>Extract</span><span>→</span>
              <span>Score</span><span>→</span>
              <span>Recommend</span>
            </div>
          </div>
          <div class="qs-ready-card">
            <div class="qs-card-kicker">WHAT YOU GET</div>
            <strong>Comparable supplier terms</strong>
            <small>
              Cost, timeline, validity and key commercial features in one view.
            </small>
          </div>
          <div class="qs-ready-card">
            <div class="qs-card-kicker">WHY IT MATTERS</div>
            <strong>Risk before commitment</strong>
            <small>
              Validation gaps and supplier-specific risks are surfaced
              before the recommendation.
            </small>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_workspace_status(
    uploaded: list | None,
    result: dict | None,
    criteria_count: int,
) -> None:
    file_count = len(uploaded or [])
    analyzed = len((result or {}).get("quotations", []) or [])

    if result:
        status = "Analysis complete"
        status_tone = "complete"
        primary_count = analyzed
        secondary = "recommendation ready"
    elif file_count:
        status = "Ready to analyze"
        status_tone = "ready"
        primary_count = file_count
        secondary = "files ready"
    else:
        status = "Awaiting quotations"
        status_tone = "waiting"
        primary_count = 0
        secondary = "not analyzed yet"

    st.markdown(
        f"""
        <div class="qs-workspace-strip {status_tone}">
          <div>
            <span class="qs-status-dot"></span>
            <strong>{status}</strong>
          </div>
          <span>{primary_count} quotation(s)</span>
          <span>{secondary}</span>
          <span>{criteria_count} criteria</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_summary_metrics(result: dict) -> None:
    quotes = result.get("quotations", []) or []
    scores = result.get("scores", []) or []
    validation = result.get("validation", []) or []

    if isinstance(validation, dict):
        validation = validation.get("validation", []) or []

    completeness_scores = [
        score
        for item in validation
        if isinstance(item, dict)
        for score in [_safe_score(item.get("completeness_score"))]
        if score is not None and 0 <= score <= 100
    ]
    avg = (
        sum(completeness_scores) / len(completeness_scores)
        if completeness_scores
        else None
    )

    best = _top_score(scores)

    best_score = _safe_score(
        best.get("score") if best else None
    )

    best_label = (
        f"{best_score:.1f}/100"
        if best_score is not None
        else "N/A"
    )

    # The supplier shown under the deterministic score must be the
    # supplier that actually owns that score, not the qualitative winner.
    best_supplier = (
        str(best.get("supplier") or "Unknown")
        if best
        else "No ranked supplier"
    )

    cards = [
        (
            str(len(quotes)),
            "Quotations",
            "Documents analyzed",
            "neutral",
        ),
        (
            str(len(result.get("documents", []) or [])),
            "Documents",
            "Source files",
            "neutral",
        ),
        (
            f"{avg:.1f}%" if avg is not None else "N/A",
            "Completeness",
            "Average extracted coverage",
            "good" if avg is not None and avg >= 85 else "warn",
        ),
        (
            best_label,
            "Top deterministic score",
            best_supplier,
            "good" if best else "neutral",
        ),
    ]

    cols = st.columns(4, gap="small")

    for col, (value, label, sub, tone) in zip(cols, cards):
        with col:
            st.markdown(
                f"""
                <div class="qs-metric {tone}">
                  <div class="qs-metric-value">{value}</div>
                  <div class="qs-metric-label">{label}</div>
                  <div class="qs-metric-sub">
                    {html.escape(str(sub))}
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _render_supplier_snapshot(result: dict) -> None:
    scores = result.get("scores", []) or []
    quotes = result.get("quotations", []) or []

    if not scores and not quotes:
        return

    quote_map = {
        _supplier_name(quote): quote
        for quote in quotes
    }

    rows = []

    for rank, item in enumerate(scores or [], start=1):
        supplier = str(item.get("supplier") or "Unknown")
        quote = quote_map.get(supplier, {})
        score = _safe_score(item.get("score"))

        rows.append(
            {
                "#": rank,
                "Supplier": supplier,
                "Score": (
                    round(score, 1)
                    if score is not None
                    else "Not scored"
                ),
                "Cost": money(
                    quote.get("total_cost"),
                    quote.get("currency"),
                ),
                "Timeline": quote.get("delivery_timeline") or "—",
                "Validity": quote.get("validity_period") or "—",
            }
        )

    if not rows:
        return

    st.markdown(
        '<div class="qs-section-kicker">SUPPLIER COMPARISON</div>',
        unsafe_allow_html=True,
    )

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )

    cost_issue = next(
        (
            item
            for item in scores
            if item.get("cost_comparable") is False
        ),
        None,
    )

    if cost_issue:
        reason = cost_issue.get(
            "cost_comparability_reason",
            "Supplier prices cannot currently be compared reliably.",
        )

        st.info(
            f"Price component excluded from scoring: {reason} "
            "Overall scores use the remaining available criteria."
        )


def _evidence_confidence(result: dict) -> tuple[str, str]:
    """Estimate extraction confidence from validated field coverage only."""
    quotes = result.get("quotations", []) or []
    validation = result.get("validation", []) or []

    if isinstance(validation, dict):
        validation = validation.get("validation", []) or []

    validation = [item for item in validation if isinstance(item, dict)]

    if not quotes:
        return "Low", "No quotations are available for evidence assessment."

    if not validation:
        return "Low", "Extraction validation data is unavailable."

    if len(validation) < len(quotes):
        return (
            "Low",
            f"Extraction validation covers {len(validation)} of {len(quotes)} quotations.",
        )

    completeness_scores = [
        score
        for item in validation
        for score in [_safe_score(item.get("completeness_score"))]
        if score is not None and 0 <= score <= 100
    ]

    if len(completeness_scores) < len(quotes):
        return "Low", "One or more quotations have no valid completeness score."

    missing_count = 0
    for item in validation:
        missing_fields = item.get("missing_fields") or []
        if isinstance(missing_fields, str):
            missing_fields = [missing_fields]
        if isinstance(missing_fields, (list, tuple, set)):
            missing_count += sum(
                1
                for field in missing_fields
                if field is not None and str(field).strip()
            )

    average_completeness = sum(completeness_scores) / len(completeness_scores)

    if len(quotes) >= 3 and average_completeness >= 90 and missing_count <= 2:
        return (
            "High",
            "Three or more quotations have strong validated field coverage.",
        )

    if len(quotes) >= 2 and average_completeness >= 80 and missing_count <= 5:
        return (
            "High",
            "All quotations have good validated field coverage.",
        )

    if average_completeness >= 80 and missing_count <= 4:
        return (
            "Moderate",
            "Extracted fields are reasonably complete, but the comparison set is limited.",
        )

    return (
        "Low",
        "Material quotation fields are missing or extracted coverage is limited.",
    )


def _render_decision_cockpit(result: dict) -> None:
    scores = result.get("scores", []) or []
    quotes = result.get("quotations", []) or []
    risks = result.get("risks", []) or []

    rec = (
        (result.get("recommendation", {}) or {})
        .get("recommendations", {})
        or {}
    )

    primary = rec.get("primary_recommendation", {}) or {}
    best = _top_score(scores)

    deterministic_supplier = str(
        (best or {}).get("supplier") or "No scored supplier"
    )

    qualitative_supplier = str(
        primary.get("supplier") or ""
    ).strip()

    recommendation_differs = bool(
        qualitative_supplier
        and best
        and qualitative_supplier.casefold()
        != deterministic_supplier.casefold()
    )

    if qualitative_supplier:
        supplier = qualitative_supplier

        supplier_heading = (
            "QUALITATIVE RECOMMENDATION"
            if recommendation_differs
            else "RECOMMENDED SUPPLIER"
        )
    elif best:
        supplier = deterministic_supplier
        supplier_heading = "TOP DETERMINISTIC RANKING"
    else:
        supplier = "No recommendation"
        supplier_heading = "RECOMMENDATION STATUS"

    score = _safe_score(
        (best or {}).get("score")
    )

    if primary.get("reason"):
        reason = str(primary["reason"])
    elif best:
        reason = (
            "This supplier has the highest deterministic score "
            "based on the available configured criteria."
        )
    else:
        reason = "No supplier recommendation was returned."

    confidence, confidence_reason = _evidence_confidence(result)

    risk_count = count_risk_findings(risks)

    score_label = (
        f"{score:.1f} / 100"
        if score is not None
        else "Not scored"
    )

    score_tone = (
        "good"
        if score is not None and score >= 85
        else (
            "warn"
            if score is not None and score >= 70
            else "neutral"
        )
    )

    confidence_class = (
        "good"
        if confidence == "High"
        else (
            "warn"
            if confidence == "Moderate"
            else "danger"
        )
    )

    components = []

    if best:
        component_map = [
            ("Cost", best.get("cost_score")),
            ("Completeness", best.get("completeness_score")),
            ("Timeline", best.get("timeline_score")),
            ("Terms", best.get("terms_score")),
            ("Risk", best.get("risk_score")),
        ]

        for label, value in component_map:
            val = _safe_score(value)

            if val is not None:
                components.append((label, val))

    strong = sorted(
        components,
        key=lambda item: item[1],
        reverse=True,
    )[:3]

    strengths_html = "".join(
        (
            f'<span class="qs-reason-chip">'
            f'<span>✓</span>{html.escape(label)} {value:.0f}'
            f'</span>'
        )
        for label, value in strong
    )

    risk_html = (
        '<span class="qs-risk-count">'
        '✓ No material risks surfaced'
        '</span>'
        if not risk_count
        else (
            '<span class="qs-risk-count danger">'
            f'⚠ {risk_count} risk item(s) require review'
            '</span>'
        )
    )

    st.markdown(
        f"""
        <div class="qs-decision-hero">
          <div class="qs-decision-main">
            <div class="qs-reco-kicker">
              {html.escape(supplier_heading)}
            </div>
            <div class="qs-decision-supplier">
              🥇 {html.escape(supplier)}
            </div>
            <div class="qs-decision-reason">
              {html.escape(reason)}
            </div>
            <div class="qs-strengths-label">
              Deterministic strengths · {html.escape(deterministic_supplier)}
            </div>
            <div class="qs-reason-row">{strengths_html}</div>
          </div>
          <div class="qs-score-panel {score_tone}">
            <div class="qs-score-label">
              TOP DETERMINISTIC SCORE
            </div>
            <div class="qs-score-value">{score_label}</div>
            <div class="qs-score-sub">
              Score belongs to {html.escape(deterministic_supplier)}.
              Calculated from the configured criteria.
            </div>
          </div>
        </div>
        <div class="qs-decision-meta-grid">
          <div class="qs-decision-meta-card {confidence_class}">
            <span>EVIDENCE CONFIDENCE</span>
            <strong>{confidence}</strong>
            <small>{html.escape(confidence_reason)}</small>
          </div>
          <div class="qs-decision-meta-card">
            <span>SUPPLIER SET</span>
            <strong>{len(quotes)}</strong>
            <small>quotation(s) compared</small>
          </div>
          <div class="qs-decision-meta-card {'danger' if risk_count else 'good'}">
            <span>RISK REVIEW</span>
            <strong>{risk_count}</strong>
            <small>
              {'item(s) require review' if risk_count else 'no material risks surfaced'}
            </small>
          </div>
          <div class="qs-decision-meta-card">
            <span>SOURCE COVERAGE</span>
            <strong>{len(result.get('documents', []) or [])}</strong>
            <small>source file(s) analyzed</small>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if recommendation_differs:
        st.warning(
            f"The qualitative recommendation names {supplier}, while "
            f"{deterministic_supplier} has the highest deterministic score "
            f"({score_label}). Review the qualitative rationale and "
            "supplier evidence before making a procurement decision.",
            icon="⚖️",
        )

    st.markdown(
        f'<div class="qs-section-kicker qs-section-spaced">'
        f'SCORING BREAKDOWN — {html.escape(deterministic_supplier)}'
        f'</div>',
        unsafe_allow_html=True,
    )

    weights = (
        (best or {}).get("weights")
        or result.get("weights")
        or {}
    )

    if best and components:
        cols = st.columns(len(components), gap="small")

        for col, (label, value) in zip(cols, components):
            weight = _safe_score(weights.get(label.lower(), 0)) or 0.0

            with col:
                st.markdown(
                    f"""
                    <div class="qs-score-breakdown">
                      <div class="qs-score-breakdown-top">
                        <strong>{html.escape(label)}</strong>
                        <span>{value:.0f}</span>
                      </div>
                      <div class="qs-score-track">
                        <span style="width:{max(0, min(100, value)):.1f}%"></span>
                      </div>
                      <small>
                        {weight * 100:.0f}% weight ·
                        contribution {value * weight:.1f}
                      </small>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown(
        f'<div class="qs-section-kicker qs-section-spaced">'
        f'WHY {html.escape(deterministic_supplier.upper())} '
        f'SCORED HIGHEST'
        f'</div>',
        unsafe_allow_html=True,
    )

    reason_cols = st.columns(3, gap="small")

    for col, (label, value) in zip(reason_cols, strong):
        with col:
            st.markdown(
                f"""
                <div class="qs-why-card">
                  <span>✓</span>
                  <strong>{html.escape(label)}</strong>
                  <small>
                    Deterministic component score: {value:.0f}/100.
                  </small>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if not strong:
        st.caption(
            "The available result does not contain component-level "
            "scoring details."
        )

    st.markdown(
        f'<div class="qs-risk-inline">{risk_html}</div>',
        unsafe_allow_html=True,
    )


def _render_recommendation(result: dict) -> None:
    rec = (
        (result.get("recommendation", {}) or {})
        .get("recommendations", {})
        or {}
    )

    primary = rec.get("primary_recommendation", {}) or {}

    if not primary:
        st.info(
            "No qualitative recommendation was requested or generated."
        )
        return

    supplier = html.escape(
        str(primary.get("supplier") or "Recommended supplier")
    )

    reason = html.escape(
        str(
            primary.get("reason")
            or "Recommendation details are available below."
        )
    )

    st.markdown(
        f"""
        <div class="qs-recommendation-card">
          <div class="qs-reco-kicker">RECOMMENDED OPTION</div>
          <div class="qs-reco-title">{supplier}</div>
          <div class="qs-reco-copy">{reason}</div>
          <div class="qs-reco-foot">
            Evidence-backed qualitative recommendation ·
            numeric ranking remains deterministic
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("Why this supplier?", expanded=True):
        st.json(rec)


def _render_risks(result: dict) -> None:
    # Empty supplier risk records are not actual risk findings.
    risks = [
        risk
        for risk in (result.get("risks") or [])
        if isinstance(risk, dict)
        and count_risk_findings([risk]) > 0
    ]

    validation = result.get("validation", []) or []

    if not risks:
        st.markdown(
            """
            <div class="qs-success-card">
              <span>✓</span>
              <div>
                <strong>No material risks surfaced.</strong>
                <div>
                  Validation data is still available below for inspection.
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        for risk in risks:
            level = str(
                risk.get("level") or "medium"
            ).lower()

            tone = (
                "danger"
                if level in {"critical", "high"}
                else "warn"
            )

            supplier = html.escape(
                str(risk.get("supplier") or "Supplier")
            )

            level_display = html.escape(level.upper())

            risk_items = risk.get("items") or []

            if isinstance(risk_items, str):
                risk_items = [risk_items]

            items = "".join(
                f"<li>{html.escape(str(item))}</li>"
                for item in risk_items
                if item is not None and str(item).strip()
            )

            if not items:
                continue

            st.markdown(
                f"""
                <div class="qs-risk-card {tone}">
                  <div class="qs-risk-top">
                    <strong>{supplier}</strong>
                    <span>{level_display}</span>
                  </div>
                  <ul>{items}</ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if isinstance(validation, dict):
        validation = validation.get("validation", []) or []

    if validation:
        st.markdown(
            '<div class="qs-section-kicker qs-section-spaced">'
            'VALIDATION</div>',
            unsafe_allow_html=True,
        )

        st.dataframe(
            pd.DataFrame(validation),
            use_container_width=True,
            hide_index=True,
        )


def _render_evidence(result: dict) -> None:
    evidence = result.get("evidence", []) or []

    if not evidence:
        st.info(
            "No evidence records were returned for this analysis."
        )
        return

    for item in evidence:
        location = item.get("location", "Source")
        source = item.get("source", "Evidence")

        with st.expander(
            f"{location} · {source}",
            expanded=False,
        ):
            st.markdown(item.get("text", ""))


def _render_export_center(result: dict) -> None:
    st.markdown(
        '<div class="qs-section-kicker qs-section-spaced">'
        'EXPORT ANALYSIS'
        '</div>',
        unsafe_allow_html=True,
    )

    st.caption(
        "Download the extracted supplier data, deterministic scoring, "
        "validation results and risk findings."
    )

    excel_col, csv_col, json_col = st.columns(3, gap="small")

    with excel_col:
        st.download_button(
            "Excel workbook",
            data=analysis_xlsx(result),
            file_name="quotesense-analysis.xlsx",
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "spreadsheetml.sheet"
            ),
            icon=":material/table_view:",
            use_container_width=True,
            key="qs-export-excel",
        )

    with csv_col:
        st.download_button(
            "Supplier CSV",
            data=quotations_csv(result),
            file_name="quotesense-suppliers.csv",
            mime="text/csv",
            icon=":material/csv:",
            use_container_width=True,
            key="qs-export-csv",
        )

    with json_col:
        st.download_button(
            "Full analysis JSON",
            data=analysis_json(result),
            file_name="quotesense-analysis.json",
            mime="application/json",
            icon=":material/data_object:",
            use_container_width=True,
            key="qs-export-json",
        )


def main():
    agent = get_agent(portfolio_token)

    _render_header(
        agent,
        session_active,
        gateway_mode,
        session_provider,
        session_model,
    )

    _render_hero()

    with st.sidebar:
        st.markdown(
            '<div class="qs-sidebar-brand">'
            '<span class="qs-sidebar-mark">$</span>'
            '<div><strong>QUOTESENSE</strong>'
            '<small>PROCUREMENT INTELLIGENCE</small></div>'
            '</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="qs-sidebar-title">Decision workspace</div>',
            unsafe_allow_html=True,
        )

        session_chip = (
            "<span>Session · active</span>"
            if session_active
            else (
                "<span>Session · required</span>"
                if gateway_mode
                else ""
            )
        )

        st.markdown(
            f'<div class="qs-meta-chips">'
            f'<span>Provider · {session_provider or agent.llm.provider}</span>'
            f'<span>Model · {session_model or agent.llm.model}</span>'
            f'{session_chip}</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="qs-sidebar-note">'
            'Configure criteria, upload supplier quotations, then run '
            'the transparent scoring pipeline.'
            '</div>',
            unsafe_allow_html=True,
        )

        query = st.text_area(
            "Analysis request",
            (
                "Compare the quotations, explain trade-offs, identify "
                "risks, and recommend the strongest option."
            ),
            height=120,
        )

        criteria = st.multiselect(
            "Criteria",
            [
                "cost",
                "completeness",
                "timeline",
                "terms",
                "risk",
            ],
            [
                "cost",
                "completeness",
                "timeline",
                "terms",
                "risk",
            ],
        )

        run = st.button(
            "🚀 Analyze quotations",
            type="primary",
            use_container_width=True,
            disabled=(gateway_mode and not session_active),
            help=(
                "Launch QuoteSense from the portfolio to start a secure AI session."
                if gateway_mode and not session_active
                else (
                    "Run quotation extraction, scoring, validation "
                    "and recommendation."
                )
            ),
        )

        if gateway_mode and not session_active:
            debug = st.session_state.get("gateway_debug") or {}
            auth_rejected = debug.get("status_code") in {401, 403}

            if portfolio_token or auth_rejected:
                st.error(
                    "The portfolio AI session is invalid or expired. "
                    "Start a fresh AI session in the portfolio and "
                    "launch QuoteSense again."
                )

                if debug:
                    with st.expander(
                        "Debug: gateway response (temporary)",
                        expanded=True,
                    ):
                        st.text_area(
                            "Raw diagnostic (copy this)",
                            value=(
                                f"URL: {debug.get('url')}\n"
                                f"Status: {debug.get('status_code')}\n"
                                f"Server: {debug.get('server', '')}\n"
                                f"Cache-Control: {debug.get('cache_control', '')}\n"
                                f"CF-Cache-Status: {debug.get('cf_cache_status', '')}\n"
                                f"Age: {debug.get('age', '')}\n"
                                f"ETag: {debug.get('etag', '')}\n"
                                f"Body: {debug.get('body')}"
                            ),
                            height=220,
                        )
            else:
                st.warning(
                    "Portfolio AI session required. Launch QuoteSense "
                    "from your portfolio to enable analysis."
                )

            st.link_button(
                "Open portfolio",
                "https://asaifali-portfolio.vercel.app",
                use_container_width=True,
            )

        st.divider()

        st.markdown(
            '<div class="qs-sidebar-kicker">SYSTEM</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            f'<div class="qs-sidebar-health">'
            f'<div><span class="qs-status-dot"></span> '
            f'{"Gateway session active" if session_active else "Local / session ready"}'
            f'</div>'
            f'<small>{session_provider or agent.llm.provider} · '
            f'{session_model or agent.llm.model}</small>'
            f'<small>'
            f'{len(st.session_state.get("result", {}).get("quotations", []) or []) if st.session_state.get("result") else 0} '
            f'analyzed quotations</small>'
            f'</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="qs-sidebar-kicker qs-sidebar-workflow">'
            'WORKFLOW</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="qs-side-step">01 · Extract supplier terms</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="qs-side-step">02 · Score deterministically</div>',
            unsafe_allow_html=True,
        )

        st.markdown(
            '<div class="qs-side-step">'
            '03 · Explain risk + recommendation</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        """
        <div class="qs-upload-head">
          <div>
            <div class="qs-upload-kicker">SUPPLIER INPUT</div>
            <div class="qs-upload-title">
              Drop supplier quotations here
            </div>
            <div class="qs-upload-copy">
              Add one or more source files. QuoteSense will extract terms,
              normalize suppliers, and keep the decision logic inspectable.
            </div>
          </div>
          <div class="qs-upload-badge">
            <span>PDF</span>
            <span>DOCX</span>
            <span>TXT</span>
            <span>XLSX</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    uploaded = st.file_uploader(
        "Supplier quotation files",
        type=[
            extension.lstrip(".")
            for extension in config.SUPPORTED_FORMATS
        ],
        accept_multiple_files=True,
        label_visibility="collapsed",
        help="Upload PDF, DOCX, TXT or XLSX supplier quotation files.",
    )

    _render_workspace_status(
        uploaded,
        st.session_state.get("result"),
        len(criteria),
    )

    result = st.session_state.get("result")

    _render_pipeline(bool(result))

    if not uploaded:
        _render_empty_state(uploaded)

        if result:
            st.info(
                "No documents are currently selected. Showing the "
                "results from the last completed analysis."
            )

            if st.button(
                "Clear previous results",
                icon=":material/delete_sweep:",
            ):
                st.session_state.pop("result", None)
                st.rerun()

    else:
        st.markdown(
            f'<div class="qs-file-state">'
            f'<strong>{len(uploaded)} quotation(s) ready</strong>'
            f'<span>Review the files, then run analysis.</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

        current_files = [
            item.name
            for item in uploaded
        ]

        previous_files = (
            result.get("uploaded_files", [])
            if result
            else []
        )

        if result and current_files != previous_files and not run:
            st.warning(
                "These documents have not been analyzed yet. "
                "Click Analyze quotations to replace the previous result set."
            )

    if run:
        if gateway_mode and not session_active:
            st.warning(
                "Your portfolio AI session is missing or has expired. "
                "Launch QuoteSense from the portfolio and try again."
            )

        elif not uploaded:
            st.warning(
                "Please upload at least one quotation before starting an analysis."
            )

        else:
            paths = []
            metadata = []

            try:
                for item in uploaded:
                    suffix = os.path.splitext(item.name)[1].lower()
                    fd, path = tempfile.mkstemp(suffix=suffix)
                    paths.append(path)

                    try:
                        with os.fdopen(fd, "wb") as tmp:
                            tmp.write(item.getvalue())
                    except Exception:
                        try:
                            os.close(fd)
                        except OSError:
                            pass
                        raise

                    metadata.append(item.name)

                progress = st.progress(
                    0,
                    text="Extracting quotations…",
                )

                with st.spinner(
                    "Running multi-document quotation pipeline…"
                ):
                    progress.progress(
                        35,
                        text="Extracting structured fields…",
                    )

                    result = agent.process_documents(
                        paths,
                        query=query,
                        criteria=criteria,
                    )

                    progress.progress(
                        78,
                        text="Scoring suppliers and validating terms…",
                    )

                    result["uploaded_files"] = metadata
                    st.session_state["result"] = result

                    progress.progress(
                        100,
                        text="Recommendation ready",
                    )

                progress.empty()

                st.toast(
                    "Quotation analysis complete",
                    icon="✅",
                )

            except Exception as exc:
                message = str(exc)
                normalized = message.lower()

                if (
                    "401" in normalized
                    or "unauthorized" in normalized
                    or "demo session" in normalized
                    or "bearer" in normalized
                ):
                    _clear_gateway_session()

                    st.error(
                        "Portfolio AI session expired or is no longer valid. "
                        "Return to the portfolio and launch QuoteSense again "
                        "to start a fresh secure session."
                    )

                    st.link_button(
                        "Return to portfolio",
                        "https://asaifali-portfolio.vercel.app",
                        use_container_width=True,
                    )

                else:
                    st.error(f"Analysis failed: {message}")

            finally:
                cleanup_failed = False
                for path in paths:
                    try:
                        os.unlink(path)
                    except FileNotFoundError:
                        pass
                    except OSError:
                        cleanup_failed = True

                if cleanup_failed:
                    st.warning(
                        "QuoteSense could not remove one or more temporary "
                        "upload files. Please check the app host's temporary "
                        "storage permissions."
                    )

    result = st.session_state.get("result")

    if not result:
        return

    st.markdown(
        '<div class="qs-results-title">Decision cockpit</div>',
        unsafe_allow_html=True,
    )

    _render_summary_metrics(result)
    _render_decision_cockpit(result)
    _render_supplier_snapshot(result)
    _render_export_center(result)

    tabs = st.tabs(
        [
            "Decision Overview",
            "Quotations",
            "Scoring",
            "Risks & Validation",
            "Recommendation",
            "Evidence",
            "Raw",
        ]
    )

    with tabs[0]:
        _render_recommendation(result)

        if result.get("metrics"):
            with st.expander(
                "Execution metrics",
                expanded=False,
            ):
                st.json(result["metrics"])

    with tabs[1]:
        quotes = result.get("quotations", [])

        rows = [
            {
                "Supplier": _supplier_name(quote),
                "Cost": money(
                    quote.get("total_cost"),
                    quote.get("currency"),
                ),
                "Timeline": quote.get("delivery_timeline") or "—",
                "Validity": quote.get("validity_period") or "—",
                "Features": ", ".join(
                    quote.get("key_features", []) or []
                ),
            }
            for quote in quotes
        ]

        if rows:
            st.dataframe(
                pd.DataFrame(rows),
                use_container_width=True,
                hide_index=True,
            )

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
            st.dataframe(
                pd.DataFrame(scores),
                use_container_width=True,
                hide_index=True,
            )

            st.caption(
                "The ranking is deterministic. The LLM does not "
                "directly control the numeric score."
            )
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
