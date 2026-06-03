"""
Carga el system prompt desde Supabase (tabla tenant_prompts), igual que el
flujo n8n. Asi el prompt vive en UN solo lugar y el equipo lo edita sin tocar
codigo ni redeploy (basta reiniciar el servicio para refrescar el cache).

Config por env:
  LOCATION_ID   - location del tenant (ej. V3iaVn0uBrQYxtNHPBeb = TVS)
  AGENT_KEY     - cual agente (tvs_ventas | motofusion_taller | servicio | default)
  PROMPT_KEY    - default 'system_prompt'
  PROMPTS_TABLE - default 'tenant_prompts'

Si no hay config o falla, devuelve None y el cerebro cae al prompt generico.
"""
import os
import json
import urllib.request
import urllib.parse

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
LOCATION_ID = os.getenv("LOCATION_ID", "")
AGENT_KEY = os.getenv("AGENT_KEY", "tvs_ventas")
PROMPT_KEY = os.getenv("PROMPT_KEY", "system_prompt")
PROMPTS_TABLE = os.getenv("PROMPTS_TABLE", "tenant_prompts")


def load_prompt_kv(agent_key: str, prompt_key: str, location_id: str = None) -> str | None:
    """Lee cualquier prompt de tenant_prompts por (location, agent_key, prompt_key).

    location_id por parametro = multi-tenant (varias empresas en el mismo brain).
    Si no se pasa, cae al env LOCATION_ID (comportamiento original, TVS)."""
    loc = location_id or LOCATION_ID
    if not (SUPABASE_URL and SUPABASE_KEY and loc):
        return None
    q = urllib.parse.urlencode({
        "location_id": f"eq.{loc}",
        "agent_key": f"eq.{agent_key}",
        "prompt_key": f"eq.{prompt_key}",
        "select": "content",
        "limit": "1",
    })
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    }
    req = urllib.request.Request(f"{SUPABASE_URL}/rest/v1/{PROMPTS_TABLE}?{q}", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            rows = json.load(r)
        if rows and rows[0].get("content"):
            return rows[0]["content"]
    except Exception:
        pass
    return None


def load_prompt() -> str | None:
    """El system prompt del agente activo (AGENT_KEY)."""
    return load_prompt_kv(AGENT_KEY, PROMPT_KEY)


def load_stage_prompt(location_id: str, stage: str) -> str | None:
    """Prompt de una etapa del pipeline (agent_key='pipeline', prompt_key='stage_<x>')."""
    return load_prompt_kv("pipeline", f"stage_{stage}", location_id=location_id)


def load_company_context(location_id: str) -> str | None:
    """Capa 1: contexto de empresa (siempre presente). Comun a todas las etapas."""
    return load_prompt_kv("default", "company_context", location_id=location_id)
