import json
from datetime import timedelta
from decimal import Decimal

import httpx
import pytest

from agente.adapters.triage import (
    HttpTriageAdapter, LocalTriageAdapter, TRIAGE_TYPES, atraso_min, from_triage_output, to_caso,
)
from agente.domain.models import AffectedItem, IssueType

from factories import T0, facts, order, signals, ticket

TRIAGE_KEYS = {
    "meses_conta", "reembolsos_90d", "reclamacoes_loja_semana", "valor_pedido",
    "atraso_min", "distancia_gps_m", "foto_compativel", "tipo_problema",
}


class FakeSignals:
    def __init__(self, s=None, missing=False):
        self._s = s or signals()
        self._missing = missing

    async def get(self, order):
        return None if self._missing else self._s


class RecordingTriage:
    """Imita src/triagem.py::triar e guarda a entrada recebida."""

    def __init__(self, score=0.05, faixa="baixo", raises=None):
        self.calls: list[dict] = []
        self._out = {"score": score, "faixa": faixa, "acao": "x",
                     "motivos": ["Reduz a suspeita: y."]}
        self._raises = raises

    def __call__(self, caso):
        self.calls.append(caso)
        if self._raises:
            raise self._raises
        return self._out


# ---------- mapeamento de entrada ----------

def test_mapeamento_de_tipos_cobre_os_tipos_da_triagem():
    assert set(TRIAGE_TYPES.values()) == {
        "item_faltando", "pedido_errado", "nao_entregue", "comida_estragada"}
    assert TRIAGE_TYPES[IssueType.ITEM_ERRADO] == "pedido_errado"
    assert TRIAGE_TYPES[IssueType.QUALIDADE] == "comida_estragada"


def test_to_caso_tem_exatamente_os_campos_da_triagem():
    caso = to_caso(order(), facts(), signals(), ref=T0)
    assert set(caso) == TRIAGE_KEYS
    assert caso["valor_pedido"] == pytest.approx(59.80)
    assert isinstance(caso["valor_pedido"], float)


def test_foto_vem_dos_sinais_e_nunca_do_llm():
    f = facts(issue_type=IssueType.QUALIDADE, has_photo_evidence=True)
    assert to_caso(order(), f, signals(foto_compativel=0), ref=T0)["foto_compativel"] == 0


@pytest.mark.parametrize("delivered, eta, esperado", [
    (50, 40, 10),     # entregue 10 min depois do prometido
    (30, 40, 0),      # adiantado não vira atraso negativo
    (300, 40, 59),    # limitado ao máximo visto no treino
])
def test_atraso_min(delivered, eta, esperado):
    o = order(delivered_at=T0 + timedelta(minutes=delivered), eta_minutes=eta)
    assert atraso_min(o, ref=T0 + timedelta(days=1)) == esperado


def test_atraso_sem_entrega_mede_ate_o_chamado():
    o = order(status="nao_entregue", delivered_at=None, eta_minutes=40)
    assert atraso_min(o, ref=T0 + timedelta(minutes=55)) == 15


def test_atraso_sem_eta_e_zero():
    assert atraso_min(order(eta_minutes=None), ref=T0) == 0


# ---------- mapeamento de saída ----------

def _out(score, faixa):
    return {"score": score, "faixa": faixa, "acao": "x", "motivos": ["m1", "m2"]}


def test_faixa_baixa_sem_flag():
    caso = to_caso(order(), facts(), signals(), ref=T0)
    r = from_triage_output(_out(0.1, "baixo"), caso, order(), facts())
    assert r.eligible and r.risk_flags == []
    assert r.confidence == pytest.approx(0.9)
    assert r.score == 0.1 and r.reasons == ["m1", "m2"]
    assert r.reason_code == "risco_baixo"
    assert r.suggested_amount == Decimal("29.90")  # dos itens afetados, não da triagem


@pytest.mark.parametrize("faixa", ["medio", "alto"])
def test_faixa_media_e_alta_viram_flag(faixa):
    caso = to_caso(order(), facts(), signals(), ref=T0)
    r = from_triage_output(_out(0.8, faixa), caso, order(), facts())
    assert r.risk_flags == [f"risco_{faixa}"]
    assert r.eligible  # a triagem nunca nega


def test_gps_proximo_em_nao_entregue_vira_flag():
    f = facts(issue_type=IssueType.NAO_ENTREGUE, affected_items=[])
    caso = to_caso(order(), f, signals(distancia_gps_m=10), ref=T0)
    r = from_triage_output(_out(0.1, "baixo"), caso, order(), f)
    assert r.risk_flags == ["gps_proximo"]


@pytest.mark.parametrize("raw", [
    {}, {"score": 0.1}, {"score": "x", "faixa": "baixo"},
    {"score": 0.1, "faixa": "outra"}, {"score": 1.5, "faixa": "alto"},
])
def test_saida_invalida_levanta(raw):
    caso = to_caso(order(), facts(), signals(), ref=T0)
    with pytest.raises(ValueError):
        from_triage_output(raw, caso, order(), facts())


# ---------- LocalTriageAdapter ----------

async def test_local_chama_triagem_com_o_caso():
    fn = RecordingTriage()
    r = await LocalTriageAdapter(fn, FakeSignals()).evaluate(ticket(), order(), facts())
    assert len(fn.calls) == 1 and set(fn.calls[0]) == TRIAGE_KEYS
    assert r.risk_flags == [] and r.score == 0.05


async def test_outro_nao_chama_triagem_e_nao_tem_flag():
    fn = RecordingTriage()
    f = facts(issue_type=IssueType.OUTRO, affected_items=[])
    r = await LocalTriageAdapter(fn, FakeSignals()).evaluate(ticket(), order(), f)
    assert fn.calls == [] and r.risk_flags == [] and r.reason_code == "sem_triagem"


async def test_atraso_nao_chama_triagem_e_escala():
    fn = RecordingTriage()
    f = facts(issue_type=IssueType.ATRASO, affected_items=[])
    r = await LocalTriageAdapter(fn, FakeSignals()).evaluate(ticket(), order(), f)
    assert fn.calls == [] and r.risk_flags == ["tipo_sem_triagem"]


async def test_sem_sinais_escala():
    fn = RecordingTriage()
    r = await LocalTriageAdapter(fn, FakeSignals(missing=True)).evaluate(ticket(), order(), facts())
    assert fn.calls == [] and r.risk_flags == ["sinais_indisponiveis"]


async def test_erro_na_triagem_escala():
    fn = RecordingTriage(raises=RuntimeError("modelo quebrou"))
    r = await LocalTriageAdapter(fn, FakeSignals()).evaluate(ticket(), order(), facts())
    assert r.risk_flags == ["triagem_indisponivel"]


async def test_affected_items_nao_altera_quantidade_comprada():
    f = facts(affected_items=[AffectedItem(sku="X", qty=5)])  # comprou 2
    r = await LocalTriageAdapter(RecordingTriage(), FakeSignals()).evaluate(ticket(), order(), f)
    assert r.suggested_amount == Decimal("59.80")


# ---------- HttpTriageAdapter ----------

def _http(handler):
    return HttpTriageAdapter("http://triagem:8001/", FakeSignals(),
                             transport=httpx.MockTransport(handler))


async def test_http_envia_caso_e_ignora_resumo():
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["url"] = str(req.url)
        seen["body"] = json.loads(req.content)
        return httpx.Response(200, json={**_out(0.67, "medio"), "resumo": "texto do LLM"})

    r = await _http(handler).evaluate(ticket(), order(), facts())
    assert seen["url"] == "http://triagem:8001/triagem"
    assert set(seen["body"]) == TRIAGE_KEYS
    assert r.risk_flags == ["risco_medio"] and r.score == 0.67


@pytest.mark.parametrize("handler", [
    lambda req: httpx.Response(500),
    lambda req: httpx.Response(422, json={"detail": "x"}),
    lambda req: httpx.Response(200, content=b"nao e json"),
    lambda req: (_ for _ in ()).throw(httpx.ConnectTimeout("timeout")),
])
async def test_http_falha_escala(handler):
    r = await _http(handler).evaluate(ticket(), order(), facts())
    assert r.risk_flags == ["triagem_indisponivel"]
