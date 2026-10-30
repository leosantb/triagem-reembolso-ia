from src.triagem import triar

CASO_HONESTO = {
    "meses_conta": 48, "reembolsos_90d": 0, "reclamacoes_loja_semana": 12,
    "valor_pedido": 40.0, "atraso_min": 30, "distancia_gps_m": 20,
    "foto_compativel": 1, "tipo_problema": "comida_estragada",
}
CASO_SUSPEITO = {
    "meses_conta": 1, "reembolsos_90d": 6, "reclamacoes_loja_semana": 0,
    "valor_pedido": 190.0, "atraso_min": 0, "distancia_gps_m": 10,
    "foto_compativel": 0, "tipo_problema": "nao_entregue",
}


def test_caso_honesto_e_aprovado_na_hora():
    assert triar(CASO_HONESTO)["faixa"] == "baixo"


def test_caso_suspeito_vai_para_humano():
    resultado = triar(CASO_SUSPEITO)
    assert resultado["faixa"] == "alto"
    assert "humana" in resultado["acao"]


def test_sistema_nunca_nega_sozinho():
    for caso in (CASO_HONESTO, CASO_SUSPEITO):
        assert "negar" not in triar(caso)["acao"].lower()


def test_sempre_explica_o_motivo():
    for caso in (CASO_HONESTO, CASO_SUSPEITO):
        assert len(triar(caso)["motivos"]) >= 1


def test_nao_entregue_ignora_a_foto():
    com_foto = {**CASO_SUSPEITO, "foto_compativel": 1}
    sem_foto = {**CASO_SUSPEITO, "foto_compativel": 0}
    assert triar(com_foto)["score"] == triar(sem_foto)["score"]