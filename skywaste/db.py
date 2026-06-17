"""
Slim DBClient for the serverless (Vercel) build.

The full project talks to Supabase. On Vercel we run the optimization engine
in "stateless" mode: there is no persistent DB connection, so `client` is always
None and the engine transparently falls back to its bundled static data
(disposal-cost table, ABP regimes, static airport map). This keeps cold starts
fast and avoids shipping the heavy `supabase` dependency into the function.

If SUPABASE_URL + SUPABASE_SERVICE_KEY are set as Vercel env vars AND the
`supabase` package is installed, a real client is created automatically.
"""
from __future__ import annotations

import os
from typing import Any, Optional


class DBClient:
    def __init__(self) -> None:
        self.supabase_url: Optional[str] = os.getenv("SUPABASE_URL") or None
        self.supabase_key: Optional[str] = os.getenv("SUPABASE_SERVICE_KEY") or None
        self.client: Optional[Any] = None

        # Only attempt a real connection if both creds AND the package exist.
        if self.supabase_url and self.supabase_key:
            try:
                from supabase import create_client  # type: ignore

                self.client = create_client(self.supabase_url, self.supabase_key)
            except Exception:
                # Missing package or bad creds → stay in stateless mode.
                self.client = None

    def get_conn_pool_string(self) -> str:
        return os.getenv("SUPABASE_DB_URL") or os.getenv("DATABASE_URL", "")
