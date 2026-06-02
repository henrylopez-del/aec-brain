"""
Nodo analizador: replica el "9. Analyze Response" de n8n.

Toma la conversacion (historial + ultimo intercambio) y la clasifica en:
  vacio | interes|<resumen> | alerta|<subtipo>: <contexto>
usando el prompt REAL analyzer_prompt de tenant_prompts (agent_key=default).

Devuelve un dict con la DECISION (no ejecuta acciones; eso es Fase B en n8n/GHL):
  {classification, subtype, note, escalate, tags, raw}

Mapeo a tags (segun tag_instructions):
  interes -> ['interesado']   alerta -> ['alerta']   vacio -> []
"""
import os

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

from config import load_prompt_kv

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
ANALYZER_AGENT = os.getenv("ANALYZER_AGENT_KEY", "default")
ANALYZER_PROMPT_KEY = os.getenv("ANALYZER_PROMPT_KEY", "analyzer_prompt")

_FALLBACK = (
    "Eres un clasificador. Lee el historial y responde SOLO una linea: "
    "'vacio', o 'interes|<motivo>', o 'alerta|<subtipo>: <contexto>'."
)

_llm = None
_prompt_cache = None


def _get_llm():
    global _llm
    if _llm is None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        _llm = ChatGoogleGenerativeAI(
            model=MODEL, temperature=0.1, max_output_tokens=80, google_api_key=api_key
        )
    return _llm


def _prompt() -> str:
    global _prompt_cache
    if _prompt_cache is None:
        _prompt_cache = load_prompt_kv(ANALYZER_AGENT, ANALYZER_PROMPT_KEY) or _FALLBACK
    return _prompt_cache


def _format_convo(history: list) -> str:
    lines = []
    for m in history:
        who = "Cliente" if m.get("role") == "user" else "Bot"
        lines.append(f"{who}: {m.get('content', '')}")
    return "HISTORIAL DE CONVERSACION:\n" + "\n".join(lines)


def _empty(raw: str = "vacio") -> dict:
    return {"classification": "vacio", "subtype": None, "note": "",
            "escalate": False, "tags": [], "raw": raw}


def parse(raw: str) -> dict:
    line = (raw or "").strip().splitlines()[0].strip() if raw else "vacio"
    low = line.lower()
    if low.startswith("alerta"):
        cls = "alerta"
    elif low.startswith("interes"):
        cls = "interes"
    else:
        return _empty(line)

    subtype, note = None, ""
    if "|" in line:
        rest = line.split("|", 1)[1].strip()
        if ":" in rest:
            head, after = rest.split(":", 1)
            h = head.strip().lower()
            if h in ("frustrado", "opt_out") or h.startswith("broadcast"):
                subtype, note = h, after.strip()
            else:
                note = rest
        else:
            note = rest

    tags = ["interesado"] if cls == "interes" else ["alerta"]
    return {"classification": cls, "subtype": subtype, "note": note,
            "escalate": True, "tags": tags, "raw": line}


def analyze(history: list, user_message: str = "", bot_reply: str = "") -> dict:
    try:
        convo = _format_convo(history)
        out = _get_llm().invoke(
            [SystemMessage(content=_prompt()), HumanMessage(content=convo)]
        ).content
        return parse(out)
    except Exception as e:
        return _empty(f"[error] {type(e).__name__}")
