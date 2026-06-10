"""Demo: run the EKT agent on the real L101 position 01.03.0004 (FSS,
Verbreiterungsstreifen) and resume through the HITL review interrupt.

Run offline:  EKT_MOCK=1 python main.py   (default)
Run live LLM: EKT_MOCK=0 ANTHROPIC_API_KEY=... python main.py
"""
import os
os.environ.setdefault("EKT_MOCK", "1")

from langgraph.types import Command

from graph import build_graph

POSITION = {
    "oz": "01.03.0004",
    "kurztext": "Frostschutzschicht herstellen",
    "langtext": (
        "Frostschutzschicht herstellen. In Verkehrsflaechen der Belastungsklasse "
        "Bk1,8 im Bereich des Verbreiterungsstreifen in nichttragfaehigen "
        "Teilflaechen. Baustoffgemisch 0/32. Feinanteil Kategorie UF3, im "
        "eingebauten Zustand hoechstens 5 Masse v.H. Feinanteile. "
        "Verdichtungsgrad/Verformungsmodul Ev2 = 45 MPa. Einbaudicke = 20 cm. "
        "Baustoffgemisch = B2-Material, gebr. Naturgestein nach ZTV-StB LSBB St 21. "
        "Abgerechnet wird nach Auftragsprofilen."),
    "boq_menge": 100.0,
    "boq_einheit": "m3",
    "abb_excerpts": [
        "Hinweis zur OZ 01.03.0005: Einbau Asphalttragschicht im Bereich des "
        "Verbreiterungsstreifens, Handeinbau. Streifenbreite >/= 50,0 cm.",
        "Vollsperrung; Bauzeit 31.08.2026 - 16.10.2026.",
    ],
}


def show(state):
    print(f"\nClassification: {state['work_type']} "
          f"@ {state['classification_confidence']:.2f}")
    print(f"  {state['classification_notes']}")
    print("\nDrivers:")
    for k, v in state["drivers"].items():
        p = state["driver_provenance"].get(k, {})
        print(f"  {k:18} = {v}   ({p.get('confidence', 1.0):.2f})")
    print("\nOperations:")
    for r in state["operation_results"]:
        m = f" / {r['method']} @ {r['method_confidence']:.2f}" if r["method"] else ""
        print(f"  {r['operation']}{m}  ->  {r['eur_total']:>9.2f} EUR")
        for l in r["lines"]:
            val = (f"{l['out_value']} {l['out_einheit']}" if l["out_id"]
                   else f"{l['eur']:.2f} EUR")
            note = f"   [{l['note']}]" if l.get("note") else ""
            print(f"      - {l['goal'][:58]:58} {val}{note}")
    e = state["ekt"]
    print(f"\nEKT: {e['total_eur']} EUR total -> {e['per_unit_eur']} EUR/"
          f"{e['einheit']}  (registry v{e['registry_version']})")
    print("\nReview flags (batched for the Kalkulator):")
    for f in state["review_flags"]:
        print(f"  [{f['kind']:14}] {f['where']:22} {f['detail'][:90]}")


if __name__ == "__main__":
    app = build_graph()
    cfg = {"configurable": {"thread_id": "demo-01.03.0004"}}

    result = app.invoke({"position": POSITION}, cfg)

    if "__interrupt__" in result:                 # paused at hitl_review
        print("=" * 78)
        print("GRAPH PAUSED: hitl_review interrupt (Kalkulator's batched review)")
        print("=" * 78)
        show(app.get_state(cfg).values)
        print("\n>>> resuming with: approve")
        result = app.invoke(Command(resume={"action": "approve"}), cfg)

    print("\nDone. Final status: assessment approved and persisted (stub).")
