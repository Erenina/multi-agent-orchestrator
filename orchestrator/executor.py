"""
YÜRÜTÜCÜ — planlayıcının verdiği TEK bir adımı gerçekleştirir.

Kendi küçük ReAct döngüsüne sahiptir: gerekirse araç çağırır, sonucu görür,
tekrar dener; max_tool_calls_per_step sınırına ulaşınca elindeki bilgiyle bir
özet ister. (research-agent'taki tek-agent ReAct döngüsünün, "tek bir alt
görevle sınırlı" hali.)
"""

import json

from orchestrator.config import settings
from orchestrator.llm import chat
from orchestrator.tools import TOOL_FUNCS, TOOL_SCHEMAS


EXECUTOR_SYSTEM = """Sen bir YÜRÜTÜCÜsün. Sana verilen TEK bir alt görevi
tamamla. Gerekirse web_search, read_url veya calculator araçlarını kullan.
Bir aracı çağırırken GEREKLİ TÜM parametreleri doldur; asla boş argümanla
araç çağırma. Yeterli bilgiyi topladığında bu adımın sonucunu KISA ve net
özetle (varsa kaynak URL'lerini dahil et). Sadece bu adıma odaklan, başka
adımlara girme."""


def _assistant_msg(msg) -> dict:
    return {
        "role": "assistant",
        "content": msg.content or "",
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ],
    }


def run_step(c, goal: str, context: list[dict] | None = None, on_event=None) -> str:
    """
    Tek bir adımı gerçekleştir, sonucun metin özetini döndür.

    context: önceki adımların {"goal", "result"} listesi. Adımlar planlayıcı
    tarafından ayrı hedefler olarak tanımlansa da ("sonucu 15 ile topla" gibi)
    birbirine referans verebilir; bu yüzden yürütücüye önceki sonuçları da
    veriyoruz — aksi halde her adım izole çalışır ve önceki adımın çıktısını
    "göremez".
    """
    user_content = goal
    if context:
        prior = "\n".join(f"- {s['goal']}: {s['result']}" for s in context)
        user_content = f"Önceki adımların sonuçları:\n{prior}\n\nŞimdi bu adımı gerçekleştir: {goal}"

    messages = [
        {"role": "system", "content": EXECUTOR_SYSTEM},
        {"role": "user", "content": user_content},
    ]

    for _ in range(settings.max_tool_calls_per_step):
        response = chat(c, messages, tools=TOOL_SCHEMAS, tool_choice="auto")
        msg = response.choices[0].message

        if not msg.tool_calls:
            return msg.content or ""

        messages.append(_assistant_msg(msg))
        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            if on_event:
                on_event("tool_call", name, args)

            func = TOOL_FUNCS.get(name)
            result = func(**args) if func else f"Bilinmeyen araç: {name}"
            if on_event:
                on_event("tool_result", name, result)

            messages.append({"role": "tool", "tool_call_id": tc.id, "content": str(result)})

    messages.append({
        "role": "user",
        "content": "Adım limitine ulaştın. Elindeki bilgiyle bu adımın en iyi özetini ver.",
    })
    response = chat(c, messages)
    return response.choices[0].message.content or "Sonuç üretilemedi."
