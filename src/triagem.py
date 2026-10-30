from pathlib import Path

import joblib
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
MODELO = joblib.load(RAIZ / "modelos" / "modelo_risco.joblib")

LIMITE_BAIXO = 0.30  # abaixo disso: aprova na hora
LIMITE_ALTO = 0.70   # acima disso: investigação humana
PESO_MINIMO = 0.2    # contribuições menores que isso não viram motivo

# Como descrever cada característica em português
TEXTOS = {
    "num__reembolsos_90d": lambda c: f"{c['reembolsos_90d']} reembolso(s) nos últimos 90 dias",
    "num__meses_conta": lambda c: f"conta com {c['meses_conta']} meses",
    "num__reclamacoes_loja_semana": lambda c: (
        f"loja com {c['reclamacoes_loja_semana']} reclamação(ões) nesta semana"
    ),
    "num__valor_pedido": lambda c: f"pedido de R$ {c['valor_pedido']:.2f}".replace(".", ","),
    "num__atraso_min": lambda c: f"atraso de {c['atraso_min']} minutos",
    "num__distancia_gps_m": lambda c: f"GPS a {c['distancia_gps_m']:.0f} m do endereço",
    "num__foto_compativel": lambda c: (
        "a foto confirma o problema" if c["foto_compativel"] == 1
        else "a foto não confirma o problema"
    ),
}


def preparar_caso(caso: dict) -> dict:
    caso = dict(caso)  # faz uma cópia, para não alterar o original
    if caso["tipo_problema"] == "nao_entregue":
        caso["foto_compativel"] = 0  # foto não se aplica: mesmo valor usado no treino
    return caso


def calcular_contribuicoes(caso: dict) -> dict:
    preparo = MODELO.named_steps["preparo"]
    classificador = MODELO.named_steps["classificador"]
    valores = preparo.transform(pd.DataFrame([caso]))
    if hasattr(valores, "toarray"):
        valores = valores.toarray()
    nomes = preparo.get_feature_names_out()
    return dict(zip(nomes, valores[0] * classificador.coef_[0]))


def gerar_motivos(caso: dict) -> list[str]:
    if not hasattr(MODELO.named_steps["classificador"], "coef_"):
        return ["Explicação detalhada disponível apenas para a regressão logística."]

    contribuicoes = calcular_contribuicoes(caso)
    ignorar = set()
    if caso["tipo_problema"] == "nao_entregue":
        ignorar.add("num__foto_compativel")  # foto não se aplica

    fatores = [
        (nome, valor) for nome, valor in contribuicoes.items()
        if nome in TEXTOS and nome not in ignorar and abs(valor) >= PESO_MINIMO
    ]
    fatores.sort(key=lambda fator: abs(fator[1]), reverse=True)  # os mais fortes primeiro

    motivos = []
    for nome, valor in fatores[:4]:
        efeito = "Aumenta a suspeita" if valor > 0 else "Reduz a suspeita"
        motivos.append(f"{efeito}: {TEXTOS[nome](caso)}.")

    if caso["tipo_problema"] == "nao_entregue" and caso["distancia_gps_m"] < 50:
        motivos.append("Atenção: o GPS indica que o entregador esteve a menos de 50 m do endereço.")
    if not motivos:
        motivos.append("Nenhum fator se destacou: o caso está dentro do padrão.")
    return motivos


def triar(caso: dict) -> dict:
    caso = preparar_caso(caso)
    score = float(MODELO.predict_proba(pd.DataFrame([caso]))[0, 1])
    if score < LIMITE_BAIXO:
        faixa, acao = "baixo", "Aprovar o reembolso automaticamente"
    elif score < LIMITE_ALTO:
        faixa, acao = "medio", "Enviar para atendente humano com resumo"
    else:
        faixa, acao = "alto", "Enviar para investigação humana"
    return {"score": round(score, 3), "faixa": faixa, "acao": acao,
            "motivos": gerar_motivos(caso)}


if __name__ == "__main__":
    exemplo = {
        "meses_conta": 36, "reembolsos_90d": 0, "reclamacoes_loja_semana": 8,
        "valor_pedido": 45.0, "atraso_min": 25, "distancia_gps_m": 20,
        "foto_compativel": 1, "tipo_problema": "comida_estragada",
    }
    print(triar(exemplo))