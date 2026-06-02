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

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

# El prompt vive en env var, NO en codigo. Asi Vic/Henry lo cambian sin deploy.
DEFAULT_PROMPT = (
    "Eres un asistente de atencion al cliente por WhatsApp. "
    "Responde claro, breve y en espanol. Si no tienes un dato, dilo, no lo inventes."
)
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", DEFAULT_PROMPT)


class State(TypedDict):
    user_message: str
    conversation_id: str
    reply: str


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
    messages = [SystemMessage(content=SYSTEM_PROMPT)]
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


_graph = StateGraph(State)
_graph.add_node("respond", respond_node)
_graph.set_entry_point("respond")
_graph.add_edge("respond", END)
brain = _graph.compile()


def run_brain(user_message: str, conversation_id: str = "") -> str:
    if not user_message:
        return "No recibi ningun mensaje."
    try:
        result = brain.invoke(
            {"user_message": user_message, "conversation_id": conversation_id, "reply": ""}
        )
        return result["reply"]
    except RuntimeError as e:
        return f"[config] {e}"
    except Exception as e:
        return f"[error] {type(e).__name__}: {e}"
