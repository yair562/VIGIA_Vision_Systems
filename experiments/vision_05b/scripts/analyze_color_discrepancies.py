"""
experiments/vision_05b/scripts/analyze_color_discrepancies.py
Analiza detalladamente las 23 discrepancias y las 20 abstenciones UNKNOWN
del benchmark operativo en ROI (benchmark_color_results.json).
"""
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS_JSON = REPO_ROOT / "experiments" / "vision_05b" / "results" / "benchmark_color_results.json"

with open(RESULTS_JSON, "r", encoding="utf-8") as f:
    data = json.load(f)

roi_records = data.get("sample_roi_records", [])

discrepancies = []
abstentions = []
matches = []

for rec in roi_records:
    gt = rec.get("ground_truth_color")
    pred = rec.get("predicted_color")
    if not gt:
        continue
    if pred == gt:
        matches.append(rec)
    elif pred == "UNKNOWN":
        abstentions.append(rec)
    else:
        discrepancies.append(rec)

print(f"Total evaluables: {len(roi_records)}")
print(f"Matches (Aciertos): {len(matches)}")
print(f"Abstenciones UNKNOWN: {len(abstentions)}")
print(f"Discrepancias (Errores de clasificación): {len(discrepancies)}")
print("\n" + "="*80)
print(f"LISTADO DETALLADO DE LAS {len(discrepancies)} DISCREPANCIAS:")
print("="*80)

for i, d in enumerate(discrepancies, 1):
    print(f"[{i:02d}] Archivo: {d.get('file_name')}")
    print(f"     Clase: {d.get('cand_label')} | Conf Det: {d.get('cand_confidence')}")
    print(f"     GT (Campo): {d.get('ground_truth_color')} | Pred: {d.get('predicted_color')} (Conf: {d.get('confidence')})")
    print(f"     Status: {d.get('status')} | Iluminación: {d.get('lighting_condition')}")
    print(f"     Razón: {d.get('reason')}")
    print("-" * 80)

print("\n" + "="*80)
print(f"RESUMEN DE LAS {len(abstentions)} ABSTENCIONES UNKNOWN:")
print("="*80)
for i, a in enumerate(abstentions, 1):
    print(f"[{i:02d}] {a.get('file_name')} | GT: {a.get('ground_truth_color')} | Luz: {a.get('lighting_condition')} | Razón: {a.get('reason')}")
