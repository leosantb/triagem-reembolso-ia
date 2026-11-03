from decimal import Decimal

import pytest

from agente.config import Settings
from agente.domain.models import Action, Decision, IssueType, OrderItem, PaymentMethod
from agente.policy import decide, fallback_reply, reply_is_consistent

from factories import facts, order, triage

S = Settings(auto_approve_limit_brl=80)


def test_reembolsa_no_meio_original():
    d = decide(facts(), order(), triage(), S)
    assert d.action == Action.REEMBOLSAR
    assert d.amount == Decimal("29.90")
    assert d.refund_to == PaymentMethod.PIX


def test_saldo_so_quando_cliente_pede():
    d = decide(facts(prefers_app_credit=True), order(), triage(), S)
    assert d.refund_to == PaymentMethod.SALDO_APP


@pytest.mark.parametrize("flag", ["risco_medio", "risco_alto", "triagem_indisponivel"])
def test_risk_flag_escala_e_fica_no_trace(flag):
    d = decide(facts(), order(), triage(risk_flags=[flag]), S)
    assert d.action == Action.ESCALAR
    assert d.reason_code == "risco"
    assert flag in d.rule_trace


def test_confianca_baixa_sem_flag_nao_escala():
    # decisão: vale a faixa da triagem, não um segundo limite de confiança no agente
    d = decide(facts(), order(), triage(confidence=0.71), S)
    assert d.action == Action.REEMBOLSAR


def test_acima_do_limite_escala():
    # O guia usava suggested_amount=120 num pedido de R$ 59,80; o valor é limitado ao total
    # dos itens, então nunca passaria do limite. Aqui o pedido realmente custa mais que R$ 80.
    o = order(items=[OrderItem(sku="X", name="Combo", qty=1, unit_price=Decimal("120.00"))])
    d = decide(facts(), o, triage(suggested_amount=Decimal("120")), S)
    assert d.action == Action.ESCALAR
    assert d.reason_code == "valor_acima_limite"


def test_valor_limitado_ao_total_dos_itens():
    d = decide(facts(), order(), triage(suggested_amount=Decimal("120")), S)
    assert d.amount == Decimal("59.80")


def test_sem_itens_pede_info_e_nao_nega():
    d = decide(facts(affected_items=[]), order(), triage(), S)
    assert d.action == Action.PEDIR_INFO


def test_outro_pede_info():
    d = decide(facts(issue_type=IssueType.OUTRO, affected_items=[]), order(), triage(), S)
    assert d.action == Action.PEDIR_INFO


def test_qualidade_sem_foto_pede_info():
    d = decide(facts(issue_type=IssueType.QUALIDADE), order(), triage(), S)
    assert d.reason_code == "falta_foto"


def test_nao_entregue_com_status_entregue_escala():
    d = decide(facts(issue_type=IssueType.NAO_ENTREGUE), order(), triage(), S)
    assert d.reason_code == "status_conflitante"


def test_nao_entregue_devolve_total_com_taxas():
    d = decide(facts(issue_type=IssueType.NAO_ENTREGUE, affected_items=[]),
               order(status="nao_entregue"), triage(), S)
    assert d.action == Action.REEMBOLSAR
    assert d.amount == Decimal("68.78")  # 59,80 + 7,99 + 0,99


def test_valor_zero_escala_em_vez_de_reembolsar_zero():
    d = decide(facts(issue_type=IssueType.ATRASO, affected_items=[]), order(),
               triage(suggested_amount=Decimal("0")), S)
    assert d.action == Action.ESCALAR
    assert d.reason_code == "valor_indefinido"


def test_dinheiro_escala_salvo_saldo_no_app():
    o = order(payment_method=PaymentMethod.DINHEIRO)
    assert decide(facts(), o, triage(), S).reason_code == "pagamento_dinheiro"
    assert decide(facts(prefers_app_credit=True), o, triage(), S).action == Action.REEMBOLSAR


def test_triagem_inelegivel_nega_com_motivo():
    d = decide(facts(), order(), triage(eligible=False, reason_code="fora_do_prazo"), S)
    assert d.action == Action.NEGAR
    assert d.reason_code == "fora_do_prazo"


def test_resposta_com_valor_diferente_e_rejeitada():
    d = Decision(action=Action.REEMBOLSAR, amount=Decimal("29.90"), reason_code="aprovado")
    assert reply_is_consistent("Reembolsamos R$ 29,90 no seu Pix.", d)
    assert not reply_is_consistent("Reembolsamos R$ 59,80 no seu Pix.", d)


def test_reembolso_com_valor_placeholder_e_rejeitado():
    d = Decision(action=Action.REEMBOLSAR, amount=Decimal("29.90"), reason_code="aprovado")
    assert not reply_is_consistent("Reembolsamos R$ 29,90, mais R$ X de taxa.", d)


@pytest.mark.parametrize("action", [Action.PEDIR_INFO, Action.ESCALAR, Action.NEGAR])
@pytest.mark.parametrize("text", [
    # caso real do qwen2.5:7b (e01): pedir_info com promessa e valor placeholder
    "Vamos reembolsar o valor correspondente. O reembolso será de R$ X.",
    "Vamos reembolsar o item faltante assim que possível. Pedimos revisão.",
    "Reembolsaremos o valor em breve; se quiser revisão, responda.",
    "O reembolso foi aprovado. Se discordar, peça revisão.",
])
def test_promessa_de_reembolso_fora_de_reembolsar_e_rejeitada(action, text):
    assert not reply_is_consistent(text, Decision(action=action, reason_code="x"))


@pytest.mark.parametrize("text", [
    "Precisamos saber quais itens vieram com problema. Pode nos informar?",
    "Seu caso foi encaminhado para uma pessoa do time, que vai analisar o reembolso.",
])
def test_resposta_sem_promessa_passa(text):
    assert reply_is_consistent(text, Decision(action=Action.PEDIR_INFO, reason_code="x"))


def test_negativa_sem_revisao_e_rejeitada():
    d = Decision(action=Action.NEGAR, reason_code="fora_do_prazo")
    assert not reply_is_consistent("Não podemos reembolsar.", d)


@pytest.mark.parametrize("d", [
    Decision(action=Action.REEMBOLSAR, amount=Decimal("29.90"), refund_to=PaymentMethod.PIX,
             reason_code="aprovado"),
    Decision(action=Action.NEGAR, reason_code="fora_do_prazo"),
    Decision(action=Action.PEDIR_INFO, reason_code="faltam_itens"),
    Decision(action=Action.ESCALAR, reason_code="risco"),
])
def test_fallback_sempre_passa_no_guardrail(d):
    assert reply_is_consistent(fallback_reply(d), d)
