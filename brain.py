"""
Cerebro AEC (prueba) - LangGraph minimo.

Alcance de la prueba: recibe un mensaje, responde, devuelve texto.
Sin escalacion, sin follow-up, sin guard TVS (eso es produccion).

El grafo arranca con un solo nodo (responder). Esta hecho asi a proposito
para que crezca: cuando se sume routing, sub-agentes o guard, se agregan
nodos sin reescribir nada.
"""
import os
from typing import TypedDict

from langgraph.graph import StateGraph, END
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import SystemMessage, HumanMessage

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

# El prompt vive en env var, NO en codigo. Asi Vic/Henry lo cambian sin deploy.
# Default generico solo para validar que el tubo responde algo coherente.
DEFAULT_PROMPT = (
    "Eres un asistente de atencion al cliente por WhatsApp. "
    "Responde claro, breve y en espanol. Si no tienes un dato, dilo, no lo inventes."
)
SYSTEM_PROMPT = os.getenv("SYSTEM_PROMPT", DEFAULT_PROMPT)


class State(TypedDict):
    user_message: str
    conversation_id: str
    reply: str


_llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0, max_output_tokens=600)


def respond_node(state: State) -> dict:
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=state["user_message"]),
    ]
    out = _llm.invoke(messages)
    return {"reply": out.content}


_graph = StateGraph(State)
_graph.add_node("respond", respond_node)
_graph.set_entry_point("respond")
_graph.add_edge("respond", END)
brain = _graph.compile()


def run_brain(user_message: str, conversation_id: str = "") -> str:
    if not user_message:
        return "No recibi ningun mensaje."
    result = brain.invoke(
        {"user_message": user_message, "conversation_id": conversation_id, "reply": ""}
    )
    return result["reply"]
