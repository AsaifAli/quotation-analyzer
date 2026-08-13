"""Local launcher for CLI, Streamlit and API."""
import argparse, subprocess, sys

def main():
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=["web","api","cli","test"])
    p.add_argument("--document","-d")
    p.add_argument("--query","-q",default="Compare quotations and recommend the strongest option.")
    p.add_argument("--port","-p",type=int,default=8501)
    a=p.parse_args()
    if a.mode=="web": subprocess.run([sys.executable,"-m","streamlit","run","streamlit_app.py","--server.port",str(a.port)],check=True)
    elif a.mode=="api": subprocess.run([sys.executable,"-m","uvicorn","app:app","--host","0.0.0.0","--port",str(a.port)],check=True)
    elif a.mode=="cli":
        if not a.document: p.error("--document is required for cli")
        subprocess.run([sys.executable,"agent_interface.py","--document",a.document,"--query",a.query],check=True)
    else: subprocess.run([sys.executable,"-m","pytest","-q"],check=True)
if __name__=="__main__": main()
