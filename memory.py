"""
Memoria de conversacion persistida en Supabase (tabla public.aec_chat_memory).

Hecha con stdlib (urllib) a proposito: NO agrega dependencias al build.
Lee/escribe via PostgREST con la service role key. Falla silenciosa: si Supabase
no esta configurado o falla, el bot sigue respondiendo, solo sin memoria.
"""
import os
import json
import urllib.request
import urllib.parse

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TABLE = "aec_chat_memory"
HISTORY_LIMIT = 12  # ultimos N mensajes que se le dan de contexto al modelo


def memory_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def fetch_history(conversation_id: str, limit: int = HISTORY_LIMIT) -> list:
    """Devuelve [{role, content}, ...] en orden cronologico."""
    if not memory_enabled() or not conversation_id:
        return []
    q = urllib.parse.urlencode({
        "conversation_id": f"eq.{conversation_id}",
        "select": "role,content",
        "order": "created_at.desc",
        "limit": str(limit),
    })
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{TABLE}?{q}", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            rows = json.load(r)
        return list(reversed(rows))
    except Exception:
        return []


def append_messages(conversation_id: str, pairs: list) -> None:
    """pairs: [(role, content), ...]. Persiste el turno (user + assistant)."""
    if not memory_enabled() or not conversation_id:
        return
    payload = [
        {"conversation_id": conversation_id, "role": role, "content": content}
        for role, content in pairs
    ]
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{TABLE}", data=data, headers=_headers(), method="POST"
    )
    try:
        urllib.request.urlopen(req, timeout=8).read()
    except Exception:
        pass
