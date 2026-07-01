"""
Komut satırı arayüzü — orkestratörü çalıştır ve planı/yürütmeyi canlı göster.

Kullanım:
    python cli.py "Sorunuz burada"
    python cli.py                 # etkileşimli mod
"""

import sys

from orchestrator.core import run, OrchestratorError


def _print_event(*ev):
    kind = ev[0]
    if kind == "plan":
        print("\n📋 PLAN:")
        for s in ev[1]:
            print(f"   {s['id']}. {s['goal']}")
    elif kind == "step_start":
        _, sid, goal = ev
        print(f"\n▶️  Adım {sid}: {goal}")
    elif kind == "tool_call":
        _, sid, name, args = ev
        arg_str = ", ".join(f"{k}={v!r}" for k, v in args.items())
        print(f"   🔧 {name}({arg_str})")
    elif kind == "tool_result":
        _, sid, name, result = ev
        preview = str(result).strip().replace("\n", " ")
        print(f"      ↳ {preview if len(preview) <= 300 else preview[:300] + '…'}")
    elif kind == "step_done":
        _, sid, result = ev
        preview = str(result).strip().replace("\n", " ")
        print(f"   ✅ Adım {sid} tamamlandı: {preview if len(preview) <= 200 else preview[:200] + '…'}")
    elif kind == "replan":
        print("\n🔁 PLAN GÜNCELLENDİ:")
        for s in ev[1]:
            print(f"   {s['id']}. {s['goal']}")
    elif kind == "final":
        print("\n" + "=" * 72)
        print("🏁 NİHAİ CEVAP\n")
        print(ev[1])
        print("=" * 72)


def ask(question: str) -> None:
    print(f"\n❓ {question}")
    try:
        run(question, on_event=_print_event)
    except OrchestratorError as e:
        print(f"\n❌ {e}")
        sys.exit(1)


def main() -> None:
    if len(sys.argv) > 1:
        ask(" ".join(sys.argv[1:]))
        return
    print("🧭 Multi-agent orkestratör hazır — çıkmak için Ctrl+C")
    try:
        while True:
            q = input("\n> ").strip()
            if q:
                ask(q)
    except (KeyboardInterrupt, EOFError):
        print("\ngörüşürüz 👋")


if __name__ == "__main__":
    main()
