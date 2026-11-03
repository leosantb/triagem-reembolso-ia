"""Avaliação ponta a ponta com o LLM real. Não roda no pytest (precisa do Ollama).

    python tests/eval/run_eval.py
"""
import asyncio
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from agente.api import build_agent
from agente.domain.models import Action, Ticket

CASES = Path(__file__).parent / "cases.jsonl"


async def main() -> None:
    agent = build_agent()
    lines = CASES.read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line.strip()]
    results, latencies = [], []

    for c in rows:
        t0 = time.perf_counter()
        r = await agent.handle(Ticket(
            ticket_id=c["id"], customer_id=c.get("customer_id", "C-1"), order_id=c["order_id"],
            message=c["message"], created_at=datetime.now(timezone.utc),
        ))
        latencies.append(time.perf_counter() - t0)
        exp = c["expect"]
        ok_action = r.decision.action.value == exp["action"]
        ok_amount = "amount" not in exp or r.decision.amount == Decimal(exp["amount"])
        ok_dest = "refund_to" not in exp or (
            r.decision.refund_to is not None and r.decision.refund_to.value == exp["refund_to"])
        ok = ok_action and ok_amount and ok_dest
        false_approval = r.decision.action == Action.REEMBOLSAR and exp["action"] != "reembolsar"
        results.append((c["id"], ok, false_approval))
        if not ok:
            print(f"FALHA {c['id']}: esperado {exp}, obtido {r.decision.action.value} "
                  f"{r.decision.amount} {r.decision.refund_to} {r.decision.rule_trace}")

    n = len(results)
    latencies.sort()
    print(f"acerto: {sum(r[1] for r in results) / n:.0%}")
    print(f"aprovações indevidas: {sum(r[2] for r in results)}")
    print(f"latência p95: {latencies[max(0, int(n * 0.95) - 1)]:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
