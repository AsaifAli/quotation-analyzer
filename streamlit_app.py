"""Portfolio-ready Streamlit dashboard for quotation intelligence."""
import json, os, tempfile
import pandas as pd
import streamlit as st
import plotly.express as px
from modules.ai_agent import QuotationIntelligenceAgent
import config

st.set_page_config(page_title="Quotation Intelligence", page_icon="📑", layout="wide")

@st.cache_resource
def get_agent():
    return QuotationIntelligenceAgent()

def money(v, currency=""):
    try: return f"{currency or ''} {float(v):,.2f}".strip()
    except (TypeError, ValueError): return "N/A"

def main():
    st.title("📑 Quotation Intelligence Platform")
    st.caption("Extract → validate → score → compare → risk-assess → recommend")
    with st.sidebar:
        st.subheader("Analysis configuration")
        agent=get_agent()
        st.write(f"**Provider:** `{agent.llm.provider}`")
        st.write(f"**Model:** `{agent.llm.model}`")
        query=st.text_area("Analysis request", "Compare the quotations, explain trade-offs, identify risks, and recommend the strongest option.")
        criteria=st.multiselect("Criteria", ["cost","completeness","timeline","terms","risk"], ["cost","completeness","timeline","terms","risk"])
        run=st.button("🚀 Analyze quotations", type="primary", use_container_width=True)
    uploaded=st.file_uploader(
        "Upload one or more supplier quotations",
        type=[x.lstrip('.') for x in config.SUPPORTED_FORMATS],
        accept_multiple_files=True,
    )

    result=st.session_state.get("result")

    if not uploaded:
        st.markdown("### Portfolio demo")
        st.markdown(
            "- Multi-document ingestion · structured extraction · deterministic scoring · "
            "evidence · risk detection · human-review recommendation"
        )
        if result:
            st.info(
                "No documents are currently selected. Showing the results from the "
                "last completed analysis."
            )
            if st.button("🗑️ Clear previous results"):
                st.session_state.pop("result", None)
                st.rerun()
    else:
        st.success(f"Loaded **{len(uploaded)} document(s)**")
        current_files = [item.name for item in uploaded]
        previous_files = result.get("uploaded_files", []) if result else []
        if result and current_files != previous_files and not run:
            st.warning(
                "These documents have not been analyzed yet. The results below are "
                "from the previous completed analysis. Click **Analyze quotations** "
                "to replace them."
            )

    if run:
        if not uploaded:
            st.warning("Please upload at least one quotation before starting an analysis.")
        else:
            paths=[]; metadata=[]
            try:
                for item in uploaded:
                    suffix=os.path.splitext(item.name)[1].lower()
                    fd,path=tempfile.mkstemp(suffix=suffix)
                    with os.fdopen(fd,"wb") as tmp:
                        tmp.write(item.getvalue())
                    paths.append(path)
                    metadata.append(item.name)
                with st.spinner("Running multi-document quotation pipeline..."):
                    result=agent.process_documents(paths, query=query, criteria=criteria)
                result["uploaded_files"]=metadata
                st.session_state["result"]=result
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")
            finally:
                for path in paths:
                    if os.path.exists(path):
                        os.unlink(path)

    result=st.session_state.get("result")
    if not result: return
    quotes=result.get("quotations",[]); scores=result.get("scores",[]); validation=result.get("validation",[])
    tabs=st.tabs(["📊 Overview","📋 Quotations","🏆 Scoring","⚠️ Risks & Validation","🧠 Recommendation","🔎 Evidence","🛠️ Raw"])
    with tabs[0]:
        c1,c2,c3,c4=st.columns(4)
        c1.metric("Quotations",len(quotes)); c2.metric("Documents",len(result.get("documents",[])))
        avg=sum(x["completeness_score"] for x in validation)/len(validation) if validation else 0
        c3.metric("Avg completeness",f"{avg:.1f}%"); best=scores[0] if scores else None
        c4.metric("Top score",f"{best['score']:.1f}/100" if best and best.get("score") is not None else "N/A")
        if scores:
            df=pd.DataFrame([{"Supplier":x["supplier"],"Score":x["score"] or 0} for x in scores])
            st.plotly_chart(px.bar(df,x="Supplier",y="Score",range_y=[0,100],title="Deterministic procurement score"),use_container_width=True)
        if result.get("metrics"): st.json(result["metrics"])
    with tabs[1]:
        rows=[{"Supplier":q.get("supplier"),"Cost":money(q.get("total_cost"),q.get("currency")),"Timeline":q.get("delivery_timeline"),"Validity":q.get("validity_period"),"Features":", ".join(q.get("key_features",[]) or [])} for q in quotes]
        st.dataframe(pd.DataFrame(rows),use_container_width=True)
        st.download_button("Download extracted quotations",json.dumps(quotes,indent=2),"quotations.json","application/json")
    with tabs[2]:
        st.dataframe(pd.DataFrame(scores),use_container_width=True)
        st.caption("The ranking is deterministic. The LLM does not directly control the numeric score.")
    with tabs[3]:
        if result.get("risks"):
            for r in result["risks"]: st.warning(f"**{r['supplier']} — {r['level'].upper()}**\n\n"+"\n".join(f"- {x}" for x in r.get("items",[])))
        st.dataframe(pd.DataFrame(validation),use_container_width=True)
    with tabs[4]:
        analysis=result.get("analysis",{}).get("analysis",{})
        rec=result.get("recommendation",{}).get("recommendations",{})
        if analysis: st.json(analysis)
        if rec:
            primary=rec.get("primary_recommendation",{})
            st.success(f"Primary recommendation: **{primary.get('supplier','N/A')}**")
            st.write(primary.get("reason","")); st.json(rec)
        else: st.info("No qualitative recommendation was requested/generated.")
    with tabs[5]:
        for item in result.get("evidence",[]):
            with st.expander(f"{item['location']} — {item['source']}"): st.write(item.get("text",""))
    with tabs[6]: st.json(result)

if __name__ == "__main__": main()
