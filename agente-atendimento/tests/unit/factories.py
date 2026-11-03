"""Fábricas de objetos de teste. Todos os dados são sintéticos."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from agente.domain.models import (
    AffectedItem, ExtractedFacts, IssueType, Order, OrderItem, PaymentMethod, RiskSignals,
    Ticket, TriageResult,
)

T0 = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)


def order(**kw) -> Order:
    base = dict(
        order_id="P", customer_id="C", merchant_id="M", courier_id="E",
        items=[OrderItem(sku="X", name="X-Burger", qty=2, unit_price=Decimal("29.90"))],
        delivery_fee=Decimal("7.99"), service_fee=Decimal("0.99"),
        payment_method=PaymentMethod.PIX, status="entregue",
        created_at=T0, delivered_at=T0 + timedelta(minutes=50), eta_minutes=40,
    )
    return Order(**{**base, **kw})


def facts(**kw) -> ExtractedFacts:
    base = dict(issue_type=IssueType.ITEM_FALTANDO, affected_items=[AffectedItem(sku="X", qty=1)],
                customer_wants="reembolso", summary="faltou 1 lanche")
    return ExtractedFacts(**{**base, **kw})


def triage(**kw) -> TriageResult:
    base = dict(eligible=True, confidence=0.9, reason_code="ok", suggested_amount=Decimal("29.90"))
    return TriageResult(**{**base, **kw})


def signals(**kw) -> RiskSignals:
    base = dict(meses_conta=36, reembolsos_90d=0, reclamacoes_loja_semana=8,
                distancia_gps_m=20.0, foto_compativel=1)
    return RiskSignals(**{**base, **kw})


def ticket(**kw) -> Ticket:
    base = dict(ticket_id="T", customer_id="C", order_id="P", message="faltou 1 lanche",
                created_at=T0)
    return Ticket(**{**base, **kw})
