# AEC brain (prueba)

Cerebro en Python para el flujo `AEC pruebas`. n8n recibe el mensaje, lo manda
aqui por HTTP, este servicio responde con Gemini y devuelve el texto. n8n envia
la respuesta. **El reply vuelve a n8n.** Solo respuestas, sin escalacion.

```
WhatsApp/GHL -> n8n (AEC pruebas) -> POST /respond -> Gemini -> {"reply": "..."} -> n8n envia
```

## Endpoints

- `GET  /health`  -> `{"ok": true}`
- `POST /respond` -> recibe el JSON de n8n, devuelve `{"reply": "...", "conversationId": "..."}`

## Deploy en Render (free)

1. Subir este repo a GitHub (privado esta bien).
2. En Render: **New -> Blueprint** y seleccionar el repo. Render lee `render.yaml` solo.
3. En el dashboard del servicio, pestana **Environment**, setear:
   - `GEMINI_API_KEY` = la key de Gemini (esta en Supabase, categoria general).
   - `SYSTEM_PROMPT` = el prompt de prueba (se puede cambiar sin redeploy).
4. Deploy. Render da una URL tipo `https://aec-brain-test.onrender.com`.
5. Esa URL + `/respond` es la que se pega en el nodo HTTP Request de `AEC pruebas`.

> Nota: el plan free duerme tras ~15 min sin trafico. El primer mensaje despues
> de un rato tarda ~30-60s en despertar. Normal para pruebas.

## Probar local

```bash
pip install -r requirements.txt
cp .env.example .env        # y poner la GEMINI_API_KEY
uvicorn app:app --reload
curl -X POST localhost:8000/respond -H "Content-Type: application/json" \
  -d '{"message":"hola, que motos tienen?","conversationId":"test1"}'
```

## Pendiente de Henry para cerrar la prueba

- Export de una ejecucion de `AEC pruebas` -> ajustar el parseo del payload en `app.py`.
- Definir el `SYSTEM_PROMPT` de prueba (opcion A: el de la instancia de pruebas / opcion B: uno generico).
- El nodo HTTP Request en `AEC pruebas` apuntando a la URL de Render.
