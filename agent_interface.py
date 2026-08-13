"""CLI entry point retained for portfolio demos."""
import argparse, json
from modules.ai_agent import QuotationIntelligenceAgent

def main():
    p=argparse.ArgumentParser(description="Quotation Intelligence CLI")
    p.add_argument("--document","-d",required=True)
    p.add_argument("--query","-q",default="Compare quotations and recommend the strongest option.")
    args=p.parse_args()
    result=QuotationIntelligenceAgent().process(args.document,args.query)
    print(json.dumps(result,indent=2,default=str))

if __name__=="__main__": main()
