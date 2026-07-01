"""
Groq istemcisi ve tekrar deneme (retry) mantığı.

Hem PLANLAYICI hem YÜRÜTÜCÜ aynı istemciyi ve aynı retry mekanizmasını
kullanır. research-agent projesinde öğrenilen ders: Llama'nın function-calling'i
bazen bozuk/eksik argümanlı bir çağrı üretir (Groq bunu 'tool_use_failed' ile
reddeder). Üretim rastgele olduğundan, sıcaklığı artırarak tekrar denemek
genelde geçerli bir çıktı üretir.

Planlayıcı, serbest metin yerine bir ARAÇ çağırmaya zorlanarak (tool_choice)
"yapılandırılmış çıktı" üretir — böylece planı ayrıştırmak için kırılgan bir
JSON-metin ayrıştırıcısına gerek kalmaz.
"""

import json

import groq as groq_sdk
from groq import Groq

from orchestrator.config import settings


class LLMError(Exception):
    """Groq API çağrısı, tüm tekrar denemelere rağmen başarısız oldu."""


def client() -> Groq:
    if not settings.groq_api_key:
        raise LLMError(
            "GROQ_API_KEY tanımlı değil. https://console.groq.com'dan ücretsiz "
            "key al ve .env'e ekle."
        )
    return Groq(api_key=settings.groq_api_key)


def chat(c: Groq, messages, *, tools=None, tool_choice=None, temperature=0.2, attempts=4):
    """Sohbet tamamlama çağrısı; geçici hatalarda sıcaklığı artırıp tekrar dener."""
    kwargs = {"model": settings.model, "messages": messages, "temperature": temperature}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = tool_choice or "auto"

    last_error = None
    for i in range(attempts):
        try:
            return c.chat.completions.create(**kwargs)
        except groq_sdk.APIError as e:
            last_error = e
            retryable = "tool_use_failed" in str(e) or "did not match schema" in str(e)
            if retryable and i < attempts - 1:
                kwargs["temperature"] = min(0.8, kwargs["temperature"] + 0.2)
                continue
            raise LLMError(f"LLM çağrısı başarısız: {e}") from e
    raise LLMError(f"LLM çağrısı başarısız: {last_error}")


def forced_call(c: Groq, messages, tool_schema: dict, **kw) -> dict:
    """Modeli TEK bir belirli aracı çağırmaya zorla, argümanlarını dict olarak döndür."""
    name = tool_schema["function"]["name"]
    response = chat(
        c, messages,
        tools=[tool_schema],
        tool_choice={"type": "function", "function": {"name": name}},
        **kw,
    )
    msg = response.choices[0].message
    if not msg.tool_calls:
        raise LLMError(f"Model '{name}' aracını çağırmadı.")
    try:
        return json.loads(msg.tool_calls[0].function.arguments or "{}")
    except json.JSONDecodeError as e:
        raise LLMError(f"'{name}' argümanları çözümlenemedi: {e}") from e


def choice_call(c: Groq, messages, tools: list, **kw) -> tuple[str, dict]:
    """Modeli, verilen araçlardan BİRİNİ seçip çağırmaya zorla (tool_choice=required)."""
    response = chat(c, messages, tools=tools, tool_choice="required", **kw)
    msg = response.choices[0].message
    if not msg.tool_calls:
        raise LLMError("Model hiçbir aracı çağırmadı.")
    tc = msg.tool_calls[0]
    try:
        args = json.loads(tc.function.arguments or "{}")
    except json.JSONDecodeError as e:
        raise LLMError(f"Argümanlar çözümlenemedi: {e}") from e
    return tc.function.name, args
