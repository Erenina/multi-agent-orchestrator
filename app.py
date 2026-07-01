"""
FastAPI web arayüzü — orkestratörü tarayıcıdan çalıştır, PLANLAYICI/YÜRÜTÜCÜ
akışını CANLI göster (Server-Sent Events).

orchestrator.core.run'un on_event callback'i, olayları bir kuyruğa (queue)
yazar; SSE üreteci kuyruktan okuyup tarayıcıya akıtır — agent birkaç adım
sürdüğü için kullanıcı planı ve her adımın yürütülüşünü anlık izler.

Uç noktalar:
  GET /            -> tek sayfa arayüz
  GET /health      -> sağlık kontrolü
  GET /ask?q=...   -> SSE akışı (plan + adım adım yürütme olayları)
"""

import json
import queue
import threading
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from orchestrator.core import run, OrchestratorError

app = FastAPI(title="Multi-Agent Orchestrator")

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


def _event_payload(ev: tuple) -> dict:
    """core.py'nin (tuple) olayını, arayüzün anlayacağı JSON'a çevir."""
    kind = ev[0]
    if kind == "plan":
        return {"type": "plan", "steps": ev[1]}
    if kind == "step_start":
        return {"type": "step_start", "id": ev[1], "goal": ev[2]}
    if kind == "tool_call":
        return {"type": "tool_call", "id": ev[1], "name": ev[2], "args": ev[3]}
    if kind == "tool_result":
        return {"type": "tool_result", "id": ev[1], "name": ev[2], "result": str(ev[3])}
    if kind == "step_done":
        return {"type": "step_done", "id": ev[1], "result": str(ev[2])}
    if kind == "replan":
        return {"type": "replan", "steps": ev[1]}
    if kind == "final":
        return {"type": "final", "answer": ev[1]}
    if kind == "error":
        return {"type": "error", "message": ev[1]}
    return {"type": "unknown"}


@app.get("/ask")
def ask(q: str):
    """Soruyu çalıştır; her olayı oluştukça SSE ile gönder."""

    def stream():
        events: queue.Queue = queue.Queue()

        def on_event(*ev):
            events.put(ev)

        def worker():
            try:
                run(q, on_event=on_event)
            except OrchestratorError as e:
                events.put(("error", str(e)))
            except Exception as e:  # beklenmedik hata arayüzü çökertmesin
                events.put(("error", f"Beklenmedik hata: {e}"))
            finally:
                events.put(None)  # bitiş işareti

        threading.Thread(target=worker, daemon=True).start()

        while True:
            ev = events.get()
            if ev is None:
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                break
            yield f"data: {json.dumps(_event_payload(ev), ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
