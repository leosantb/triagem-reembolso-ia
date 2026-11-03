import json
import uuid
from pathlib import Path
from typing import Any

import structlog
from pydantic import ValidationError

from agente.config import Settings
from agente.domain.models import (
    AgentReply, Decision, ExtractedFacts, Order, Ticket, TriageResult,
)
from agente.policy import decide, escalate, fallback_reply, reason_text, reply_is_consistent
from agente.ports import DecisionStore, LLMClient, OrderRepository, TriageService
from agente.redact import redact
from agente.tools import build_tools

log = structlog.get_logger()
_PROMPTS = Path(__file__).parent / "prompts"
EXTRACT_PROMPT = (_PROMPTS / "extract.md").read_text(encoding="utf-8")
REPLY_PROMPT = (_PROMPTS / "reply.md").read_text(encoding="utf-8")


class SupportAgent:
    def __init__(
        self,
        llm: LLMClient,
        orders: OrderRepository,
        triage: TriageService,
        store: DecisionStore,
        settings: Settings,
    ) -> None:
        self.llm, self.orders, self.triage = llm, orders, triage
        self.store, self.settings = store, settings

    async def handle(self, ticket: Ticket) -> AgentReply:
        trace_id = uuid.uuid4().hex
        tlog = log.bind(trace_id=trace_id, ticket_id=ticket.ticket_id)
        # LGPD: mascara dados pessoais antes de qualquer chamada ao LLM e de qualquer log
        ticket = ticket.model_copy(update={"message": redact(ticket.message)})

        order = await self.orders.get(ticket.order_id)
        facts: ExtractedFacts | None = None
        triage: TriageResult | None = None

        if order is None or order.customer_id != ticket.customer_id:
            decision = escalate("pedido_invalido")
        else:
            facts = await self._extract_facts(ticket, tlog)
            if facts is None:
                decision = escalate("extracao_falhou")
            else:
                triage = await self.triage.evaluate(ticket, order, facts)
                tlog.info("triage_result", score=triage.score, flags=triage.risk_flags,
                          reason=triage.reason_code)
                decision = decide(facts, order, triage, self.settings)

        message = await self._write_reply(facts, decision, tlog)
        await self.store.save(ticket, decision, trace_id)
        tlog.info("ticket_handled", action=decision.action, rules=decision.rule_trace)
        return AgentReply(
            ticket_id=ticket.ticket_id, message=message,
            decision=decision, facts=facts, triage=triage, trace_id=trace_id,
        )

    async def _extract_facts(self, ticket: Ticket, tlog: Any) -> ExtractedFacts | None:
        try:
            return await self._extract_facts_llm(ticket, tlog)
        except Exception as exc:  # LLM fora do ar ou resposta malformada -> escala
            tlog.warning("extract_failed", error=repr(exc))
            return None

    async def _extract_facts_llm(self, ticket: Ticket, tlog: Any) -> ExtractedFacts | None:
        tools = build_tools(self.orders, ticket)
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": EXTRACT_PROMPT},
            {"role": "user",
             "content": f"<mensagem_cliente>\n{ticket.message}\n</mensagem_cliente>"},
        ]

        # 1) rodadas de tool calling, com teto. Cada rodada é uma chamada inteira ao LLM,
        #    então encerramos assim que não há nada novo a consultar.
        all_tools = {s["function"]["name"] for s in tools.schemas}
        called: set[str] = set()
        for _ in range(self.settings.max_tool_rounds):
            msg = (await self.llm.chat(messages, tools=tools.schemas))["message"]
            calls = msg.get("tool_calls") or []
            new_calls = [c for c in calls if c["function"]["name"] not in called]
            if not new_calls:  # sem chamadas, ou só repetições do que já foi consultado
                if calls:
                    tlog.info("tool_loop_stopped", reason="repeticao")
                break
            messages.append(
                {"role": "assistant", "content": msg.get("content") or "",
                 "tool_calls": new_calls})
            for call in new_calls:
                fn = call["function"]
                result = await tools.call(fn["name"], fn.get("arguments") or {})
                called.add(fn["name"])
                tlog.info("tool_call", tool=fn["name"])
                messages.append({
                    "role": "tool",
                    "tool_name": fn["name"],
                    "content": json.dumps(result, ensure_ascii=False),
                })
            if called >= all_tools:  # já tem tudo que as ferramentas podem dar
                break

        # 2) saída estruturada, com uma tentativa de correção
        messages.append(
            {"role": "user", "content": "Responda apenas com o JSON dos fatos extraídos."})
        schema = ExtractedFacts.model_json_schema()
        for attempt in range(2):
            content = (await self.llm.chat(messages, response_schema=schema))["message"]["content"]
            try:
                facts = ExtractedFacts.model_validate_json(content)
                return self._sanitize(facts, await self.orders.get(ticket.order_id))
            except ValidationError as exc:
                tlog.warning("facts_invalid", attempt=attempt, errors=exc.error_count())
                messages += [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": f"JSON inválido: {exc.errors()[:3]}. Corrija."},
                ]
        return None

    @staticmethod
    def _sanitize(facts: ExtractedFacts, order: Order | None) -> ExtractedFacts:
        """Remove SKUs que o modelo inventou."""
        valid = {i.sku for i in order.items} if order else set()
        return facts.model_copy(
            update={"affected_items": [a for a in facts.affected_items if a.sku in valid]})

    async def _write_reply(
        self, facts: ExtractedFacts | None, decision: Decision, tlog: Any
    ) -> str:
        context = {
            "acao": decision.action.value,
            "valor": str(decision.amount),
            "destino_reembolso": decision.refund_to.value if decision.refund_to else None,
            "motivo": reason_text(decision.reason_code),
            "resumo_problema": facts.summary if facts else None,
        }
        messages = [
            {"role": "system", "content": REPLY_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        try:
            text = ((await self.llm.chat(messages))["message"]["content"] or "").strip()
        except Exception as exc:  # LLM fora do ar -> template
            tlog.warning("reply_llm_failed", error=repr(exc))
            return fallback_reply(decision)
        if reply_is_consistent(text, decision):
            return text
        tlog.warning("reply_inconsistent_fallback")
        return fallback_reply(decision)
