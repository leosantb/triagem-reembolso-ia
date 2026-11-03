from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz do repositório = raiz do projeto de triagem (src/triagem.py, modelos/).
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ollama_host: str = "http://localhost:11434"
    llm_model: str = "qwen2.5:7b"
    llm_temperature: float = 0.1
    llm_timeout_s: float = 60.0
    max_tool_rounds: int = 6

    # triagem
    # stub  -> StubTriage (sem o projeto de triagem)
    # local -> LocalTriageAdapter, importa src/triagem.py do repositório (extra local-triage)
    # http  -> HttpTriageAdapter, chama POST {triage_url}/triagem (serviço no docker-compose)
    triage_mode: Literal["stub", "local", "http"] = "stub"
    triage_url: str = "http://localhost:8001"
    triage_timeout_s: float = 10.0
    triage_root: Path = _REPO_ROOT

    # política
    # Não há limite de confiança aqui: vale a faixa da própria triagem
    # (score < 0,30 aprova; acima disso vai para humano). Ver CLAUDE.md, "Decisões".
    auto_approve_limit_brl: float = 80.0


settings = Settings()
