import json
from decimal import Decimal

from agente.adapters.dev import InMemoryDecisionStore, StubTriage
from agente.agent import SupportAgent
from agente.config import Settings
from agente.domain.models import Action, PaymentMethod
from agente.policy import fallback_reply

from factories import order, ticket, triage

S = Settings(auto_approve_limit_brl=80, max_tool_rounds=3)

FACTS_OK = {"issue_type": "item_faltando", "affected_items": [{"sku": "X", "qty": 1}],
            "customer_wants": "reembolso", "summary": "faltou 1 X-Burger"}


class ScriptedLLM:
    """Devolve respostas em ordem e guarda as mensagens recebidas."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.seen: list[list[dict]] = []

    async def chat(self, messages, tools=None, response_schema=None):
        self.seen.append([dict(m) for m in messages])
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return {"message": r}


def msg(content="", tool_calls=None):
    return {"content": content, "tool_calls": tool_calls}


class Orders:
    def __init__(self, o=None):
        self.o = o or order()

    async def get(self, order_id):
        return self.o if order_id == self.o.order_id else None


class FixedTriage:
    def __init__(self, result):
        self.result = result

    async def evaluate(self, ticket, order, facts):
        return self.result


def agent(llm, triage_svc=None, store=None):
    return SupportAgent(llm=llm, orders=Orders(), triage=triage_svc or StubTriage(),
                        store=store or InMemoryDecisionStore(), settings=S)


async def test_fluxo_completo_reembolsa():
    llm = ScriptedLLM(
        msg(tool_calls=[{"function": {"name": "consultar_pedido", "arguments": {}}}]),
        msg(),                                  # fim das ferramentas
        msg(json.dumps(FACTS_OK)),              # fatos estruturados
        msg("Sentimos muito. Reembolsamos R$ 29,90 no seu Pix."),
    )
    store = InMemoryDecisionStore()
    r = await agent(llm, store=store).handle(ticket())
    assert r.decision.action == Action.REEMBOLSAR
    assert r.decision.amount == Decimal("29.90")
    assert r.decision.refund_to == PaymentMethod.PIX
    assert r.message.endswith("R$ 29,90 no seu Pix.")
    assert len(store.records) == 1
    tool_msg = [m for m in llm.seen[1] if m["role"] == "tool"][0]
    assert json.loads(tool_msg["content"])["itens"][0]["sku"] == "X"


def call(name):
    return {"function": {"name": name, "arguments": {}}}


async def test_loop_para_quando_modelo_repete_ferramenta():
    llm = ScriptedLLM(
        msg(tool_calls=[call("consultar_pedido")]),
        msg(tool_calls=[call("consultar_pedido")]),   # repetição -> encerra o loop
        msg(json.dumps(FACTS_OK)),
        msg("Reembolsamos R$ 29,90."),
    )
    r = await agent(llm).handle(ticket())
    assert r.decision.action == Action.REEMBOLSAR
    assert llm.replies == []  # 4 chamadas ao LLM, e não 6 rodadas de ferramenta + 2


async def test_loop_para_quando_todas_as_ferramentas_foram_usadas():
    llm = ScriptedLLM(
        msg(tool_calls=[call("consultar_pedido"), call("consultar_entrega")]),
        msg(json.dumps(FACTS_OK)),                    # sem rodada extra de ferramentas
        msg("Reembolsamos R$ 29,90."),
    )
    r = await agent(llm).handle(ticket())
    assert r.decision.action == Action.REEMBOLSAR
    tool_msgs = [m for m in llm.seen[1] if m["role"] == "tool"]
    assert [m["tool_name"] for m in tool_msgs] == ["consultar_pedido", "consultar_entrega"]


async def test_risco_da_triagem_escala():
    llm = ScriptedLLM(msg(), msg(json.dumps(FACTS_OK)), msg("Vamos analisar."))
    tr = FixedTriage(triage(risk_flags=["risco_alto"], score=0.99))
    r = await agent(llm, tr).handle(ticket())
    assert r.decision.action == Action.ESCALAR
    assert "risco_alto" in r.decision.rule_trace
    assert r.triage.score == 0.99  # resultado da triagem vai na resposta


async def test_resposta_com_valor_errado_vira_template():
    llm = ScriptedLLM(msg(), msg(json.dumps(FACTS_OK)), msg("Reembolsamos R$ 59,80."))
    r = await agent(llm).handle(ticket())
    assert r.message == fallback_reply(r.decision)


async def test_json_invalido_tem_uma_correcao():
    llm = ScriptedLLM(msg(), msg("{quebrado"), msg(json.dumps(FACTS_OK)),
                      msg("Reembolsamos R$ 29,90."))
    r = await agent(llm).handle(ticket())
    assert r.decision.action == Action.REEMBOLSAR


async def test_sku_inventado_e_removido():
    facts = {**FACTS_OK, "affected_items": [{"sku": "INVENTADO", "qty": 1}]}
    llm = ScriptedLLM(msg(), msg(json.dumps(facts)), msg("Quais itens?"))
    r = await agent(llm).handle(ticket())
    assert r.facts.affected_items == []
    assert r.decision.action == Action.PEDIR_INFO


async def test_pedido_de_outro_cliente_escala_sem_llm_de_extracao():
    llm = ScriptedLLM(msg("Vamos verificar."))
    r = await agent(llm).handle(ticket(customer_id="OUTRO"))
    assert r.decision.reason_code == "pedido_invalido"
    assert r.triage is None
    assert len(llm.seen) == 1  # só a resposta


async def test_llm_fora_do_ar_escala_e_usa_template():
    llm = ScriptedLLM(ConnectionError("ollama off"), ConnectionError("ollama off"))
    r = await agent(llm).handle(ticket())
    assert r.decision.reason_code == "extracao_falhou"
    assert r.message == fallback_reply(r.decision)


async def test_dados_pessoais_nao_chegam_ao_llm():
    llm = ScriptedLLM(msg(), msg(json.dumps(FACTS_OK)), msg("Reembolsamos R$ 29,90."))
    await agent(llm).handle(ticket(message="faltou lanche, meu email é ana@exemplo.com"))
    first_user = llm.seen[0][1]["content"]
    assert "ana@exemplo.com" not in first_user and "[EMAIL]" in first_user
