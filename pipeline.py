"""
Pipeline de ventas ESTRUCTURADO para Ainnovation (no "wildfire creative").

El bot no improvisa: avanza por etapas con un objetivo único cada una y un
GATE determinista para pasar a la siguiente. Cada etapa tiene su propio prompt
en tenant_prompts (agent_key='pipeline', prompt_key='stage_<nombre>').

Esto es lo opuesto al prompt creativo único: predecible, califica, y solo
avanza cuando se cumple el criterio de la etapa.

Etapas (mapeadas al pipeline GHL "Ventas"):
  apertura -> calificacion -> educacion -> demo -> cierre
"""
from langchain_core.messages import SystemMessage, HumanMessage

STAGES = ["apertura", "calificacion", "educacion", "demo", "cierre"]

# Objetivo de cada etapa + criterio (gate) para avanzar.
STAGE_DEF = {
    "apertura": {
        "goal": "Enganchar, identificar el giro del negocio y el dolor principal.",
        "gate": "El cliente ya dijo su giro/tipo de negocio Y al menos un dolor o necesidad concreta.",
    },
    "calificacion": {
        "goal": "Calificar: volumen de mensajes/dia, quien contesta hoy, herramienta actual, presupuesto aproximado.",
        "gate": "Ya hay al menos 2 datos de calificacion (volumen, quien contesta, herramienta o presupuesto).",
    },
    "educacion": {
        "goal": "Explicar como el sistema resuelve SU dolor especifico y manejar la objecion principal.",
        "gate": "El cliente mostro interes real (pregunto como sigue, pidio ejemplos) o resolvio su objecion.",
    },
    "demo": {
        "goal": "Proponer y agendar una demo. Confirmar si es la persona que decide.",
        "gate": "El cliente acepto agendar una demo o pidio fecha/horario.",
    },
    "cierre": {
        "goal": "Cerrar el plan adecuado y dar el siguiente paso (link de pago / agenda).",
        "gate": "El cliente confirmo el plan o pregunto como pagar/contratar.",
    },
}


def first_stage() -> str:
    return STAGES[0]


def next_stage(current: str) -> str:
    """Avanza una sola etapa hacia adelante. Nunca salta ni retrocede."""
    try:
        i = STAGES.index(current)
    except ValueError:
        return STAGES[0]
    return STAGES[min(i + 1, len(STAGES) - 1)]


def stage_goal(stage: str) -> str:
    return STAGE_DEF.get(stage, {}).get("goal", "")


def stage_prompt_key(stage: str) -> str:
    return f"stage_{stage}"


def decide_advance(llm, history: list, user_message: str, reply: str, current_stage: str) -> bool:
    """
    Gate determinista-asistido: ¿se cumple el criterio para avanzar de etapa?
    Una sola llamada corta al LLM, temperatura 0, salida binaria.
    Forward-only: si avanza, sube exactamente una etapa.
    """
    crit = STAGE_DEF.get(current_stage, {}).get("gate", "")
    if not crit:
        return False
    convo = "\n".join(
        ("Cliente: " if m.get("role") == "user" else "Bot: ") + m.get("content", "")
        for m in history[-6:]
    )
    sys = (
        "Eres un evaluador de etapa de un pipeline de ventas. "
        "Decide si la conversacion YA cumple el criterio para avanzar de etapa. "
        "Responde EXCLUSIVAMENTE una palabra: AVANZAR o QUEDAR. Sin explicacion."
    )
    human = (
        f"Etapa actual: {current_stage}\n"
        f"Criterio para avanzar: {crit}\n\n"
        f"Conversacion reciente:\n{convo}\n"
        f"Ultimo mensaje del cliente: {user_message}\n"
        f"Respuesta del bot: {reply}\n\n"
        "Se cumple el criterio? AVANZAR o QUEDAR:"
    )
    try:
        out = llm.invoke([SystemMessage(content=sys), HumanMessage(content=human)])
        return "AVANZAR" in (out.content or "").upper()
    except Exception:
        return False
