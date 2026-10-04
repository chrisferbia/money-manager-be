"""Local UI verification server with fictional, in-memory data only.

Run from the backend root: python tests/manual/import_preview.py
Never use this test adapter as a deployed Worker entrypoint.
"""
from pathlib import Path
import sys

import uvicorn
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from app import app
from auth import require_workspace
from fake_d1 import FakeD1, InProcessApp


async def preview_workspace(request: Request):
    request.state.workspace_id = 1
    return 1


database = FakeD1((ROOT / "db_init.sql").read_text())
database.reset()
database.connection.executescript("""
    INSERT INTO accounts (id,workspace_id,name,type) VALUES (1,1,'BCA','bank');
    INSERT INTO categories (id,workspace_id,name,type) VALUES (1,1,'Food','expense'),(2,1,'Shopping','expense'),(3,1,'Salary','income'),(4,1,'Other','expense');
""")
app.dependency_overrides[require_workspace] = preview_workspace


@app.get("/runtime-config.json")
async def runtime_config():
    return {"apiBaseUrl": "http://127.0.0.1:8791"}


if __name__ == "__main__":
    preview = CORSMiddleware(InProcessApp(app, database), allow_origins=["http://127.0.0.1:5179"], allow_methods=["*"], allow_headers=["*"])
    uvicorn.run(preview, host="127.0.0.1", port=8791)
