"""Sinais de risco sintéticos (histórico do cliente, loja, GPS, foto).

Não há acesso a dados reais: este provider é a implementação definitiva por enquanto.
Os valores foram calibrados contra a triagem real para cobrir as três faixas.
"""
from agente.domain.models import Order, RiskSignals

_SIGNALS = {
    # baixo (score ~0,05)
    "P-1001": RiskSignals(meses_conta=36, reembolsos_90d=0, reclamacoes_loja_semana=8,
                          distancia_gps_m=20.0, foto_compativel=1),
    # médio (score ~0,67)
    "P-1002": RiskSignals(meses_conta=8, reembolsos_90d=2, reclamacoes_loja_semana=3,
                          distancia_gps_m=150.0, foto_compativel=1),
    # alto (score ~0,99); GPS a 10 m num "não entregue"
    "P-1003": RiskSignals(meses_conta=1, reembolsos_90d=6, reclamacoes_loja_semana=0,
                          distancia_gps_m=10.0, foto_compativel=0),
    # baixo (score ~0,07); entregador longe do endereço
    "P-1004": RiskSignals(meses_conta=40, reembolsos_90d=0, reclamacoes_loja_semana=6,
                          distancia_gps_m=900.0, foto_compativel=0),
}


class FakeRiskSignalsProvider:
    async def get(self, order: Order) -> RiskSignals | None:
        return _SIGNALS.get(order.order_id)
