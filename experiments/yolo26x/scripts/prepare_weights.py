"""
Descarga y verificacion controlada de pesos experimentales en ``experiments/yolo26x/weights/``.

- Copia ``../../yolo11n.pt`` verificando SHA-256 sin tocar el archivo de produccion.
- Descarga ``yolo11x.pt`` y ``yolo26x.pt`` dentro de ``weights/``.
- Inspecciona metadatos internos (capas, parametros, end2end, reg_max, stride, names)
  y escribe ``results/weights_manifest.json``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from ultralytics import YOLO
from ultralytics.utils.downloads import attempt_download_asset


def compute_sha256(path: Path, chunk_size: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            b = fh.read(chunk_size)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def inspect_model_metadata(weights_path: Path) -> Dict[str, Any]:
    model = YOLO(str(weights_path))
    inner = model.model
    head = inner.model[-1] if hasattr(inner, "model") and len(inner.model) > 0 else None
    n_params = sum(p.numel() for p in inner.parameters())
    n_layers = len(list(inner.modules()))
    end2end_flag = bool(getattr(head, "end2end", False)) if head is not None else False
    has_one2one = getattr(head, "one2one_cv2", None) is not None if head is not None else False
    reg_max = getattr(head, "reg_max", None) if head is not None else None
    stride = [float(s) for s in getattr(head, "stride", []).tolist()] if head is not None and hasattr(head, "stride") else []
    names = {int(k): str(v) for k, v in model.names.items()}
    coco_vehicle_map = {k: names.get(k) for k in (2, 3, 5, 7)}
    return {
        "weights_relpath": weights_path.name,
        "size_bytes": weights_path.stat().st_size,
        "size_mb": round(weights_path.stat().st_size / (1024.0 * 1024.0), 3),
        "sha256": compute_sha256(weights_path),
        "num_parameters": int(n_params),
        "num_torch_modules": int(n_layers),
        "end2end": end2end_flag,
        "has_one2one_head": bool(has_one2one),
        "reg_max": int(reg_max) if reg_max is not None else None,
        "stride": stride,
        "nc": len(names),
        "coco_vehicle_classes": coco_vehicle_map,
    }


def main() -> None:
    exp_root = Path(__file__).resolve().parents[1]
    repo_root = exp_root.parents[1]
    weights_dir = exp_root / "weights"
    results_dir = exp_root / "results"
    weights_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    # 1. Copiar yolo11n.pt desde la raiz sin alterar el original
    prod_11n = repo_root / "yolo11n.pt"
    if not prod_11n.is_file():
        raise FileNotFoundError(f"No se encontro el baseline de produccion en {prod_11n}")
    exp_11n = weights_dir / "yolo11n.pt"
    prod_sha = compute_sha256(prod_11n)
    if not exp_11n.is_file() or compute_sha256(exp_11n) != prod_sha:
        shutil.copy2(prod_11n, exp_11n)

    # 2. Descargar yolo11x.pt y yolo26x.pt exclusivamente dentro de weights/
    prev_cwd = Path.cwd()
    try:
        os.chdir(weights_dir)
        for asset_name in ("yolo11x.pt", "yolo26x.pt"):
            dst = weights_dir / asset_name
            if not dst.is_file():
                t0 = time.perf_counter()
                downloaded = attempt_download_asset(str(dst), release="v8.4.0")
                elapsed = time.perf_counter() - t0
                print(f"Downloaded {asset_name} -> {downloaded} in {elapsed:.2f}s")
    finally:
        os.chdir(prev_cwd)

    manifest: Dict[str, Any] = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "production_yolo11n_sha256": prod_sha,
        "models": {},
    }
    for name in ("yolo11n.pt", "yolo11x.pt", "yolo26x.pt"):
        wp = weights_dir / name
        if not wp.is_file():
            raise FileNotFoundError(f"Peso esperado faltante: {wp}")
        manifest["models"][name] = inspect_model_metadata(wp)

    out_path = results_dir / "weights_manifest.json"
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(manifest, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
