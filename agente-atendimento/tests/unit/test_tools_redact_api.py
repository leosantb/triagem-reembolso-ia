from fastapi.testclient import TestClient

from agente import api as api_module
from agente.adapters.dev import StubTriage
from agente.adapters.triage import HttpTriageAdapter, LocalTriageAdapter
from agente.config import Settings
from agente.redact import redact
from agente.tools import build_tools

from factories import order, ticket


class Orders:
    async def get(self, order_id):
        return order() if order_id == "P" else None


async def test_ferramentas_sao_presas_ao_pedido_do_chamado():
    tools = build_tools(Orders(), ticket())
    names = {s["function"]["name"] for s in tools.schemas}
    assert names == {"consultar_pedido", "consultar_entrega"}
    for s in tools.schemas:
        assert s["function"]["parameters"]["properties"] == {}  # sem order_id
    assert "erro" in await tools.call("consultar_pedido", {"order_id": "999"})
    assert "erro" in await tools.call("reembolsar", {})


async def test_visao_do_pedido_sem_pii():
    view = await build_tools(Orders(), ticket()).call("consultar_pedido", {})
    assert set(view) == {"status", "itens", "taxa_entrega", "pagamento"}


def test_redact():
    out = redact("cpf 123.456.789-09, tel (11) 91234-5678, email a@b.com")
    assert "[CPF]" in out and "[TELEFONE]" in out and "[EMAIL]" in out
    assert "123.456" not in out and "a@b.com" not in out


def test_redact_nao_mexe_em_valores():
    assert redact("veio errado, paguei R$ 29,90") == "veio errado, paguei R$ 29,90"


def test_build_triage_por_modo(monkeypatch):
    assert isinstance(api_module.build_triage(Settings(triage_mode="stub")), StubTriage)
    assert isinstance(api_module.build_triage(Settings(triage_mode="http")), HttpTriageAdapter)
    monkeypatch.setattr(api_module, "load_local_triage", lambda root: lambda caso: {})
    assert isinstance(api_module.build_triage(Settings(triage_mode="local")), LocalTriageAdapter)


def test_api_health():
    with TestClient(api_module.app) as client:
        body = client.get("/health").json()
    assert body["status"] == "ok" and "triage_mode" in body
