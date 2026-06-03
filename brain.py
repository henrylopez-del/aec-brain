"""
Cerebro AEC (prueba) - LangGraph minimo.

Alcance de la prueba: recibe un mensaje, responde, devuelve texto.
Sin escalacion, sin follow-up, sin guard TVS (eso es produccion).

El grafo arranca con un solo nodo (responder). Esta hecho asi a proposito
para que crezca: cuando se sume routing, sub-agentes o guard, se agregan
nodos sin reescribir nada.

El LLM se construye perezoso (en el primer uso), NO al importar, para que el
servicio arranque aunque falte la GEMINI_API_KEY. Asi /health vive siempre y
/respond avisa claro si falta la key, en vez de tumbar el deploy.
"""
import os
from typing import TypedDict

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from memory import fetch_history, append_messages
from config import load_prompt, load_stage_prompt, load_company_context
from analyzer import analyze
import pipeline
import pipeline_state

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

# Locations que usan el PIPELINE DE VENTAS estructurado (por etapas).
# El resto (TVS) sigue con el prompt unico de siempre. Coma-separado.
PIPELINE_LOCATIONS = set(
    x.strip() for x in os.getenv("PIPELINE_LOCATIONS", "").split(",") if x.strip()
)


def _location_of(conversation_id: str) -> str:
    """conversationId = 'location:contact' -> location."""
    return conversation_id.split(":", 1)[0] if ":" in conversation_id else ""


def as_text(content) -> str:
    """Gemini puede devolver .content como string o como lista de partes
    ([{'type':'text','text':...}, ...]). Normaliza a string plano."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for p in content:
            if isinstance(p, dict):
                out.append(p.get("text") or p.get("content") or "")
            else:
                out.append(str(p))
        return "".join(out).strip()
    return str(content or "")

# Fallback si no hay prompt en Supabase ni env var.
DEFAULT_PROMPT = (
    "Eres un asistente de atencion al cliente por WhatsApp. "
    "Responde claro, breve y en espanol. Si no tienes un dato, dilo, no lo inventes."
)

# Prioridad del prompt: 1) Supabase tenant_prompts (como n8n) 2) env SYSTEM_PROMPT
# 3) generico. Se cachea al primer uso; reiniciar el servicio lo refresca.
_SYSTEM_PROMPT_CACHE = None


def _system_prompt() -> str:
    global _SYSTEM_PROMPT_CACHE
    if _SYSTEM_PROMPT_CACHE is None:
        _SYSTEM_PROMPT_CACHE = load_prompt() or os.getenv("SYSTEM_PROMPT", DEFAULT_PROMPT)
    return _SYSTEM_PROMPT_CACHE


class State(TypedDict):
    user_message: str
    conversation_id: str
    reply: str
    analysis: dict
    stage: str
    next_stage: str


_llm = None  # lazy singleton


def _get_llm():
    global _llm
    if _llm is None:
        api_key = os.getenv("GEMINI_API_KEY", "").strip()
        if not api_key or api_key == "PENDIENTE":
            raise RuntimeError("Falta GEMINI_API_KEY (setearla en Render).")
        # Pasamos la key explicita: la libreria por default busca GOOGLE_API_KEY
        # o credenciales de Google Cloud, no nuestra GEMINI_API_KEY.
        _llm = ChatGoogleGenerativeAI(
            model=MODEL,
            temperature=0,
            max_output_tokens=600,
            google_api_key=api_key,
        )
    return _llm


def _system_for(conv: str, location: str):
    """Devuelve (system_text, stage). En modo pipeline: company_context + prompt de
    la etapa actual. Si no, el prompt unico de siempre (TVS)."""
    if location in PIPELINE_LOCATIONS:
        stage = pipeline_state.get_stage(conv)
        company = load_company_context(location) or ""
        stage_p = load_stage_prompt(location, stage) or ""
        objetivo = pipeline.stage_goal(stage)
        sys = (
            (company + "\n\n" if company else "")
            + f"# ETAPA ACTUAL DEL PIPELINE: {stage}\n"
            + (f"Objetivo de esta etapa: {objetivo}\n\n" if objetivo else "\n")
            + (stage_p or _system_prompt())
        )
        return sys, stage
    return _system_prompt(), None


def respond_node(state: State) -> dict:
    llm = _get_llm()
    conv = state.get("conversation_id", "")
    user_msg = state["user_message"]
    location = _location_of(conv)

    system_text, stage = _system_for(conv, location)

    # Memoria: arma el contexto con el historial previo de esta conversacion.
    history = fetch_history(conv)
    messages = [SystemMessage(content=system_text)]
    for m in history:
        if m.get("role") == "user":
            messages.append(HumanMessage(content=m.get("content", "")))
        else:
            messages.append(AIMessage(content=m.get("content", "")))
    messages.append(HumanMessage(content=user_msg))

    out = llm.invoke(messages)
    reply = as_text(out.content)

    # Persiste el turno para que el proximo mensaje lo recuerde.
    append_messages(conv, [("user", user_msg), ("assistant", reply)])

    # GATE del pipeline: solo en modo pipeline, decide si avanza de etapa.
    new_stage = stage
    if stage is not None:
        if pipeline.decide_advance(llm, history, user_msg, reply, stage):
            new_stage = pipeline.next_stage(stage)
        pipeline_state.set_stage(conv, new_stage)

    return {"reply": reply, "stage": stage, "next_stage": new_stage}


def analyze_node(state: State) -> dict:
    # Re-lee el historial (ya incluye el turno recien persistido) y clasifica.
    conv = state.get("conversation_id", "")
    history = fetch_history(conv)
    result = analyze(history, state["user_message"], state.get("reply", ""))
    return {"analysis": result}


_graph = StateGraph(State)
_graph.add_node("respond", respond_node)
_graph.add_node("analyze", analyze_node)
_graph.set_entry_point("respond")
_graph.add_edge("respond", "analyze")
_graph.add_edge("analyze", END)
brain = _graph.compile()


def _empty_analysis() -> dict:
    return {"classification": "vacio", "subtype": None, "note": "",
            "escalate": False, "tags": [], "raw": ""}


def run_brain(user_message: str, conversation_id: str = "") -> dict:
    if not user_message:
        return {"reply": "No recibi ningun mensaje.", "analysis": _empty_analysis()}
    try:
        result = brain.invoke(
            {"user_message": user_message, "conversation_id": conversation_id,
             "reply": "", "analysis": {}, "stage": "", "next_stage": ""}
        )
        return {"reply": result["reply"],
                "analysis": result.get("analysis") or _empty_analysis(),
                "stage": result.get("stage"),
                "next_stage": result.get("next_stage")}
    except RuntimeError as e:
        return {"reply": f"[config] {e}", "analysis": _empty_analysis()}
    except Exception as e:
        return {"reply": f"[error] {type(e).__name__}: {e}", "analysis": _empty_analysis()}
