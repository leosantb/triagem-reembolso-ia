from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from pydantic import BaseModel, Field

from agente.adapters.dev import InMemoryDecisionStore, StubTriage
from agente.adapters.fake_orders import FakeOrderRepository
from agente.adapters.fake_signals import FakeRiskSignalsProvider
from agente.adapters.ollama_llm import OllamaLLM
from agente.adapters.triage import HttpTriageAdapter, LocalTriageAdapter, load_local_triage
from agente.agent import SupportAgent
from agente.config import Settings, settings
from agente.domain.models import AgentReply, Ticket
from agente.ports import TriageService


def build_triage(s: Settings) -> TriageService:
    if s.triage_mode == "http":
        return HttpTriageAdapter(s.triage_url, FakeRiskSignalsProvider(), s.triage_timeout_s)
    if s.triage_mode == "local":
        return LocalTriageAdapter(load_local_triage(s.triage_root), FakeRiskSignalsProvider())
    return StubTriage()


def build_agent(s: Settings = settings) -> SupportAgent:
    llm = OllamaLLM(s.ollama_host, s.llm_model, s.llm_temperature, s.llm_timeout_s)
    return SupportAgent(
        llm=llm,
        orders=FakeOrderRepository(),   # trocar pelo repositório real
        triage=build_triage(s),
        store=InMemoryDecisionStore(),  # trocar por Postgres
        settings=s,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = build_agent()
    yield


app = FastAPI(title="Agente de Atendimento", lifespan=lifespan)


class TicketIn(BaseModel):
    ticket_id: str
    customer_id: str
    order_id: str
    message: str = Field(min_length=3, max_length=4000)
    attachment_urls: list[str] = []


@app.post("/tickets", response_model=AgentReply)
async def handle_ticket(body: TicketIn) -> AgentReply:
    ticket = Ticket(**body.model_dump(), created_at=datetime.now(timezone.utc))
    # Falhas do LLM e da triagem já degradam para escalar/template dentro do agente.
    return await app.state.agent.handle(ticket)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.llm_model, "triage_mode": settings.triage_mode}
