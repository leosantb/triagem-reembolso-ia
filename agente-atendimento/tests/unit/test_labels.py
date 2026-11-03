from typing import get_args

from agente.domain.models import Order, PaymentMethod, Responsible
from agente.labels import LABELS, alert_flags, label, refund_destination
from agente.policy import _REASONS

ORDER_STATUS = Order.model_fields["status"].annotation

# Passos que a política grava em rule_trace sem estar em _REASONS
RULE_STEPS = {"valor_itens_afetados", "nao_entregue_total", "triagem_inelegivel"}
# Resultados e alertas que o adapter da triagem pode gerar
TRIAGE_CODES = {
    "risco_baixo", "risco_medio", "risco_alto", "gps_proximo", "tipo_sem_triagem",
    "triagem_indisponivel", "sinais_indisponiveis", "valor_indefinido", "sem_triagem",
}


def test_todo_codigo_gerado_tem_texto_em_portugues():
    codes = (set(_REASONS) | RULE_STEPS | TRIAGE_CODES | {r.value for r in Responsible}
             | {p.value for p in PaymentMethod} | set(get_args(ORDER_STATUS)))
    faltando = sorted(c for c in codes if c not in LABELS)
    assert faltando == []


def test_nenhum_texto_tem_sublinhado():
    assert [t for t in LABELS.values() if "_" in t] == []


def test_codigo_desconhecido_fica_legivel():
    assert label("regra_nova_qualquer") == "Regra nova qualquer"
    assert label(None) == "—"


def test_alertas_nao_repetem_nivel_de_risco():
    assert alert_flags(["risco_alto", "gps_proximo"]) == [
        "GPS indica o entregador perto do endereço"]
    assert alert_flags(["risco_medio"]) == []


def test_destino_do_reembolso():
    assert refund_destination(PaymentMethod.PIX.value) == "no Pix"
    assert refund_destination("vale_refeicao") == "no vale-refeição"
    assert refund_destination(None) == ""
