"""
Persistencia de la ETAPA del pipeline por conversacion, en Supabase.

Tabla: public.aec_pipeline_state
  session_id (text, PK)  = conversationId (location:contact)
  stage (text)           = etapa actual del pipeline
  data (jsonb)           = datos acumulados del lead (opcional, futuro)
  updated_at (timestamptz)

stdlib (urllib), sin dependencias nuevas. Falla silenciosa: si no hay Supabase
o falla, get_stage devuelve la etapa inicial y el bot sigue.
"""
import os
import json
import urllib.request
import urllib.parse

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TABLE = os.getenv("PIPELINE_STATE_TABLE", "aec_pipeline_state")
DEFAULT_STAGE = "apertura"


def _enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _headers(extra: dict = None) -> dict:
    h = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        h.update(extra)
    return h


def get_stage(session_id: str) -> str:
    if not _enabled() or not session_id:
        return DEFAULT_STAGE
    q = urllib.parse.urlencode({
        "session_id": f"eq.{session_id}",
        "select": "stage",
        "limit": "1",
    })
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{TABLE}?{q}", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            rows = json.load(r)
        if rows and rows[0].get("stage"):
            return rows[0]["stage"]
    except Exception:
        pass
    return DEFAULT_STAGE


def set_stage(session_id: str, stage: str, data: dict = None) -> None:
    if not _enabled() or not session_id:
        return
    payload = {"session_id": session_id, "stage": stage}
    if data is not None:
        payload["data"] = data
    body = json.dumps(payload).encode()
    # upsert por PK session_id
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{TABLE}?on_conflict=session_id",
        data=body,
        headers=_headers({"Prefer": "resolution=merge-duplicates,return=minimal"}),
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=8).read()
    except Exception:
        pass
