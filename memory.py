"""
Memoria de conversacion en Supabase, usando la tabla EXISTENTE del flujo de
pruebas: public.n8n_chat_histories_pruebas (formato n8n / LangChain).

Esquema: session_id (varchar) + message (jsonb). El jsonb es el mensaje
serializado de LangChain: {"type":"human"|"ai","content":"..."}.
Usar esta tabla = la memoria queda compartida con el flujo n8n; no duplicamos.

Hecha con stdlib (urllib) a proposito: NO agrega dependencias al build.
Falla silenciosa: si Supabase no esta seteado o falla, el bot sigue
respondiendo, solo sin memoria.
"""
import os
import json
import urllib.request
import urllib.parse

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
TABLE = os.getenv("MEMORY_TABLE", "n8n_chat_histories_pruebas")
HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "12"))  # ultimos N mensajes de contexto


def memory_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def _headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def fetch_history(conversation_id: str, limit: int = None) -> list:
    """Devuelve [{role, content}, ...] en orden cronologico (role: user|assistant)."""
    if not memory_enabled() or not conversation_id:
        return []
    limit = limit or HISTORY_LIMIT
    q = urllib.parse.urlencode({
        "session_id": f"eq.{conversation_id}",
        "select": "message",
        "order": "id.desc",
        "limit": str(limit),
    })
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{TABLE}?{q}", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            rows = json.load(r)
    except Exception:
        return []
    out = []
    for row in reversed(rows):  # id.desc -> reverse a cronologico
        m = row.get("message") or {}
        t = m.get("type")
        c = m.get("content", "")
        if t in ("human", "ai") and c:
            out.append({"role": "user" if t == "human" else "assistant", "content": c})
    return out


def _msg_json(role: str, content: str) -> dict:
    """Construye el jsonb en el formato LangChain que ya usa la tabla."""
    if role == "user":
        return {
            "type": "human",
            "content": content,
            "additional_kwargs": {},
            "response_metadata": {},
        }
    return {
        "type": "ai",
        "content": content,
        "tool_calls": [],
        "additional_kwargs": {},
        "response_metadata": {},
        "invalid_tool_calls": [],
    }


def append_messages(conversation_id: str, pairs: list) -> None:
    """pairs: [(role, content), ...]. Persiste el turno (user + assistant)."""
    if not memory_enabled() or not conversation_id:
        return
    payload = [
        {"session_id": conversation_id, "message": _msg_json(role, content)}
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
