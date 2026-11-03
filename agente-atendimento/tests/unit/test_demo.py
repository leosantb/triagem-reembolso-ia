"""Modo sem LLM (demo online): fatos informados + texto padrão."""
from decimal import Decimal

from agente.adapters.dev import InMemoryDecisionStore, StubTriage
from agente.agent import SupportAgent
from agente.config import Settings
from agente.demo import ensure_triage_model
from agente.domain.models import AffectedItem, Action, IssueType
from agente.policy import fallback_reply

from factories import facts, order, ticket


class Orders:
    async def get(self, order_id):
        return order() if order_id == "P" else None


def agent_sem_llm():
    return SupportAgent(llm=None, orders=Orders(), triage=StubTriage(),
                        store=InMemoryDecisionStore(), settings=Settings())


async def test_fatos_informados_sem_llm_reembolsam_com_template():
    r = await agent_sem_llm().handle(ticket(), facts_override=facts())
    assert r.decision.action == Action.REEMBOLSAR
    assert r.decision.amount == Decimal("29.90")
    assert r.message == fallback_reply(r.decision)


async def test_fatos_informados_passam_pela_limpeza_de_sku():
    f = facts(affected_items=[AffectedItem(sku="INVENTADO", qty=1)])
    r = await agent_sem_llm().handle(ticket(), facts_override=f)
    assert r.facts.affected_items == []
    assert r.decision.action == Action.PEDIR_INFO


async def test_sem_llm_e_sem_fatos_escala():
    r = await agent_sem_llm().handle(ticket())
    assert r.decision.reason_code == "extracao_falhou"


async def test_fatos_informados_nao_furam_regras():
    # o formulário não decide: "outro" continua pedindo informação
    f = facts(issue_type=IssueType.OUTRO, affected_items=[])
    r = await agent_sem_llm().handle(ticket(), facts_override=f)
    assert r.decision.action == Action.PEDIR_INFO


def test_nao_treina_se_modelo_existe(tmp_path, monkeypatch):
    (tmp_path / "modelos").mkdir()
    (tmp_path / "modelos" / "modelo_risco.joblib").write_bytes(b"x")
    chamado = []
    monkeypatch.setattr("agente.demo.subprocess.run", lambda *a, **k: chamado.append(a))
    ensure_triage_model(tmp_path)
    assert chamado == []


def test_treina_com_os_scripts_da_triagem_se_falta_modelo(tmp_path, monkeypatch):
    chamado = []
    monkeypatch.setattr("agente.demo.subprocess.run",
                        lambda cmd, **k: chamado.append((cmd[-1], k["cwd"])))
    ensure_triage_model(tmp_path)
    assert chamado == [("src.gerar_dados", tmp_path), ("src.treinar", tmp_path)]
