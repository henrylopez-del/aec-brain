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
from config import load_prompt
from analyzer import analyze

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

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


def respond_node(state: State) -> dict:
    llm = _get_llm()
    conv = state.get("conversation_id", "")
    user_msg = state["user_message"]

    # Memoria: arma el contexto con el historial previo de esta conversacion.
    messages = [SystemMessage(content=_system_prompt())]
    for m in fetch_history(conv):
        if m.get("role") == "user":
            messages.append(HumanMessage(content=m.get("content", "")))
        else:
            messages.append(AIMessage(content=m.get("content", "")))
    messages.append(HumanMessage(content=user_msg))

    out = llm.invoke(messages)
    reply = out.content

    # Persiste el turno para que el proximo mensaje lo recuerde.
    append_messages(conv, [("user", user_msg), ("assistant", reply)])
    return {"reply": reply}


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
             "reply": "", "analysis": {}}
        )
        return {"reply": result["reply"],
                "analysis": result.get("analysis") or _empty_analysis()}
    except RuntimeError as e:
        return {"reply": f"[config] {e}", "analysis": _empty_analysis()}
    except Exception as e:
        return {"reply": f"[error] {type(e).__name__}: {e}", "analysis": _empty_analysis()}
