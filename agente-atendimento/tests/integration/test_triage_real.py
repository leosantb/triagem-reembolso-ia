"""Integração com o projeto de triagem real (raiz do repositório), sem alterá-lo.

Pulado se o modelo não foi treinado ou se o extra `local-triage` não está instalado.
"""
import json
import sys
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from agente.adapters.dev import InMemoryDecisionStore
from agente.adapters.fake_orders import FakeOrderRepository
from agente.adapters.fake_signals import FakeRiskSignalsProvider
from agente.adapters.triage import LocalTriageAdapter, load_local_triage
from agente.agent import SupportAgent
from agente.config import Settings, settings
from agente.domain.models import Action, AffectedItem, ExtractedFacts, IssueType, Ticket

pytestmark = pytest.mark.integration

MODEL = settings.triage_root / "modelos" / "modelo_risco.joblib"
if not MODEL.is_file():
    pytest.skip("modelo da triagem não treinado", allow_module_level=True)
pytest.importorskip("sklearn")


@pytest.fixture(scope="module")
def triar():
    return load_local_triage(settings.triage_root)


def test_carregar_nao_registra_pacote_src(triar):
    assert "src" not in sys.modules and "src.triagem" not in sys.modules


def test_triar_ainda_tem_o_contrato_esperado(triar):
    out = triar({
        "meses_conta": 36, "reembolsos_90d": 0, "reclamacoes_loja_semana": 8,
        "valor_pedido": 45.0, "atraso_min": 25, "distancia_gps_m": 20,
        "foto_compativel": 1, "tipo_problema": "comida_estragada",
    })
    assert set(out) == {"score", "faixa", "acao", "motivos"}
    assert out["faixa"] in {"baixo", "medio", "alto"}


@pytest.mark.parametrize("order_id, issue, items, flags", [
    ("P-1001", IssueType.ITEM_FALTANDO, [AffectedItem(sku="X-BURGER", qty=1)], []),
    ("P-1002", IssueType.ITEM_FALTANDO, [AffectedItem(sku="POKE", qty=1)], ["risco_medio"]),
    ("P-1003", IssueType.NAO_ENTREGUE, [], ["risco_alto", "gps_proximo"]),
    ("P-1004", IssueType.NAO_ENTREGUE, [], []),
])
async def test_fakes_caem_nas_faixas_calibradas(triar, order_id, issue, items, flags):
    order = await FakeOrderRepository().get(order_id)
    facts = ExtractedFacts(issue_type=issue, affected_items=items,
                           customer_wants="reembolso", summary="teste")
    ticket = Ticket(ticket_id="T", customer_id=order.customer_id, order_id=order_id,
                    message="teste", created_at=datetime.now(timezone.utc))
    r = await LocalTriageAdapter(triar, FakeRiskSignalsProvider()).evaluate(ticket, order, facts)
    assert r.risk_flags == flags
    assert r.score is not None and r.reasons


class _ScriptedLLM:
    """Sem Ollama: sem ferramentas, devolve os fatos dados e uma resposta vazia (-> template)."""

    def __init__(self, facts: dict):
        self._facts = json.dumps(facts)

    async def chat(self, messages, tools=None, response_schema=None):
        if tools:
            return {"message": {"content": "", "tool_calls": None}}
        if response_schema:
            return {"message": {"content": self._facts}}
        return {"message": {"content": ""}}


@pytest.mark.parametrize("order_id, facts, action, amount", [
    # e01: faltou 1 de 2 X-Burger, cliente antigo -> reembolsa R$ 29,90 no Pix
    ("P-1001", {"issue_type": "item_faltando", "affected_items": [{"sku": "X-BURGER", "qty": 1}]},
     Action.REEMBOLSAR, Decimal("29.90")),
    # e05: faixa média -> humano
    ("P-1002", {"issue_type": "item_faltando", "affected_items": [{"sku": "POKE", "qty": 1}]},
     Action.ESCALAR, Decimal("0")),
    # e06: faixa alta + GPS no endereço -> humano
    ("P-1003", {"issue_type": "nao_entregue"}, Action.ESCALAR, Decimal("0")),
    # e07: não entregue, faixa baixa -> total com taxas (42,00 + 4,99 + 0,99)
    ("P-1004", {"issue_type": "nao_entregue"}, Action.REEMBOLSAR, Decimal("47.98")),
])
async def test_agente_ponta_a_ponta_com_triagem_real(triar, order_id, facts, action, amount):
    orders = FakeOrderRepository()
    order = await orders.get(order_id)
    agent = SupportAgent(
        llm=_ScriptedLLM({"customer_wants": "reembolso", "summary": "teste", **facts}),
        orders=orders, triage=LocalTriageAdapter(triar, FakeRiskSignalsProvider()),
        store=InMemoryDecisionStore(), settings=Settings(auto_approve_limit_brl=80),
    )
    r = await agent.handle(Ticket(ticket_id="T", customer_id=order.customer_id,
                                  order_id=order_id, message="teste",
                                  created_at=datetime.now(timezone.utc)))
    assert r.decision.action == action
    assert r.decision.amount == amount
