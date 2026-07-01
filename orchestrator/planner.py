"""
PLANLAYICI — kullanıcının isteğini adımlara böler, YÜRÜTÜCÜ'nün sonuçlarını
değerlendirir ve ya nihai cevabı verir ya da planı günceller.

Function-calling'i "yapılandırılmış çıktı" olarak kullanır: planlayıcı serbest
metin yerine bir ARAÇ çağırmaya zorlanır (propose_plan / finish / replan),
böylece cevabı her zaman geçerli, ayrıştırılabilir bir JSON'dur.
"""

from orchestrator.config import settings
from orchestrator.llm import forced_call, choice_call


PLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "propose_plan",
        "description": "Kullanıcının isteğini, bir yürütücünün gerçekleştirebileceği bağımsız adımlara böl.",
        "parameters": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "description": "Sırayla gerçekleştirilecek adımlar.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "goal": {"type": "string", "description": "Bu adımda tam olarak ne yapılmalı"},
                        },
                        "required": ["goal"],
                    },
                },
            },
            "required": ["steps"],
        },
    },
}

FINISH_TOOL = {
    "type": "function",
    "function": {
        "name": "finish",
        "description": "Toplanan bilgi kullanıcının isteğini yanıtlamaya yeterli; nihai cevabı ver.",
        "parameters": {
            "type": "object",
            "properties": {
                "answer": {"type": "string", "description": "Kaynaklarıyla birlikte tam, nihai cevap"},
            },
            "required": ["answer"],
        },
    },
}

REPLAN_TOOL = {
    "type": "function",
    "function": {
        "name": "replan",
        "description": "Toplanan bilgi yetersiz ya da bir adım başarısız oldu; eksik kalan yeni adımları öner.",
        "parameters": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"goal": {"type": "string"}},
                        "required": ["goal"],
                    },
                },
            },
            "required": ["steps"],
        },
    },
}


PLAN_SYSTEM = f"""Sen bir PLANLAYICISIN. Kullanıcının isteğini, bir YÜRÜTÜCÜ agent'ın
tek tek gerçekleştirebileceği net ve bağımsız ADIMLARA böl. Yürütücünün elinde
web_search, read_url ve calculator araçları var; onları SEN çağırmazsın, sadece
hangi hedeflerin (goal) peşinden gidileceğine karar verirsin.

Kurallar:
- Basit/tek parçalı sorular için TEK adım yeterlidir, gereksiz bölme.
- En fazla {settings.max_plan_steps} adım öner.
- Her adımın hedefi somut ve ölçülebilir olsun.

propose_plan aracını çağırarak cevap ver."""

REVIEW_SYSTEM = """Sen bir PLANLAYICISIN. Bir YÜRÜTÜCÜ'ye verdiğin adımların
sonuçlarını inceliyorsun. Kullanıcının orijinal isteğini TAM olarak
yanıtlayacak kadar bilgi toplandıysa 'finish' aracını çağırıp nihai cevabı
(varsa kaynaklarıyla) ver. Eksikse ya da bir adım başarısız olduysa 'replan'
aracını çağırıp SADECE eksik/yeni adımları listele (tamamlanmış adımları
tekrar etme).

Yeniden planlama hakkın sınırlı; hakkın azaldıkça elindeki bilgiyle 'finish'
demeyi tercih et."""


def make_plan(c, question: str) -> list[dict]:
    messages = [
        {"role": "system", "content": PLAN_SYSTEM},
        {"role": "user", "content": question},
    ]
    args = forced_call(c, messages, PLAN_TOOL)
    raw_steps = args.get("steps") or [{"goal": question}]
    return [
        {"id": i + 1, "goal": s.get("goal", question)}
        for i, s in enumerate(raw_steps[: settings.max_plan_steps])
    ]


def review(c, question: str, done_steps: list[dict], attempt: int) -> dict:
    summary = "\n".join(f"[Adım {s['id']}] {s['goal']}\nSonuç: {s['result']}" for s in done_steps)
    messages = [
        {
            "role": "system",
            "content": REVIEW_SYSTEM
            + f"\n\n(Bu senin {attempt}. değerlendirmen; en fazla {settings.max_replans} "
            "yeniden planlama hakkın var.)",
        },
        {"role": "user", "content": f"Orijinal istek: {question}\n\nTamamlanan adımlar:\n{summary}"},
    ]
    name, args = choice_call(c, messages, [FINISH_TOOL, REPLAN_TOOL])

    if name == "finish":
        return {"status": "done", "answer": args.get("answer", "")}

    raw_steps = args.get("steps") or []
    next_id = len(done_steps) + 1
    steps = [{"id": next_id + i, "goal": s.get("goal", "")} for i, s in enumerate(raw_steps)]
    return {"status": "replan", "steps": steps}
