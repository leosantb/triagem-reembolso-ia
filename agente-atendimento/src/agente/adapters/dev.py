from agente.domain.models import (
    Decision, ExtractedFacts, Order, Ticket, TriageResult, affected_amount,
)


class StubTriage:
    """Substitui a triagem real (TRIAGE_MODE=stub)."""

    async def evaluate(self, ticket: Ticket, order: Order, facts: ExtractedFacts) -> TriageResult:
        return TriageResult(
            eligible=True, confidence=0.9, reason_code="ok",
            suggested_amount=affected_amount(order, facts),
        )


class InMemoryDecisionStore:
    def __init__(self) -> None:
        self.records: list[dict] = []

    async def save(self, ticket: Ticket, decision: Decision, trace_id: str) -> None:
        self.records.append(
            {"ticket": ticket.model_dump(), "decision": decision.model_dump(), "trace_id": trace_id}
        )
