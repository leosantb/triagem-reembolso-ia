from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

RAIZ = Path(__file__).resolve().parents[1]

NUMERICAS = [
    "meses_conta", "reembolsos_90d", "reclamacoes_loja_semana",
    "valor_pedido", "atraso_min", "distancia_gps_m", "foto_compativel",
]
CATEGORICAS = ["tipo_problema"]

df = pd.read_csv(RAIZ / "data" / "reembolsos.csv")
X = df[NUMERICAS + CATEGORICAS]
y = df["fraude"]

# 80% para treinar, 20% guardados para testar com casos que o modelo nunca viu
X_treino, X_teste, y_treino, y_teste = train_test_split(
    X, y, test_size=0.2, random_state=42, stratify=y
)

modelos = {
    "Regressão logística": LogisticRegression(max_iter=1000, class_weight="balanced"),
    "Floresta aleatória": RandomForestClassifier(
        n_estimators=200, class_weight="balanced", random_state=42
    ),
}

treinados = {}
for nome, classificador in modelos.items():
    preparo = ColumnTransformer([
        ("num", StandardScaler(), NUMERICAS),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAS),
    ])
    modelo = Pipeline([("preparo", preparo), ("classificador", classificador)])
    modelo.fit(X_treino, y_treino)
    treinados[nome] = modelo

    print(f"===== {nome} =====")
    print(classification_report(y_teste, modelo.predict(X_teste),
                                target_names=["legítimo", "fraude"]))

ESCOLHIDO = "Regressão logística"  # troque depois de comparar os resultados

(RAIZ / "modelos").mkdir(exist_ok=True)
joblib.dump(treinados[ESCOLHIDO], RAIZ / "modelos" / "modelo_risco.joblib")
print(f"Modelo salvo: {ESCOLHIDO}")