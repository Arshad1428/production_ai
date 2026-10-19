import httpx
from fastapi import HTTPException

class OllamaModel:
    def __init__(self, client, settings):
        self.client, self.settings = client, settings

    async def chat(self, messages):
        try:
            response = await self.client.post("/api/chat", json={
                "model":self.settings.ollama_model, "messages":messages, "stream":False,
                "options":{"temperature":0.2, "num_predict":self.settings.max_output_tokens},
            })
            response.raise_for_status()
            content = response.json()["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Empty model output")
            return content
        except httpx.TimeoutException:
            raise HTTPException(504, "Model response timed out") from None
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            raise HTTPException(503, "Ollama unavailable, model missing, or invalid response") from None

    async def ready(self):
        try:
            r = await self.client.get("/api/tags", timeout=3)
            r.raise_for_status()
            models = r.json()["models"]
            wanted = self.settings.ollama_model
            return any(m.get("name") in {wanted, wanted + ":latest"} for m in models)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            return False
