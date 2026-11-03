from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field


class IssueType(StrEnum):
    ITEM_FALTANDO = "item_faltando"
    ITEM_ERRADO = "item_errado"
    NAO_ENTREGUE = "nao_entregue"
    QUALIDADE = "qualidade"
    ATRASO = "atraso"
    OUTRO = "outro"


class PaymentMethod(StrEnum):
    CARTAO = "cartao"
    PIX = "pix"
    VALE_REFEICAO = "vale_refeicao"
    SALDO_APP = "saldo_app"
    DINHEIRO = "dinheiro"


class Responsible(StrEnum):
    RESTAURANTE = "restaurante"
    ENTREGADOR = "entregador"
    PLATAFORMA = "plataforma"
    INDETERMINADO = "indeterminado"


class Action(StrEnum):
    REEMBOLSAR = "reembolsar"
    NEGAR = "negar"
    PEDIR_INFO = "pedir_info"
    ESCALAR = "escalar_humano"


class OrderItem(BaseModel):
    sku: str
    name: str
    qty: int = Field(gt=0)
    unit_price: Decimal


class Order(BaseModel):
    order_id: str
    customer_id: str
    merchant_id: str
    courier_id: str | None = None
    items: list[OrderItem]
    delivery_fee: Decimal
    service_fee: Decimal
    payment_method: PaymentMethod
    status: Literal["entregue", "cancelado", "em_rota", "nao_entregue"]
    created_at: datetime
    delivered_at: datetime | None = None
    eta_minutes: int | None = None

    @property
    def items_total(self) -> Decimal:
        return sum((i.unit_price * i.qty for i in self.items), Decimal("0"))


class Ticket(BaseModel):
    ticket_id: str
    customer_id: str
    order_id: str
    message: str = Field(max_length=4000)
    attachment_urls: list[str] = []
    created_at: datetime


class AffectedItem(BaseModel):
    sku: str
    qty: int = Field(gt=0)  # quantidade com problema, não a comprada


class ExtractedFacts(BaseModel):
    """O que o LLM extrai da mensagem. Só fatos, nenhuma decisão."""
    issue_type: IssueType
    affected_items: list[AffectedItem] = []
    customer_wants: Literal["reembolso", "reenvio", "informacao", "nao_informado"]
    prefers_app_credit: bool = False
    has_photo_evidence: bool = False
    summary: str = Field(max_length=300)


def affected_amount(order: "Order", facts: ExtractedFacts) -> Decimal:
    """Valor dos itens afetados, limitado à quantidade realmente comprada."""
    bought = {i.sku: i for i in order.items}
    total = Decimal("0")
    for a in facts.affected_items:
        if (item := bought.get(a.sku)) is not None:
            total += item.unit_price * min(a.qty, item.qty)
    return total


class RiskSignals(BaseModel):
    """Sinais de risco que a triagem usa e que o pedido/chamado não trazem.

    Não há acesso a dados reais: sempre vêm de um provider fake com dados sintéticos.
    """
    meses_conta: int = Field(ge=0)
    reembolsos_90d: int = Field(ge=0)
    reclamacoes_loja_semana: int = Field(ge=0)
    distancia_gps_m: float = Field(ge=0)
    # Foto verificada por um sistema (não o "cliente disse que mandou foto" do LLM).
    foto_compativel: Literal[0, 1] = 0


class TriageResult(BaseModel):
    """Saída da triagem normalizada para o agente.

    A triagem real devolve {score, faixa, acao, motivos}; o adapter converte:
    - eligible: sempre True (a triagem nunca nega; risco sai em risk_flags)
    - confidence: 1 - score (só para auditoria; a política usa a faixa)
    - risk_flags: faixa média/alta, GPS próximo, triagem indisponível...
    """
    eligible: bool
    confidence: float = Field(ge=0, le=1)
    reason_code: str
    suggested_amount: Decimal
    risk_flags: list[str] = []
    score: float | None = Field(default=None, ge=0, le=1)  # P(fraude) crua da triagem
    reasons: list[str] = []  # "motivos" da triagem, para auditoria e atendente humano


class Decision(BaseModel):
    action: Action
    amount: Decimal = Decimal("0")
    refund_to: PaymentMethod | None = None
    responsible: Responsible = Responsible.INDETERMINADO
    reason_code: str
    rule_trace: list[str] = []   # quais regras dispararam, para auditoria


class AgentReply(BaseModel):
    ticket_id: str
    message: str
    decision: Decision
    facts: ExtractedFacts | None = None
    triage: TriageResult | None = None  # para auditoria e para o atendente humano
    trace_id: str
