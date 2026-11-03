"""Ponte com o projeto de triagem (raiz do repositório). O projeto de triagem NÃO é alterado.

Contrato real da triagem (src/triagem.py::triar e POST /triagem em src/api.py):

    entrada: {meses_conta, reembolsos_90d, reclamacoes_loja_semana, valor_pedido,
              atraso_min, distancia_gps_m, foto_compativel, tipo_problema}
    saída:   {score, faixa: baixo|medio|alto, acao, motivos: [str]}  (+ resumo no HTTP)

`score` é P(fraude). A triagem nunca nega: faixa baixa aprova, média/alta vão para humano.
"""
import asyncio
import importlib.util
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

from agente.domain.models import (
    ExtractedFacts, IssueType, Order, RiskSignals, Ticket, TriageResult, affected_amount,
)
from agente.ports import RiskSignalsProvider

log = structlog.get_logger()

TriageFn = Callable[[dict[str, Any]], dict[str, Any]]

# IssueType do agente -> tipo_problema da triagem. Tipos ausentes não passam pela triagem.
TRIAGE_TYPES: dict[IssueType, str] = {
    IssueType.ITEM_FALTANDO: "item_faltando",
    IssueType.ITEM_ERRADO: "pedido_errado",
    IssueType.NAO_ENTREGUE: "nao_entregue",
    IssueType.QUALIDADE: "comida_estragada",
}

_FAIXAS = {"baixo", "medio", "alto"}
GPS_PROXIMO_M = 50  # mesma regra de alerta da triagem (src/triagem.py)
ATRASO_MAX_TREINO = 59  # data/reembolsos.csv: atraso_min vai de 0 a 59 em todos os tipos


# ---------- mapeamento (funções puras, compartilhadas pelos dois adapters) ----------

def atraso_min(order: Order, ref: datetime) -> int:
    """Minutos além do prometido (created_at + eta), limitados à faixa vista no treino.

    Sem `delivered_at`, mede até `ref` (abertura do chamado), não até "agora": o resultado
    fica reproduzível para auditoria. Sem `eta_minutes` -> 0.
    """
    if order.eta_minutes is None:
        return 0
    end = order.delivered_at or ref
    late = (end - order.created_at).total_seconds() / 60 - order.eta_minutes
    return min(ATRASO_MAX_TREINO, max(0, round(late)))


def to_caso(
    order: Order, facts: ExtractedFacts, signals: RiskSignals, ref: datetime
) -> dict[str, Any]:
    """Monta a entrada da triagem. Única conversão Decimal -> float do agente."""
    return {
        "meses_conta": signals.meses_conta,
        "reembolsos_90d": signals.reembolsos_90d,
        "reclamacoes_loja_semana": signals.reclamacoes_loja_semana,
        "valor_pedido": float(order.items_total),
        "atraso_min": atraso_min(order, ref),
        "distancia_gps_m": float(signals.distancia_gps_m),
        # vem dos sinais, nunca de facts.has_photo_evidence (o que o LLM leu na mensagem)
        "foto_compativel": signals.foto_compativel,
        "tipo_problema": TRIAGE_TYPES[facts.issue_type],
    }


def from_triage_output(
    raw: dict[str, Any], caso: dict[str, Any], order: Order, facts: ExtractedFacts
) -> TriageResult:
    """Converte a saída da triagem. Formato inesperado -> ValueError."""
    try:
        score = float(raw["score"])
        faixa = raw["faixa"]
        motivos = [str(m) for m in raw.get("motivos", [])]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"saída da triagem inválida: {exc!r}") from exc
    if faixa not in _FAIXAS or not 0 <= score <= 1:
        raise ValueError(f"saída da triagem inválida: faixa={faixa!r} score={score!r}")

    flags: list[str] = []
    if faixa != "baixo":
        flags.append(f"risco_{faixa}")
    if caso["tipo_problema"] == "nao_entregue" and caso["distancia_gps_m"] < GPS_PROXIMO_M:
        flags.append("gps_proximo")

    return TriageResult(
        eligible=True,  # a triagem nunca nega
        confidence=round(1 - score, 3),
        reason_code=f"risco_{faixa}",
        suggested_amount=affected_amount(order, facts),
        risk_flags=flags,
        score=score,
        reasons=motivos,
    )


def _no_triage(order: Order, facts: ExtractedFacts, reason: str, flag: str | None) -> TriageResult:
    return TriageResult(
        eligible=True, confidence=0.0, reason_code=reason,
        suggested_amount=affected_amount(order, facts),
        risk_flags=[flag] if flag else [],
    )


class _BaseTriageAdapter:
    def __init__(self, signals: RiskSignalsProvider) -> None:
        self._signals = signals

    async def _call(self, caso: dict[str, Any]) -> dict[str, Any]:  # pragma: no cover
        raise NotImplementedError

    async def evaluate(self, ticket: Ticket, order: Order, facts: ExtractedFacts) -> TriageResult:
        tlog = log.bind(ticket_id=ticket.ticket_id, adapter=type(self).__name__)

        if facts.issue_type == IssueType.OUTRO:
            # sem triagem e sem flag: a política pede mais informação ao cliente
            return _no_triage(order, facts, "sem_triagem", None)
        if facts.issue_type not in TRIAGE_TYPES:
            # ex.: atraso. A triagem não cobre; vai para humano.
            return _no_triage(order, facts, "tipo_sem_triagem", "tipo_sem_triagem")

        signals = await self._signals.get(order)
        if signals is None:
            return _no_triage(order, facts, "sinais_indisponiveis", "sinais_indisponiveis")

        caso = to_caso(order, facts, signals, ref=ticket.created_at)
        if caso["valor_pedido"] <= 0:
            return _no_triage(order, facts, "valor_indefinido", "valor_indefinido")

        try:
            raw = await self._call(caso)
            result = from_triage_output(raw, caso, order, facts)
        except Exception as exc:  # qualquer falha da triagem -> humano, nunca decisão às cegas
            tlog.warning("triage_failed", error=repr(exc))
            return _no_triage(order, facts, "triagem_indisponivel", "triagem_indisponivel")

        tlog.info("triage_done", score=result.score, flags=result.risk_flags)
        return result


class LocalTriageAdapter(_BaseTriageAdapter):
    """Chama `triar` in-process. Para desenvolvimento e testes; o alvo é o HttpTriageAdapter."""

    def __init__(self, triage_fn: TriageFn, signals: RiskSignalsProvider) -> None:
        super().__init__(signals)
        self._triage_fn = triage_fn

    async def _call(self, caso: dict[str, Any]) -> dict[str, Any]:
        # triar é síncrona e usa pandas/sklearn: roda fora do event loop
        return await asyncio.to_thread(self._triage_fn, dict(caso))


class HttpTriageAdapter(_BaseTriageAdapter):
    """Chama POST {base_url}/triagem (src/api.py da triagem). O campo `resumo` é ignorado."""

    def __init__(
        self,
        base_url: str,
        signals: RiskSignalsProvider,
        timeout_s: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,  # injeção para testes
    ) -> None:
        super().__init__(signals)
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s
        self._transport = transport

    async def _call(self, caso: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout_s, transport=self._transport
        ) as client:
            resp = await client.post("/triagem", json=caso)
            resp.raise_for_status()
            return resp.json()


def load_local_triage(triage_root: Path) -> TriageFn:
    """Carrega `triar` de {triage_root}/src/triagem.py pelo caminho do arquivo.

    Não altera sys.path nem registra o pacote `src`. Carregar o módulo lê
    modelos/modelo_risco.joblib; exige o extra `local-triage` (mesmas versões da triagem).
    """
    path = Path(triage_root) / "src" / "triagem.py"
    if not path.is_file():
        raise FileNotFoundError(f"triagem não encontrada em {path}")
    spec = importlib.util.spec_from_file_location("_triagem_reembolso", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"não foi possível carregar {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.triar
