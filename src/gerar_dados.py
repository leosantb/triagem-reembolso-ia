from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(42)  # semente fixa: sempre gera os mesmos dados
N = 5000

TIPOS = ["item_faltando", "comida_estragada", "nao_entregue", "pedido_errado"]

df = pd.DataFrame({
    "meses_conta": rng.integers(0, 60, N),
    "reembolsos_90d": rng.poisson(0.6, N),
    "reclamacoes_loja_semana": rng.poisson(3, N),
    "valor_pedido": rng.uniform(20, 200, N).round(2),
    "atraso_min": rng.integers(0, 60, N),
    "distancia_gps_m": rng.exponential(80, N).round(0),
    "foto_compativel": rng.choice([1, 0], N, p=[0.8, 0.2]),
    "tipo_problema": rng.choice(TIPOS, N),
})
# Para "não entregue" não há o que fotografar: a foto não é usada
sem_foto = df["tipo_problema"] == "nao_entregue"
df.loc[sem_foto, "foto_compativel"] = 0
# Regras que deixam a fraude mais ou menos provável (documente no README)
nao_entregue_com_gps_na_porta = (
    (df["tipo_problema"] == "nao_entregue") & (df["distancia_gps_m"] < 50)
)
logit = (
    0.2
    + 0.8 * df["reembolsos_90d"]            # muitos reembolsos: mais suspeito
    - 0.04 * df["meses_conta"]              # conta antiga: menos suspeito
    - 0.25 * df["reclamacoes_loja_semana"]  # loja com muitas queixas: problema real
    + 0.006 * df["valor_pedido"]            # pedido caro: um pouco mais suspeito
    - 1.5 * df["foto_compativel"]           # foto confirma: menos suspeito
    + 1.2 * nao_entregue_com_gps_na_porta   # diz que não chegou, mas o GPS estava na porta
    - 1.2 * sem_foto                        # compensa a falta de foto (veja abaixo)
)
probabilidade = 1 / (1 + np.exp(-logit))
df["fraude"] = rng.binomial(1, probabilidade)

(RAIZ / "data").mkdir(exist_ok=True)
df.to_csv(RAIZ / "data" / "reembolsos.csv", index=False)
print(f"{N} casos gerados. Taxa de fraude: {df['fraude'].mean():.1%}")