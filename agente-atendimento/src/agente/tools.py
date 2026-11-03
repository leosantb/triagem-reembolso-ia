from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

from agente.domain.models import Order, Ticket
from agente.ports import OrderRepository

ToolFn = Callable[..., Awaitable[dict[str, Any]]]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[dict[str, Any], ToolFn]] = {}

    def register(self, name: str, description: str, params: dict[str, Any], fn: ToolFn) -> None:
        schema = {
            "type": "function",
            "function": {"name": name, "description": description, "parameters": params},
        }
        self._tools[name] = (schema, fn)

    @property
    def schemas(self) -> list[dict[str, Any]]:
        return [s for s, _ in self._tools.values()]

    async def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in self._tools:
            return {"erro": f"ferramenta desconhecida: {name}"}
        _, fn = self._tools[name]
        try:
            return await fn(**args)
        except TypeError as exc:  # argumentos inventados pelo modelo
            return {"erro": f"argumentos inválidos: {exc}"}


def order_view(order: Order) -> dict[str, Any]:
    """Visão do pedido sem PII: o LLM não precisa de endereço, CPF ou cartão."""
    return {
        "status": order.status,
        "itens": [
            {"sku": i.sku, "nome": i.name, "qtd": i.qty, "preco": str(i.unit_price)}
            for i in order.items
        ],
        "taxa_entrega": str(order.delivery_fee),
        "pagamento": order.payment_method.value,
    }


def build_tools(orders: OrderRepository, ticket: Ticket) -> ToolRegistry:
    """Só ferramentas de leitura, presas ao pedido do chamado (sem order_id como argumento)."""
    reg = ToolRegistry()
    no_params = {"type": "object", "properties": {}}

    async def consultar_pedido() -> dict[str, Any]:
        order = await orders.get(ticket.order_id)
        return order_view(order) if order else {"erro": "pedido não encontrado"}

    async def consultar_entrega() -> dict[str, Any]:
        order = await orders.get(ticket.order_id)
        if not order:
            return {"erro": "pedido não encontrado"}
        promised = order.created_at.timestamp() / 60 + (order.eta_minutes or 0)
        end = (order.delivered_at or datetime.now(timezone.utc)).timestamp() / 60
        return {
            "status": order.status,
            "entregue_em": order.delivered_at.isoformat() if order.delivered_at else None,
            "minutos_de_atraso": max(0, round(end - promised)),
        }

    reg.register("consultar_pedido", "Itens, valores e forma de pagamento do pedido.",
                 no_params, consultar_pedido)
    reg.register("consultar_entrega", "Status da entrega e atraso em minutos.",
                 no_params, consultar_entrega)
    return reg
