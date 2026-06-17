"""
Local development server — NOT used by Vercel.

On Vercel, the static site in /public and the /api/* serverless function are
served on the same origin automatically. To reproduce that locally on a single
port (so the frontend's same-origin `/api/...` calls just work), this script
mounts /public as static files on top of the FastAPI app.

    python dev_server.py            # → http://127.0.0.1:8000

Vercel ignores this file: only files under /api become functions, and /public
is served as the static root.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "api"))

import uvicorn
from fastapi.staticfiles import StaticFiles

from index import app  # the FastAPI app from api/index.py

PUBLIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "public")
app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="static")

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="127.0.0.1", port=port)
