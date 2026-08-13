"""Export compact analysis reports without requiring a document-generation service."""
import io, json
import pandas as pd

def quotations_csv(result):
    rows=[]
    for q in result.get("quotations",[]): rows.append({"supplier":q.get("supplier"),"total_cost":q.get("total_cost"),"currency":q.get("currency"),"timeline":q.get("delivery_timeline"),"validity":q.get("validity_period")})
    return pd.DataFrame(rows).to_csv(index=False)

def analysis_json(result): return json.dumps(result,indent=2,default=str)

def analysis_xlsx(result):
    out=io.BytesIO()
    with pd.ExcelWriter(out,engine="openpyxl") as writer:
        pd.DataFrame(result.get("scores",[])).to_excel(writer,index=False,sheet_name="Scores")
        pd.DataFrame(result.get("validation",[])).to_excel(writer,index=False,sheet_name="Validation")
        pd.DataFrame(result.get("risks",[])).to_excel(writer,index=False,sheet_name="Risks")
        pd.DataFrame(result.get("quotations",[])).drop(columns=["evidence"],errors="ignore").to_excel(writer,index=False,sheet_name="Quotations")
    return out.getvalue()
