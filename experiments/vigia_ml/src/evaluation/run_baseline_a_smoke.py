"""
Ejecucion de prueba exploratoria (smoke test) de Baseline A sobre ``data/raw/``.

IMPORTANTE:
- No usa predicciones como Ground Truth ni calcula accuracy sobre datos sin etiquetar.
- Registra distribucion de salidas, tasa de ``INDETERMINATE`` e indicadores de
  calidad visual para validar funcionamiento tecnico reproducible del extractor.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import cv2

from src.color_analysis.baseline_classic import predict_color_classic


def run_smoke_on_sandbox(sandbox_root: Path) -> dict:
    manifest_path = sandbox_root / "data" / "processed" / "sandbox_raw_manifest_v1.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"No existe {manifest_path}. Ejecute primero src.dataset.controlled_copy."
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = manifest.get("records", [])

    color_counts = Counter()
    domain_counts = Counter()
    quality_flags = Counter()
    samples_detail = []

    for rec in records:
        img_path = sandbox_root / rec["image_path"]
        img = cv2.imread(str(img_path))
        if img is None:
            continue
        h, w = img.shape[:2]
        # ROI por defecto equivalente a la zona central usada en VIGIA [0.10..0.90, 0.15..0.95]
        roi = (int(0.10 * w), int(0.15 * h), int(0.90 * w), int(0.95 * h))
        pred = predict_color_classic(img, roi)

        color_counts[pred.predicted_color] += 1
        domain_counts[rec["source_domain"]] += 1
        quality_flags[str(pred.quality_indicator.get("quality_flag", "UNKNOWN"))] += 1
        samples_detail.append(
            {
                "sample_id": rec["sample_id"],
                "source_domain": rec["source_domain"],
                "camera_id": rec["camera_id"],
                "predicted_color": pred.predicted_color,
                "confidence": pred.confidence,
                "is_indeterminate": pred.is_indeterminate,
                "quality_flag": pred.quality_indicator.get("quality_flag"),
                "usable_pixel_ratio": pred.quality_indicator.get("usable_pixel_ratio"),
            }
        )

    total = len(samples_detail)
    indet = color_counts.get("INDETERMINATE", 0)
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "evaluated_samples": total,
        "has_human_ground_truth": False,
        "real_world_representative": False,
        "note": (
            "Smoke test diagnostico sobre fotogramas sin GT de caja ni etiqueta humana; "
            "no reportar como accuracy de produccion."
        ),
        "predicted_color_distribution": dict(color_counts),
        "indeterminate_rate": round(indet / total, 4) if total else 0.0,
        "source_domains": dict(domain_counts),
        "quality_flags": dict(quality_flags),
        "sample_outputs_preview": samples_detail[:12],
    }

    out_path = sandbox_root / "reports" / "baseline_a_smoke_report.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def main() -> None:
    sandbox_root = Path(__file__).resolve().parents[2]
    report = run_smoke_on_sandbox(sandbox_root)
    print(
        json.dumps(
            {
                "evaluated_samples": report["evaluated_samples"],
                "predicted_color_distribution": report["predicted_color_distribution"],
                "indeterminate_rate": report["indeterminate_rate"],
                "quality_flags": report["quality_flags"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
