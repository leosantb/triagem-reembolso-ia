"""Agente para a demo online (Streamlit Cloud): tudo em um processo, sem LLM e sem chave.

Mesmo esquema da demo da triagem: o modelo de risco roda de verdade; o que dependeria de
LLM usa o texto padrão. Os fatos do chamado vêm de um formulário em vez da extração.
"""
import subprocess
import sys
from pathlib import Path

from agente.adapters.dev import InMemoryDecisionStore
from agente.adapters.fake_orders import FakeOrderRepository
from agente.adapters.fake_signals import FakeRiskSignalsProvider
from agente.adapters.triage import LocalTriageAdapter, load_local_triage
from agente.agent import SupportAgent
from agente.config import Settings


def ensure_triage_model(triage_root: Path) -> Path:
    """Gera os dados e treina o modelo da triagem se ainda não existirem.

    Roda os próprios scripts da triagem (python -m src.gerar_dados / src.treinar) em um
    subprocesso com cwd na raiz dela: nenhum código da triagem é alterado e o pacote `src`
    não entra no processo do agente.
    """
    model = Path(triage_root) / "modelos" / "modelo_risco.joblib"
    if not model.is_file():
        for module in ("src.gerar_dados", "src.treinar"):
            subprocess.run(
                [sys.executable, "-m", module], cwd=triage_root, check=True,
                stdout=subprocess.DEVNULL,
            )
    return model


def build_demo_agent(settings: Settings) -> SupportAgent:
    ensure_triage_model(settings.triage_root)
    return SupportAgent(
        llm=None,  # sem LLM na demo online: fatos do formulário + resposta padrão
        orders=FakeOrderRepository(),
        triage=LocalTriageAdapter(load_local_triage(settings.triage_root),
                                  FakeRiskSignalsProvider()),
        store=InMemoryDecisionStore(),
        settings=settings,
    )
