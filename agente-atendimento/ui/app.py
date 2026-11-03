"""Tela local do agente de atendimento. Chama POST {AGENT_URL}/tickets.

Projeto de estudo com dados sintéticos. Sem ligação com o iFood.
"""
import asyncio
import os
import uuid
from decimal import Decimal

import httpx
import streamlit as st

from agente.adapters.fake_orders import FakeOrderRepository
from agente.policy import format_brl

AGENT_URL = os.environ.get("AGENT_URL", "http://localhost:8000").rstrip("/")
TIMEOUT_S = float(os.environ.get("AGENT_TIMEOUT_S", "300"))  # LLM 7B em CPU pode demorar

PEDIDOS = {
    "P-1001": ("C-1", "Cliente antigo · triagem baixa",
               "Pedi 2 X-Burger e veio só 1, quero meu dinheiro de volta"),
    "P-1002": ("C-2", "Conta recente com reembolsos · triagem média",
               "Meu poke não veio no pedido"),
    "P-1003": ("C-3", "Não entregue com GPS no endereço · triagem alta",
               "A pizza nunca chegou, quero o dinheiro de volta"),
    "P-1004": ("C-4", "Não entregue, cliente antigo · triagem baixa",
               "Meu pedido não foi entregue, quero reembolso"),
}

ACOES = {
    "reembolsar": (st.success, "Reembolso aprovado"),
    "negar": (st.error, "Reembolso negado"),
    "pedir_info": (st.info, "Pedir mais informações ao cliente"),
    "escalar_humano": (st.warning, "Encaminhado para uma pessoa do time"),
}

st.set_page_config(page_title="Agente de atendimento", page_icon="💬")
st.title("Agente de atendimento")
st.caption("Projeto de estudo com dados sintéticos. Sem ligação com o iFood.")

order_id = st.selectbox(
    "Pedido", list(PEDIDOS), format_func=lambda o: PEDIDOS[o][1])
customer_id, _, exemplo = PEDIDOS[order_id]

order = asyncio.run(FakeOrderRepository().get(order_id))
with st.expander("Ver pedido", expanded=True):
    st.write(f"Status: **{order.status}** · pagamento: **{order.payment_method.value}**")
    for i in order.items:
        st.write(f"- {i.qty}× {i.name} (`{i.sku}`) — {format_brl(i.unit_price)}")
    st.write(f"Entrega {format_brl(order.delivery_fee)} · serviço {format_brl(order.service_fee)}")

message = st.text_area("Mensagem do cliente", value=exemplo, key=f"msg-{order_id}", height=100)

if st.button("Enviar chamado", type="primary"):
    payload = {"ticket_id": f"T-{uuid.uuid4().hex[:8]}", "customer_id": customer_id,
               "order_id": order_id, "message": message}
    try:
        with st.spinner("O agente está analisando o chamado..."):
            resp = httpx.post(f"{AGENT_URL}/tickets", json=payload, timeout=TIMEOUT_S)
            resp.raise_for_status()
            r = resp.json()
    except httpx.HTTPError as exc:
        st.error(f"Não foi possível falar com o agente em {AGENT_URL}: {exc}")
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

    with st.expander("Fatos extraídos pelo LLM"):
        st.json(r.get("facts"))
    st.caption(f"trace_id {r['trace_id']}")
