from typing import Any

from ollama import AsyncClient


class OllamaLLM:
    def __init__(self, host: str, model: str, temperature: float, timeout_s: float) -> None:
        self._client = AsyncClient(host=host, timeout=timeout_s)
        self._model = model
        self._temperature = temperature

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resp = await self._client.chat(
            model=self._model,
            messages=messages,
            tools=tools,
            format=response_schema,  # structured output do Ollama
            options={"temperature": self._temperature},
        )
        return resp.model_dump()
