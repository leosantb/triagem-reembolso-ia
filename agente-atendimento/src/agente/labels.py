"""Textos em português para exibir os códigos internos na tela.

Só apresentação: a política, a triagem e o registro de auditoria continuam usando os
códigos (ex.: "risco_alto"). Código sem texto aqui cai num formato legível genérico.
"""
from agente.domain.models import PaymentMethod

# Motivos e passos da decisão (policy.py) e resultados/alertas da triagem (adapters/triage.py)
LABELS: dict[str, str] = {
    # decisão
    "aprovado": "Reembolso aprovado",
    "risco": "Risco apontado pela triagem",
    "pedido_invalido": "Pedido não confere com o cliente",
    "extracao_falhou": "Não foi possível entender o chamado",
    "valor_acima_limite": "Valor acima do limite de aprovação automática",
    "valor_indefinido": "Não foi possível calcular o valor",
    "pagamento_dinheiro": "Pedido pago em dinheiro",
    "faltam_itens": "Faltou dizer quais itens vieram com problema",
    "falta_foto": "Falta foto do produto",
    "tipo_indefinido": "Tipo de problema não identificado",
    "status_conflitante": "O pedido consta como entregue",
    "triagem_inelegivel": "Triagem considerou o pedido inelegível",
    "valor_itens_afetados": "Valor calculado pelos itens com problema",
    "nao_entregue_total": "Valor total do pedido, com taxas",
    # triagem
    "risco_baixo": "Risco baixo",
    "risco_medio": "Risco médio",
    "risco_alto": "Risco alto",
    "gps_proximo": "GPS indica o entregador perto do endereço",
    "tipo_sem_triagem": "Tipo de problema não coberto pela triagem",
    "triagem_indisponivel": "Triagem indisponível no momento",
    "sinais_indisponiveis": "Sem dados de risco do cliente",
    "sem_triagem": "Triagem não aplicada",
    "ok": "Sem ressalvas",
    # status do pedido
    "entregue": "Entregue",
    "nao_entregue": "Não entregue",
    "em_rota": "Em rota",
    "cancelado": "Cancelado",
    # forma de pagamento
    "pix": "Pix",
    "cartao": "Cartão",
    "vale_refeicao": "Vale-refeição",
    "saldo_app": "Saldo no app",
    "dinheiro": "Dinheiro",
    # responsável
    "restaurante": "Restaurante",
    "entregador": "Entregador",
    "plataforma": "Plataforma",
    "indeterminado": "Não definido",
}

# Flags de nível de risco: já aparecem em "Nível de risco", não se repetem em "Alertas"
RISK_LEVEL_FLAGS = {"risco_baixo", "risco_medio", "risco_alto"}

REFUND_DEST: dict[str, str] = {
    PaymentMethod.PIX.value: "no Pix",
    PaymentMethod.CARTAO.value: "no cartão",
    PaymentMethod.VALE_REFEICAO.value: "no vale-refeição",
    PaymentMethod.SALDO_APP.value: "como saldo no app",
    PaymentMethod.DINHEIRO.value: "em dinheiro",
}


def label(code: str | None) -> str:
    """Texto legível para um código interno; sem texto cadastrado, troca "_" por espaço."""
    if not code:
        return "—"
    code = str(code)
    return LABELS.get(code) or code.replace("_", " ").capitalize()


def refund_destination(method: str | None) -> str:
    return REFUND_DEST.get(str(method), "") if method else ""


def alert_flags(flags: list[str]) -> list[str]:
    """Alertas para exibir: sem as flags de nível de risco, que já têm linha própria."""
    return [label(f) for f in flags if f not in RISK_LEVEL_FLAGS]
