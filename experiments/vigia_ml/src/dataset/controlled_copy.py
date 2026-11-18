"""
Copia controlada e inmutable desde evidencias historicas hacia ``data/raw/``.

Reglas de seguridad:
1. Jamas modifica, renombra o elimina archivos en ``evidencias_vigia``.
2. Verifica espacio libre disponible antes de copiar.
3. Evita copiar todas las evidencias indiscriminadamente; soporta filtrado por fecha
   y deduplicacion (1 muestra representativa por clúster de duplicados).
4. Valida integridad bit a bit mediante SHA-256 despues de cada copia.
"""

from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from src.dataset.inventory import (
    ManifestRecord,
    build_inventory,
    compute_sha256,
    inspect_storage_budget,
    save_manifest,
)


def select_records_for_copy(
    records: Sequence[ManifestRecord],
    *,
    include_dates: Optional[Sequence[str]] = None,
    deduplicate_per_cluster: bool = True,
) -> List[ManifestRecord]:
    """Selecciona un subconjunto curado sin duplicados exactos ni rafagas redundantes."""
    date_set = set(include_dates) if include_dates else None
    seen_clusters = set()
    selected: List[ManifestRecord] = []

    for rec in records:
        if not rec.is_readable:
            continue
        if date_set is not None and rec.date_folder not in date_set:
            continue
        if rec.exact_duplicate_of is not None:
            continue
        if deduplicate_per_cluster:
            if rec.duplicate_group in seen_clusters:
                continue
            seen_clusters.add(rec.duplicate_group)
        selected.append(rec)

    return selected


def execute_controlled_copy(
    source_root: Path,
    sandbox_root: Path,
    *,
    include_dates: Sequence[str] = ("20261111", "20261114"),
    deduplicate_per_cluster: bool = True,
    copy_annotated: bool = True,
    min_free_gb: float = 2.0,
) -> Dict[str, object]:
    """
    Copia de forma reproducible las muestras seleccionadas hacia ``data/raw/``,
    verifica SHA-256 de origen vs copia y genera ``data/raw/copy_receipt.json``
    junto con el manifiesto actualizado del sandbox.
    """
    budget = inspect_storage_budget(source_root, sandbox_root)
    if float(budget["free_disk_gb"]) < min_free_gb:
        raise RuntimeError(
            f"Espacio insuficiente ({budget['free_disk_gb']} GB < {min_free_gb} GB)."
        )

    all_records = build_inventory(source_root, sandbox_root, include_dates=include_dates)
    selected = select_records_for_copy(
        all_records,
        include_dates=include_dates,
        deduplicate_per_cluster=deduplicate_per_cluster,
    )

    raw_dir = sandbox_root / "data" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    copied_records: List[ManifestRecord] = []
    copied_files = 0
    copied_bytes = 0
    verified_hashes = 0

    for rec in selected:
        src_orig = (sandbox_root / rec.image_path).resolve()
        rel_sub = Path(rec.date_folder) / rec.camera_id / src_orig.name
        dst_orig = raw_dir / rel_sub
        dst_orig.parent.mkdir(parents=True, exist_ok=True)

        if not dst_orig.exists():
            shutil.copy2(src_orig, dst_orig)
            copied_files += 1
            copied_bytes += dst_orig.stat().st_size

        dst_sha = compute_sha256(dst_orig)
        if dst_sha != rec.sha256:
            raise IOError(
                f"Fallo de integridad SHA-256 al copiar {src_orig.name}: "
                f"esperado={rec.sha256}, obtenido={dst_sha}"
            )
        verified_hashes += 1

        copied_annot_rel: Optional[str] = None
        if copy_annotated and rec.annot_path:
            src_annot = (sandbox_root / rec.annot_path).resolve()
            if src_annot.is_file():
                dst_annot = raw_dir / rec.date_folder / rec.camera_id / src_annot.name
                if not dst_annot.exists():
                    shutil.copy2(src_annot, dst_annot)
                    copied_files += 1
                    copied_bytes += dst_annot.stat().st_size
                dst_annot_sha = compute_sha256(dst_annot)
                if rec.annot_sha256 and dst_annot_sha != rec.annot_sha256:
                    raise IOError(
                        f"Fallo de integridad SHA-256 en anotada {src_annot.name}."
                    )
                copied_annot_rel = dst_annot.relative_to(sandbox_root).as_posix()

        copied_dict = asdict(rec)
        copied_dict["image_path"] = dst_orig.relative_to(sandbox_root).as_posix()
        copied_dict["annot_path"] = copied_annot_rel
        copied_records.append(ManifestRecord(**copied_dict))

    receipt = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "include_dates": list(include_dates),
        "deduplicate_per_cluster": deduplicate_per_cluster,
        "copy_annotated": copy_annotated,
        "free_disk_gb_before": budget["free_disk_gb"],
        "total_scanned_in_dates": len(all_records),
        "selected_pairs": len(copied_records),
        "new_files_written": copied_files,
        "new_bytes_written": copied_bytes,
        "sha256_verified_orig": verified_hashes,
        "source_untouched": True,
    }
    receipt_path = raw_dir / "copy_receipt.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, ensure_ascii=False), encoding="utf-8")

    # Manifiesto de trabajo apuntando a las copias locales en data/raw/
    save_manifest(
        copied_records,
        sandbox_root / "data" / "processed" / "sandbox_raw_manifest_v1.json",
        sandbox_root / "data" / "processed" / "sandbox_raw_manifest_v1.csv",
    )
    return receipt


def main() -> None:
    sandbox_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Copia controlada SHA-256 hacia data/raw/.")
    parser.add_argument(
        "--source",
        type=Path,
        default=sandbox_root.parent.parent / "evidencias_vigia",
    )
    parser.add_argument(
        "--dates",
        nargs="+",
        default=["20261111", "20261114"],
    )
    parser.add_argument(
        "--no-dedup",
        action="store_true",
        help="Copiar todos los pares sin filtrar por clúster de duplicados.",
    )
    args = parser.parse_args()

    receipt = execute_controlled_copy(
        args.source,
        sandbox_root,
        include_dates=tuple(args.dates),
        deduplicate_per_cluster=not args.no_dedup,
    )
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
