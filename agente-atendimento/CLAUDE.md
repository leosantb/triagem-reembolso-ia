# Contexto
- Raiz do repositório (`src/`, `app/`, `modelos/`, `data/`, `tests/`, `Dockerfile`): projeto
  existente de triagem. NÃO alterar sem pedir. Ponto de entrada: `src/triagem.py::triar(caso)`
  e `POST /triagem` em `src/api.py`.
- `agente-atendimento/`: novo agente. Especificação em
  `agente-atendimento/docs/Agente de Atendimento iFood — Guia de Implementação.md`.

# Decisões
- Limite de confiança: vale o da triagem (`LIMITE_BAIXO = 0.30` → aprova se score < 0,30,
  ou seja, confiança > 0,70). O agente usa a `faixa` da triagem e não aplica um segundo limite.
- Sinais de risco (histórico do cliente, reclamações da loja, GPS, foto) são sempre fakes
  sintéticos: não há acesso a dados reais.

# Ambiente
- Venv do agente FORA do repositório: `~/.venvs/agente-atendimento`
  (um `.venv` dentro do repo entraria no `COPY . .` da imagem da triagem).
- Instalar: `pip install -e ".[dev,local-triage]"` dentro de `agente-atendimento/`.
- Testes: `pytest` dentro de `agente-atendimento/` (unit + integração com a triagem real).
  A triagem continua com os seus: `pytest` na raiz, com `venv/` da raiz.
- Triagem por `TRIAGE_MODE`: `stub` | `local` (carrega `src/triagem.py` por caminho de arquivo,
  sem registrar o pacote `src`) | `http` (serviço `triagem` no docker-compose).

# Regras
- Python 3.11, Pydantic v2, FastAPI, Ollama via Docker.
- Dinheiro sempre em Decimal. Nenhuma decisão de reembolso dentro de prompt de LLM:
  decisões ficam em policy.py.
- Ferramentas expostas ao LLM são só de leitura.
- Todo código novo vem com teste em tests/unit. Rode `pytest` antes de concluir.
- Não use dados reais de clientes em fixtures ou testes.