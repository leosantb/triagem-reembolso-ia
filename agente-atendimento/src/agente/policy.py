import re
from decimal import Decimal, InvalidOperation

from agente.config import Settings
from agente.domain.models import (
    Action, Decision, ExtractedFacts, IssueType, Order, PaymentMethod, Responsible, TriageResult,
)

_ITEM_ISSUES = {IssueType.ITEM_FALTANDO, IssueType.ITEM_ERRADO, IssueType.QUALIDADE}

_ANALISE = "o caso precisa de uma análise adicional da nossa equipe"

_REASONS = {
    "pedido_invalido": "não conseguimos confirmar o pedido vinculado ao chamado",
    "extracao_falhou": "precisamos que uma pessoa do time analise o seu caso",
    "risco": _ANALISE,
    "valor_acima_limite": "o valor exige aprovação de uma pessoa do time",
    "valor_indefinido": "precisamos que uma pessoa do time calcule o valor do seu caso",
    "pagamento_dinheiro": "o pagamento foi em dinheiro e o estorno precisa ser combinado",
    "faltam_itens": "precisamos saber quais itens vieram com problema",
    "falta_foto": "precisamos de uma foto do produto para analisar a qualidade",
    "tipo_indefinido": "precisamos de mais detalhes sobre o que aconteceu",
    "status_conflitante": "o sistema mostra o pedido como entregue e vamos verificar",
    "aprovado": "identificamos o problema no seu pedido",
    # códigos vindos da triagem (adapters/triage.py)
    "risco_baixo": "identificamos o problema no seu pedido",
    "risco_medio": _ANALISE,
    "risco_alto": _ANALISE,
    "tipo_sem_triagem": _ANALISE,
    "triagem_indisponivel": _ANALISE,
    "sem_triagem": "precisamos de mais detalhes sobre o que aconteceu",
}


def reason_text(code: str) -> str:
    return _REASONS.get(code, code)


def escalate(reason: str, trace: list[str] | None = None) -> Decision:
    return Decision(action=Action.ESCALAR, reason_code=reason, rule_trace=[*(trace or []), reason])


def _ask(reason: str) -> Decision:
    return Decision(action=Action.PEDIR_INFO, reason_code=reason, rule_trace=[reason])


def attribute_responsibility(facts: ExtractedFacts, order: Order) -> Responsible:
    if facts.issue_type in _ITEM_ISSUES:
        return Responsible.RESTAURANTE
    if facts.issue_type == IssueType.NAO_ENTREGUE:
        return Responsible.ENTREGADOR if order.courier_id else Responsible.PLATAFORMA
    if facts.issue_type == IssueType.ATRASO:
        return Responsible.PLATAFORMA
    return Responsible.INDETERMINADO


def decide(facts: ExtractedFacts, order: Order, triage: TriageResult, s: Settings) -> Decision:
    trace: list[str] = []
    responsible = attribute_responsibility(facts, order)

    # 1) segurança primeiro. Não há limite de confiança aqui: a faixa da triagem já decide
    #    (média/alta viram risk_flags no adapter).
    if triage.risk_flags:
        return escalate("risco", [*trace, *triage.risk_flags])

    # 2) falta informação -> pede ao cliente, não nega
    if facts.issue_type == IssueType.OUTRO:
        return _ask("tipo_indefinido")
    if facts.issue_type in _ITEM_ISSUES and not facts.affected_items:
        return _ask("faltam_itens")
    if facts.issue_type == IssueType.QUALIDADE and not facts.has_photo_evidence:
        return _ask("falta_foto")

    # 3) valor calculado a partir do pedido, nunca do texto
    if facts.issue_type == IssueType.NAO_ENTREGUE:
        if order.status == "entregue":
            return escalate("status_conflitante", trace)
        amount = order.items_total + order.delivery_fee + order.service_fee
        trace.append("nao_entregue_total")
    else:
        amount = min(triage.suggested_amount, order.items_total)
        trace.append("valor_itens_afetados")

    # 4) triagem nega -> nega com motivo explícito
    #    (a triagem atual nunca nega; a regra fica para uma triagem futura que negue)
    if not triage.eligible:
        return Decision(
            action=Action.NEGAR, reason_code=triage.reason_code,
            responsible=responsible, rule_trace=[*trace, "triagem_inelegivel"],
        )

    # 5) limites de autonomia
    if amount <= 0:  # ex.: atraso sem itens afetados; nunca "reembolsar R$ 0,00"
        return escalate("valor_indefinido", trace)
    if amount > Decimal(str(s.auto_approve_limit_brl)):
        return escalate("valor_acima_limite", trace)
    if order.payment_method == PaymentMethod.DINHEIRO and not facts.prefers_app_credit:
        return escalate("pagamento_dinheiro", trace)

    # 6) reembolso no meio original, saldo só se o cliente pediu
    refund_to = PaymentMethod.SALDO_APP if facts.prefers_app_credit else order.payment_method
    return Decision(
        action=Action.REEMBOLSAR, amount=amount.quantize(Decimal("0.01")),
        refund_to=refund_to, responsible=responsible,
        reason_code="aprovado", rule_trace=[*trace, "aprovado"],
    )


# ---------- guardrails da resposta ----------

_MONEY = re.compile(r"R\$\s?([\d.,]+)")
_CURRENCY = re.compile(r"R\$")
# Promessa de devolução de dinheiro. Só é aceita quando a decisão é reembolsar.
_PROMISE = re.compile(
    r"\b(vamos|iremos|vou|podemos|vai|irá)\s+(te\s+)?(reembolsar|devolver|estornar)"
    r"|\breembolsaremos\b|\bdevolveremos\b|\bestornaremos\b"
    r"|\b(reembolso|estorno|devolução)\s+(será|foi|está)\b"
    r"|\breembolso\s+(aprovado|confirmado)",
    re.IGNORECASE,
)


def _parse_brl(raw: str) -> Decimal | None:
    s = raw.strip(".,")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def format_brl(v: Decimal) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def reply_is_consistent(text: str, d: Decision) -> bool:
    values = [v for v in (_parse_brl(m) for m in _MONEY.findall(text)) if v is not None]
    currency_mentions = len(_CURRENCY.findall(text))
    if d.action == Action.REEMBOLSAR:
        # todo "R$" precisa ser um número igual ao decidido (rejeita "R$ X", "R$ ...")
        return (bool(values) and len(values) == currency_mentions
                and all(v == d.amount for v in values))
    if currency_mentions:  # qualquer valor citado fora de reembolso é promessa indevida
        return False
    if _PROMISE.search(text):  # "vamos reembolsar" sem decisão de reembolso
        return False
    if d.action == Action.NEGAR:
        return "revis" in text.lower()  # tem que oferecer revisão humana
    return True


_DEST = {
    PaymentMethod.SALDO_APP: "como saldo no app",
    PaymentMethod.PIX: "na conta usada no Pix",
    PaymentMethod.CARTAO: "no cartão usado na compra",
    PaymentMethod.VALE_REFEICAO: "no vale-refeição usado na compra",
}


def fallback_reply(d: Decision) -> str:
    motivo = reason_text(d.reason_code)
    if d.action == Action.REEMBOLSAR:
        return (f"Sentimos muito pelo problema com o seu pedido. Como {motivo}, "
                f"aprovamos o reembolso de {format_brl(d.amount)} {_DEST.get(d.refund_to, '')}.")
    if d.action == Action.NEGAR:
        return ("Analisamos o seu pedido e, neste caso, não foi possível aprovar o reembolso: "
                f"{motivo}. Se discordar, responda esta mensagem e uma pessoa do time fará a "
                "revisão.")
    if d.action == Action.PEDIR_INFO:
        return f"Queremos resolver isso rápido: {motivo}. Pode nos enviar?"
    return f"Recebemos o seu chamado e {motivo}. Você terá retorno de uma pessoa do time em breve."
