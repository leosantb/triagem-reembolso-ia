"""Tela do agente de atendimento. Projeto de estudo com dados sintéticos.

Dois modos:
- API (AGENT_URL definida, como no docker compose): chama POST {AGENT_URL}/tickets; o LLM
  local extrai os fatos da mensagem e redige a resposta.
- Demo online (sem AGENT_URL, ex.: Streamlit Cloud): agente e triagem rodam neste processo,
  sem LLM e sem chave. Os fatos vêm do formulário e a resposta usa o texto padrão.
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import streamlit as st

# Na demo online o pacote do agente não é instalado: importa direto de agente-atendimento/src.
_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from agente.adapters.fake_orders import FakeOrderRepository  # noqa: E402
from agente.domain.models import (  # noqa: E402
    AffectedItem, ExtractedFacts, IssueType, Ticket,
)
from agente.policy import format_brl  # noqa: E402

AGENT_URL = os.environ.get("AGENT_URL", "").rstrip("/")
MODO_API = bool(AGENT_URL)
TIMEOUT_S = float(os.environ.get("AGENT_TIMEOUT_S", "300"))

PEDIDOS = {
    "P-1001": ("C-1", "Cliente antigo · triagem baixa",
               "Pedi 2 X-Burger e veio só 1, quero meu dinheiro de volta",
               IssueType.ITEM_FALTANDO, {"X-BURGER": 1}),
    "P-1002": ("C-2", "Conta recente com reembolsos · triagem média",
               "Meu poke não veio no pedido", IssueType.ITEM_FALTANDO, {"POKE": 1}),
    "P-1003": ("C-3", "Não entregue com GPS no endereço · triagem alta",
               "A pizza nunca chegou, quero o dinheiro de volta", IssueType.NAO_ENTREGUE, {}),
    "P-1004": ("C-4", "Não entregue, cliente antigo · triagem baixa",
               "Meu pedido não foi entregue, quero reembolso", IssueType.NAO_ENTREGUE, {}),
}

TIPOS = {
    IssueType.ITEM_FALTANDO: "Item faltando",
    IssueType.ITEM_ERRADO: "Item errado",
    IssueType.QUALIDADE: "Qualidade (estragado, frio...)",
    IssueType.NAO_ENTREGUE: "Pedido não entregue",
    IssueType.ATRASO: "Só atraso",
    IssueType.OUTRO: "Outro / não sei dizer",
}
_TIPOS_COM_ITENS = {IssueType.ITEM_FALTANDO, IssueType.ITEM_ERRADO, IssueType.QUALIDADE}

ACOES = {
    "reembolsar": (st.success, "Reembolso aprovado"),
    "negar": (st.error, "Reembolso negado"),
    "pedir_info": (st.info, "Pedir mais informações ao cliente"),
    "escalar_humano": (st.warning, "Encaminhado para uma pessoa do time"),
}


@st.cache_resource(show_spinner="Preparando o modelo da triagem pela primeira vez...")
def demo_agent():
    from agente.config import Settings
    from agente.demo import build_demo_agent
    return build_demo_agent(Settings())


st.set_page_config(page_title="Agente de atendimento", page_icon="💬")
st.title("Agente de atendimento")
st.caption("Projeto de estudo com dados sintéticos. Sem ligação com o iFood.")
if not MODO_API:
    st.info(
        "**Demo online:** o modelo de risco e as regras rodam de verdade, mas sem LLM. "
        "Você informa os fatos do chamado no formulário (localmente, um LLM os extrai da "
        "mensagem) e a resposta usa o texto padrão."
    )

order_id = st.selectbox(
    "Pedido", list(PEDIDOS), format_func=lambda o: PEDIDOS[o][1])
customer_id, _, exemplo, tipo_padrao, itens_padrao = PEDIDOS[order_id]

order = asyncio.run(FakeOrderRepository().get(order_id))
with st.expander("Ver pedido", expanded=True):
    st.write(f"Status: **{order.status}** · pagamento: **{order.payment_method.value}**")
    for i in order.items:
        st.write(f"- {i.qty}× {i.name} (`{i.sku}`) — {format_brl(i.unit_price)}")
    st.write(f"Entrega {format_brl(order.delivery_fee)} · serviço {format_brl(order.service_fee)}")

message = st.text_area("Mensagem do cliente", value=exemplo, key=f"msg-{order_id}", height=100)

facts = None
if not MODO_API:
    st.subheader("Fatos do chamado")
    tipo = st.selectbox("Tipo de problema", list(TIPOS), format_func=TIPOS.get,
                        index=list(TIPOS).index(tipo_padrao), key=f"tipo-{order_id}")
    afetados: list[AffectedItem] = []
    if tipo in _TIPOS_COM_ITENS:
        st.write("Quantas unidades vieram com problema?")
        for i in order.items:
            qtd = st.number_input(i.name, 0, i.qty, itens_padrao.get(i.sku, 0),
                                  key=f"qtd-{order_id}-{i.sku}")
            if qtd:
                afetados.append(AffectedItem(sku=i.sku, qty=qtd))
    foto = tipo == IssueType.QUALIDADE and st.checkbox(
        "O cliente enviou foto", key=f"foto-{order_id}")
    saldo = st.checkbox("O cliente pediu o valor como saldo no app", key=f"saldo-{order_id}")
    facts = ExtractedFacts(
        issue_type=tipo, affected_items=afetados, customer_wants="reembolso",
        prefers_app_credit=saldo, has_photo_evidence=bool(foto),
        summary=message[:300] or TIPOS[tipo],
    )

if st.button("Enviar chamado", type="primary"):
    ticket_id = f"T-{uuid.uuid4().hex[:8]}"
    try:
        with st.spinner("O agente está analisando o chamado..."):
            if MODO_API:
                import httpx
                resp = httpx.post(
                    f"{AGENT_URL}/tickets", timeout=TIMEOUT_S,
                    json={"ticket_id": ticket_id, "customer_id": customer_id,
                          "order_id": order_id, "message": message})
                resp.raise_for_status()
                r = resp.json()
            else:
                ticket = Ticket(ticket_id=ticket_id, customer_id=customer_id,
                                order_id=order_id, message=message,
                                created_at=datetime.now(timezone.utc))
                r = asyncio.run(demo_agent().handle(ticket, facts_override=facts)) \
                    .model_dump(mode="json")
    except Exception as exc:  # noqa: BLE001 - mostra qualquer falha na tela
        st.error(f"Não foi possível analisar o chamado: {exc}")
        st.stop()

    d = r["decision"]
    show, label = ACOES.get(d["action"], (st.write, d["action"]))
    extra = ""
    if d["action"] == "reembolsar":
        extra = f": {format_brl(Decimal(d['amount']))} → {d['refund_to']}"
    show(f"{label}{extra}")

    st.subheader("Resposta ao cliente")
    st.write(r["message"])

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Decisão")
        st.write(f"Motivo: `{d['reason_code']}`")
        st.write(f"Responsável: `{d['responsible']}`")
        st.write("Regras: " + " → ".join(f"`{x}`" for x in d["rule_trace"]))
    with col2:
        st.subheader("Triagem")
        t = r.get("triage")
        if t is None:
            st.write("Não executada.")
        else:
            if t.get("score") is not None:
                st.metric("Score de risco (P(fraude))", f"{t['score']:.3f}")
            st.write(f"Resultado: `{t['reason_code']}`")
            if t["risk_flags"]:
                st.write("Alertas: " + ", ".join(f"`{f}`" for f in t["risk_flags"]))
            for m in t.get("reasons", []):
                st.write(f"- {m}")

    with st.expander("Fatos usados na decisão"):
        st.json(r.get("facts"))
    st.caption(f"trace_id {r['trace_id']}")
