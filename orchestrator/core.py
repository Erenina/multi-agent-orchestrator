"""
Multi-agent orkestrasyon döngüsü.

PLANLAYICI isteği adımlara böler → YÜRÜTÜCÜ her adımı sırayla gerçekleştirir
(kendi mini ReAct döngüsüyle) → PLANLAYICI sonuçları inceler: yeterliyse nihai
cevabı verir, değilse planı GÜNCELLER (replan). En fazla max_replans kez
yeniden planlanabilir.

Tek-agent ReAct'ten (bkz. research-agent projesi) farkı: "ne yapılacağına
karar verme" (planlama) ile "nasıl yapılacağı" (araç kullanımı) iki AYRI LLM
rolüne bölünmüş — biri stratejiyi yönetir, diğeri taktiği.
"""

from orchestrator.config import settings
from orchestrator.llm import client, LLMError
from orchestrator import planner, executor


class OrchestratorError(Exception):
    """Yapılandırma ya da LLM çağrısı hatası."""


def _fallback_answer(done_steps: list[dict]) -> str:
    return "\n\n".join(f"- {s['goal']}: {s['result']}" for s in done_steps)


def run(question: str, on_event=None) -> dict:
    """
    on_event(*ev) olayları:
      ("plan", steps)                   ilk plan yayınlandı
      ("step_start", id, goal)          bir adım başlıyor
      ("tool_call", id, name, args)     adım içinde bir araç çağrılıyor
      ("tool_result", id, name, result) aracın sonucu
      ("step_done", id, result)         adım tamamlandı
      ("replan", steps)                 plan güncellendi
      ("final", answer)                 nihai cevap

    Dönüş: {"answer": str, "steps": [olaylar]}
    """
    trace: list = []

    def emit(*ev):
        trace.append(ev)
        if on_event:
            on_event(*ev)

    try:
        c = client()
        steps_to_run = planner.make_plan(c, question)
        emit("plan", steps_to_run)

        done_steps: list = []
        replans = 0

        while True:
            for step in steps_to_run:
                step_id = step["id"]
                emit("step_start", step_id, step["goal"])

                def step_event(kind, *rest, _id=step_id):
                    emit(kind, _id, *rest)

                result = executor.run_step(c, step["goal"], context=done_steps, on_event=step_event)
                done_steps.append({**step, "result": result})
                emit("step_done", step_id, result)

            replans += 1
            verdict = planner.review(c, question, done_steps, attempt=replans)

            if verdict["status"] == "done":
                answer = verdict.get("answer") or _fallback_answer(done_steps)
                emit("final", answer)
                return {"answer": answer, "steps": trace}

            if replans >= settings.max_replans or not verdict.get("steps"):
                answer = _fallback_answer(done_steps)
                emit("final", answer)
                return {"answer": answer, "steps": trace}

            steps_to_run = verdict["steps"]
            emit("replan", steps_to_run)

    except LLMError as e:
        raise OrchestratorError(str(e)) from e
