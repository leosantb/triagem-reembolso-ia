from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

from src.resumo_llm import gerar_resumo
from src.triagem import triar

app = FastAPI(title="Triagem de reembolso com IA")


class Caso(BaseModel):
    meses_conta: int = Field(ge=0)
    reembolsos_90d: int = Field(ge=0)
    reclamacoes_loja_semana: int = Field(ge=0)
    valor_pedido: float = Field(gt=0)
    atraso_min: int = Field(ge=0)
    distancia_gps_m: float = Field(ge=0)
    foto_compativel: Literal[0, 1] = 0  # ignorada quando o pedido não foi entregue
    tipo_problema: Literal["item_faltando", "comida_estragada", "nao_entregue", "pedido_errado"]


@app.post("/triagem")
def analisar(caso: Caso) -> dict:
    dados = caso.model_dump()
    resultado = triar(dados)
    resultado["resumo"] = gerar_resumo(dados, resultado)
    return resultado