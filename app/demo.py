import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))  # deixa importar o src

import streamlit as st

from src.resumo_llm import gerar_resumo
from src.triagem import triar

st.title("Triagem de reembolso com IA")
st.caption("Projeto de estudo com dados sintéticos. Sem ligação com o iFood.")

col1, col2 = st.columns(2)
with col1:
    meses = st.number_input("Meses de conta", 0, 120, 24)
    reembolsos = st.number_input("Reembolsos nos últimos 90 dias", 0, 20, 0)
    reclamacoes = st.number_input("Reclamações da loja na semana", 0, 50, 3)
    valor = st.number_input("Valor do pedido (R$)", 1.0, 1000.0, 60.0)
with col2:
    atraso = st.number_input("Atraso (min)", 0, 180, 10)
    distancia = st.number_input("Distância do GPS ao endereço (m)", 0, 5000, 100)
    tipo = st.selectbox("Tipo de problema",
                        ["item_faltando", "comida_estragada", "nao_entregue", "pedido_errado"])
    if tipo == "nao_entregue":
        st.info("Pedido não entregue não precisa de foto: a análise usa o GPS.")
        foto = "Não"
    else:
        foto = st.radio("A foto confirma o problema?", ["Sim", "Não"])

if st.button("Analisar caso"):
    caso = {
        "meses_conta": meses, "reembolsos_90d": reembolsos,
        "reclamacoes_loja_semana": reclamacoes, "valor_pedido": valor,
        "atraso_min": atraso, "distancia_gps_m": distancia,
        "foto_compativel": 1 if foto == "Sim" else 0, "tipo_problema": tipo,
    }
    resultado = triar(caso)
    mostrar = {"baixo": st.success, "medio": st.warning, "alto": st.error}
    mostrar[resultado["faixa"]](
        f"Risco {resultado['faixa'].replace('medio', 'médio')}: "
        f"{resultado['acao']} (score {resultado['score']})"
    )
    st.subheader("Motivos")
    for motivo in resultado["motivos"]:
        st.write(f"- {motivo}")
    st.subheader("Resumo para o atendente")
    st.write(gerar_resumo(caso, resultado))