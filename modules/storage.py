"""Tiny SQLite audit store; no external database is required for the portfolio demo."""
import json, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
DB_PATH=Path(__file__).resolve().parent.parent / "data" / "history.db"

def init_db():
    DB_PATH.parent.mkdir(parents=True,exist_ok=True)
    with sqlite3.connect(DB_PATH) as db:
        db.execute("CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, created_at TEXT, provider TEXT, model TEXT, document_count INTEGER, quotation_count INTEGER, result_json TEXT)")

def save_analysis(result):
    init_db(); analysis_id=str(uuid.uuid4()); now=datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as db: db.execute("INSERT INTO analyses VALUES (?,?,?,?,?,?,?)",(analysis_id,now,result.get("provider"),result.get("model"),len(result.get("documents",[])),len(result.get("quotations",[])),json.dumps(result,default=str)))
    return analysis_id

def list_analyses(limit=20):
    init_db()
    with sqlite3.connect(DB_PATH) as db: rows=db.execute("SELECT id,created_at,provider,model,document_count,quotation_count FROM analyses ORDER BY created_at DESC LIMIT ?",(limit,)).fetchall()
    return [{"id":r[0],"created_at":r[1],"provider":r[2],"model":r[3],"document_count":r[4],"quotation_count":r[5]} for r in rows]

def get_analysis(analysis_id):
    init_db()
    with sqlite3.connect(DB_PATH) as db: row=db.execute("SELECT result_json FROM analyses WHERE id=?",(analysis_id,)).fetchone()
    return json.loads(row[0]) if row else None
