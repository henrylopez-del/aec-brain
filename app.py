"""
API del cerebro AEC (prueba).

Flujo: n8n (AEC pruebas) hace POST aqui con el mensaje del cliente.
Devolvemos {"reply": "..."} y n8n se encarga de enviarlo. El reply vuelve a n8n.
"""
from fastapi import FastAPI, Request
from brain import run_brain

app = FastAPI(title="AEC brain (prueba)")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/respond")
async def respond(req: Request):
    payload = await req.json()

    # Parseo defensivo: la forma exacta del payload de n8n se ajusta
    # cuando Henry mande un export de una ejecucion de AEC pruebas.
    # Por ahora intentamos los nombres de campo mas comunes.
    msg = (
        payload.get("message")
        or payload.get("body")
        or payload.get("text")
        or payload.get("userMessage")
        or ""
    )
    conv = (
        payload.get("conversationId")
        or payload.get("conversation_id")
        or payload.get("id")
        or ""
    )

    reply = run_brain(msg, conv)
    return {"reply": reply, "conversationId": conv}
