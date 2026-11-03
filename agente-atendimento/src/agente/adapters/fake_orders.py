"""Pedidos sintéticos para desenvolver e testar sem sistema real. Nenhum dado real."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from agente.domain.models import Order, OrderItem, PaymentMethod

_NOW = datetime.now(timezone.utc)

_ORDERS = {
    # Exemplo do guia. Cliente antigo, triagem: faixa baixa.
    "P-1001": Order(
        order_id="P-1001", customer_id="C-1", merchant_id="M-1", courier_id="E-1",
        items=[
            OrderItem(sku="X-BURGER", name="X-Burger", qty=2, unit_price=Decimal("29.90")),
            OrderItem(sku="FRITAS", name="Batata frita M", qty=1, unit_price=Decimal("14.00")),
        ],
        delivery_fee=Decimal("7.99"), service_fee=Decimal("0.99"),
        payment_method=PaymentMethod.PIX, status="entregue",
        created_at=_NOW - timedelta(minutes=70), delivered_at=_NOW - timedelta(minutes=10),
        eta_minutes=40,
    ),
    # Conta recente com reembolsos recentes. Triagem: faixa média.
    "P-1002": Order(
        order_id="P-1002", customer_id="C-2", merchant_id="M-2", courier_id="E-2",
        items=[OrderItem(sku="POKE", name="Poke de salmão", qty=1, unit_price=Decimal("45.00"))],
        delivery_fee=Decimal("5.99"), service_fee=Decimal("0.99"),
        payment_method=PaymentMethod.CARTAO, status="entregue",
        created_at=_NOW - timedelta(minutes=60), delivered_at=_NOW - timedelta(minutes=5),
        eta_minutes=45,
    ),
    # "Não entregue" com GPS do entregador no endereço e conta nova. Triagem: faixa alta.
    "P-1003": Order(
        order_id="P-1003", customer_id="C-3", merchant_id="M-1", courier_id="E-3",
        items=[OrderItem(sku="PIZZA-G", name="Pizza grande", qty=1, unit_price=Decimal("58.00"))],
        delivery_fee=Decimal("6.99"), service_fee=Decimal("0.99"),
        payment_method=PaymentMethod.CARTAO, status="nao_entregue",
        created_at=_NOW - timedelta(minutes=50), eta_minutes=50,
    ),
    # Não entregue de verdade, cliente antigo. Triagem: faixa baixa.
    "P-1004": Order(
        order_id="P-1004", customer_id="C-4", merchant_id="M-3", courier_id="E-4",
        items=[OrderItem(sku="MARMITA", name="Marmita executiva", qty=2,
                         unit_price=Decimal("21.00"))],
        delivery_fee=Decimal("4.99"), service_fee=Decimal("0.99"),
        payment_method=PaymentMethod.VALE_REFEICAO, status="nao_entregue",
        created_at=_NOW - timedelta(minutes=75), eta_minutes=40,
    ),
}


class FakeOrderRepository:
    async def get(self, order_id: str) -> Order | None:
        return _ORDERS.get(order_id)
