from typing import Any, Protocol

from agente.domain.models import (
    Decision, ExtractedFacts, Order, RiskSignals, Ticket, TriageResult,
)


class OrderRepository(Protocol):
    async def get(self, order_id: str) -> Order | None: ...


class RiskSignalsProvider(Protocol):
    async def get(self, order: Order) -> RiskSignals | None: ...


class TriageService(Protocol):
    async def evaluate(
        self, ticket: Ticket, order: Order, facts: ExtractedFacts
    ) -> TriageResult: ...


class DecisionStore(Protocol):
    async def save(self, ticket: Ticket, decision: Decision, trace_id: str) -> None: ...


class LLMClient(Protocol):
    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...
