import re

import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODELO_LLM = "llama3.2"

# Traduz os nomes técnicos para português correto
TIPOS = {
    "item_faltando": "item faltando",
    "comida_estragada": "comida estragada",
    "nao_entregue": "pedido não entregue",
    "pedido_errado": "pedido errado",
}
FAIXAS = {"baixo": "baixo", "medio": "médio", "alto": "alto"}

INSTRUCOES = (
    "Você escreve resumos para atendentes de um app de delivery brasileiro. "
    "Escreva sempre em português do Brasil, com ortografia e acentuação corretas. "
    "Use frases curtas e simples, sem palavras em inglês. "
    "Use apenas as informações fornecidas: não invente dados nem números. "
    "Escreva no máximo 3 frases e termine com a sugestão de ação."
)

EXEMPLO = (
    "Exemplo de dados:\n"
    "- Problema: comida estragada, pedido de R$ 52,00\n"
    "- Risco: baixo\n"
    "- Motivos: A foto enviada confirma o problema relatado. "
    "Cliente antigo e sem reembolsos recentes.\n"
    "- Ação sugerida: aprovar o reembolso automaticamente\n"
    "Exemplo de resumo:\n"
    "Cliente antigo relata comida estragada em um pedido de R$ 52,00, "
    "e a foto confirma o problema. O risco de fraude é baixo. "
    "Sugestão: aprovar o reembolso automaticamente.\n\n"
)


def formatar_valor(valor: float) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")


def descrever_caso(caso: dict, resultado: dict) -> str:
    return (
        f"- Problema: {TIPOS[caso['tipo_problema']]}, "
        f"pedido de {formatar_valor(caso['valor_pedido'])}\n"
        f"- Risco: {FAIXAS[resultado['faixa']]}\n"
        f"- Motivos: {' '.join(resultado['motivos'])}\n"
        f"- Ação sugerida: {resultado['acao'].lower()}\n"
    )


def resumo_padrao(caso: dict, resultado: dict) -> str:
    return (
        f"Reembolso por {TIPOS[caso['tipo_problema']]}, "
        f"pedido de {formatar_valor(caso['valor_pedido'])}. "
        f"Risco {FAIXAS[resultado['faixa']]} (score {resultado['score']}). "
        f"{' '.join(resultado['motivos'])} "
        f"Sugestão: {resultado['acao'].lower()}."
    )


def resumo_valido(texto: str) -> bool:
    if not texto or len(texto) > 600:
        return False
    palavras_em_ingles = re.compile(
        r"\b(the|and|refund|customer|order|risk)\b", re.IGNORECASE
    )
    return not palavras_em_ingles.search(texto)


def gerar_resumo(caso: dict, resultado: dict) -> str:
    prompt = (
        EXEMPLO
        + "Agora escreva o resumo para estes dados:\n"
        + descrever_caso(caso, resultado)
        + "Resumo:"
    )
    try:
        resposta = requests.post(
            OLLAMA_URL,
            json={
                "model": MODELO_LLM,
                "system": INSTRUCOES,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 200},
            },
            timeout=60,
        )
        resposta.raise_for_status()
        texto = resposta.json()["response"].strip()
    except requests.RequestException:
        return resumo_padrao(caso, resultado)  # plano B: Ollama fora do ar
    if resumo_valido(texto):
        return texto
    return resumo_padrao(caso, resultado)  # plano B: resposta ruim