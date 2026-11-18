"""
Herramienta aislada de inventario, calidad visual y deduplicacion (Actividad A).

Opera en modo estrictamente de solo lectura sobre la carpeta fuente de
evidencias (por defecto ``../../evidencias_vigia`` relativo al sandbox) y genera
manifiestos reproducibles en CSV y JSON con rutas POSIX relativas.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import cv2
import numpy as np

SOURCE_DOMAINS: Tuple[str, ...] = (
    "SCALE_MODEL_LAB",
    "SCREEN_RECAPTURE",
    "REAL_FULL_SCALE",
    "NEGATIVE_CONTROL",
    "UNKNOWN",
)

# Mapa explicito de procedencia auditada (VIGIA-ML-01). Ninguna fecha desconocida
# se asume como REAL_FULL_SCALE automaticamente.
DEFAULT_DATE_DOMAIN_PROVENANCE: Dict[str, str] = {
    "20261111": "SCREEN_RECAPTURE",
    "20261114": "SCALE_MODEL_LAB",
}

_FILENAME_TS_RE = re.compile(
    r"^(?P<ymd>\d{8})T(?P<hms>\d{6})_(?P<us>\d{6})Z_(?P<uid>[0-9a-fA-F]+)_(?P<kind>orig|annot)$"
)


@dataclass(frozen=True)
class ManifestRecord:
    """Registro canonico de una evidencia visual para el sandbox VIGIA-ML."""

    sample_id: str
    image_path: str
    sha256: str
    capture_timestamp_utc: Optional[str]
    camera_id: str
    width: int
    height: int
    source_domain: str
    session_id: str
    duplicate_group: str
    annotation_status: str
    ground_truth_status: str
    # Campos auxiliares de auditoria y curacion
    annot_path: Optional[str] = None
    annot_sha256: Optional[str] = None
    pair_complete: bool = False
    exact_duplicate_of: Optional[str] = None
    date_folder: str = "UNKNOWN"
    size_bytes: int = 0
    is_readable: bool = True
    sharpness_laplacian: float = 0.0
    luminance_mean_y: float = 0.0
    pct_dark: float = 0.0
    pct_glare: float = 0.0
    dhash_hex: str = ""
    consecutive_mad: Optional[float] = None


def compute_sha256(file_path: Path, chunk_size: int = 65536) -> str:
    """Calcula el hash SHA-256 hexadecimal de un archivo binario."""
    digest = hashlib.sha256()
    with file_path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def parse_capture_metadata(orig_path: Path, source_root: Path) -> Tuple[Optional[datetime], str, str]:
    """
    Extrae (timestamp_utc, camera_id, date_folder) desde ruta y nombre de archivo.
    Si el patron no coincide, retorna valores seguros sin asumir dominio real.
    """
    try:
        rel_parts = orig_path.relative_to(source_root).parts
    except ValueError:
        rel_parts = orig_path.parts

    date_folder = rel_parts[0] if len(rel_parts) >= 2 and rel_parts[0].isdigit() else "UNKNOWN"
    camera_id = rel_parts[-2] if len(rel_parts) >= 2 and rel_parts[-2] != date_folder else "UNKNOWN"

    match = _FILENAME_TS_RE.match(orig_path.stem)
    if match:
        dt_str = f"{match.group('ymd')}T{match.group('hms')}.{match.group('us')}+00:00"
        dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%S.%f%z").astimezone(timezone.utc)
        if date_folder == "UNKNOWN":
            date_folder = match.group("ymd")
        return dt, camera_id, date_folder
    return None, camera_id, date_folder


def compute_dhash(gray_img: np.ndarray, hash_size: int = 8) -> int:
    """Calcula un hash perceptual de diferencias (dHash 64-bit) resistente a ruido leve."""
    resized = cv2.resize(gray_img, (hash_size + 1, hash_size), interpolation=cv2.INTER_AREA)
    diff = resized[:, 1:] > resized[:, :-1]
    value = 0
    for bit in diff.flatten():
        value = (value << 1) | int(bool(bit))
    return value


def hamming_distance(hash_a: int, hash_b: int) -> int:
    """Distancia de Hamming entre dos hashes enteros."""
    return (hash_a ^ hash_b).bit_count()


def compute_visual_quality(bgr_img: np.ndarray) -> Dict[str, float]:
    """Calcula indicadores reproducibles de nitidez, luminancia y artefactos."""
    gray = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2GRAY)
    hsv = cv2.cvtColor(bgr_img, cv2.COLOR_BGR2HSV)
    sharpness = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    luminance = float(gray.mean())
    pct_dark = float((hsv[:, :, 2] < 45).mean())
    pct_glare = float(((hsv[:, :, 2] > 240) & (hsv[:, :, 1] < 40)).mean())
    return {
        "sharpness_laplacian": round(sharpness, 3),
        "luminance_mean_y": round(luminance, 3),
        "pct_dark": round(pct_dark, 4),
        "pct_glare": round(pct_glare, 4),
    }


def resolve_source_domain(
    date_folder: str,
    provenance_map: Optional[Mapping[str, str]] = None,
) -> str:
    """
    Asigna ``source_domain`` exclusivamente desde procedencia documentada.
    Nunca infiere ``REAL_FULL_SCALE`` a partir de nombres de archivo o YOLO.
    """
    mapping = provenance_map if provenance_map is not None else DEFAULT_DATE_DOMAIN_PROVENANCE
    candidate = mapping.get(date_folder, "UNKNOWN")
    return candidate if candidate in SOURCE_DOMAINS else "UNKNOWN"


def inspect_storage_budget(source_root: Path, sandbox_root: Path) -> Dict[str, object]:
    """Mide espacio libre en disco y huella por fecha antes de cualquier copia."""
    usage = shutil.disk_usage(sandbox_root)
    per_date: Dict[str, Dict[str, float | int]] = {}
    if source_root.exists():
        for entry in sorted(p for p in source_root.iterdir() if p.is_dir()):
            origs = list(entry.rglob("*_orig.jpg"))
            annots = list(entry.rglob("*_annot.jpg"))
            total_bytes = sum(f.stat().st_size for f in entry.rglob("*") if f.is_file())
            per_date[entry.name] = {
                "orig_count": len(origs),
                "annot_count": len(annots),
                "size_mb": round(total_bytes / (1024.0 * 1024.0), 3),
            }
    return {
        "free_disk_gb": round(usage.free / (1024.0 ** 3), 3),
        "source_exists": source_root.exists(),
        "total_source_mb": round(sum(float(v["size_mb"]) for v in per_date.values()), 3),
        "per_date": per_date,
    }


def build_inventory(
    source_root: Path,
    sandbox_root: Path,
    *,
    include_dates: Optional[Sequence[str]] = None,
    provenance_map: Optional[Mapping[str, str]] = None,
    session_gap_seconds: float = 60.0,
    consecutive_mad_threshold: float = 8.0,
    dhash_hamming_threshold: int = 6,
) -> List[ManifestRecord]:
    """
    Inventaria ``source_root`` en solo lectura, empareja ``_orig``/``_annot``,
    detecta duplicados exactos (SHA-256) y similares perceptuales, y agrupa
    por sesiones temporales por camara.
    """
    if not source_root.exists():
        raise FileNotFoundError(f"No existe la raiz de evidencias: {source_root}")

    date_filter = set(include_dates) if include_dates else None
    orig_paths = sorted(source_root.rglob("*_orig.jpg"))

    # Pre-extraccion ordenada por camara y tiempo para calcular sesiones y MAD
    raw_items = []
    for orig_p in orig_paths:
        dt, cam_id, date_folder = parse_capture_metadata(orig_p, source_root)
        if date_filter is not None and date_folder not in date_filter:
            continue
        annot_p = orig_p.with_name(orig_p.name.replace("_orig.jpg", "_annot.jpg"))
        has_annot = annot_p.is_file()
        sha_orig = compute_sha256(orig_p)
        sha_annot = compute_sha256(annot_p) if has_annot else None
        img = cv2.imread(str(orig_p))
        if img is None:
            raw_items.append(
                {
                    "orig_p": orig_p,
                    "annot_p": annot_p if has_annot else None,
                    "dt": dt,
                    "cam_id": cam_id,
                    "date_folder": date_folder,
                    "sha_orig": sha_orig,
                    "sha_annot": sha_annot,
                    "width": 0,
                    "height": 0,
                    "readable": False,
                    "quality": {
                        "sharpness_laplacian": 0.0,
                        "luminance_mean_y": 0.0,
                        "pct_dark": 0.0,
                        "pct_glare": 0.0,
                    },
                    "gray_thumb": None,
                    "dhash_int": 0,
                    "dhash_hex": "",
                }
            )
            continue

        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        dhash_int = compute_dhash(gray)
        gray_thumb = cv2.resize(gray, (160, 120), interpolation=cv2.INTER_AREA)
        raw_items.append(
            {
                "orig_p": orig_p,
                "annot_p": annot_p if has_annot else None,
                "dt": dt,
                "cam_id": cam_id,
                "date_folder": date_folder,
                "sha_orig": sha_orig,
                "sha_annot": sha_annot,
                "width": int(w),
                "height": int(h),
                "readable": True,
                "quality": compute_visual_quality(img),
                "gray_thumb": gray_thumb,
                "dhash_int": dhash_int,
                "dhash_hex": f"{dhash_int:016x}",
            }
        )

    raw_items.sort(
        key=lambda item: (
            item["date_folder"],
            item["cam_id"],
            item["dt"].isoformat() if item["dt"] else item["orig_p"].name,
        )
    )

    seen_sha: Dict[str, str] = {}
    session_counters: Dict[Tuple[str, str], int] = {}
    last_dt_by_cam: Dict[Tuple[str, str], Optional[datetime]] = {}
    last_thumb_by_cam: Dict[Tuple[str, str], Optional[np.ndarray]] = {}
    last_dhash_by_cam: Dict[Tuple[str, str], Optional[int]] = {}
    dup_counter_by_sess: Dict[str, int] = {}
    current_dup_group_by_cam: Dict[Tuple[str, str], str] = {}

    records: List[ManifestRecord] = []
    for item in raw_items:
        date_folder = str(item["date_folder"])
        cam_id = str(item["cam_id"])
        key = (date_folder, cam_id)
        dt: Optional[datetime] = item["dt"]

        # 1. Asignacion determinista de sesion temporal
        prev_dt = last_dt_by_cam.get(key)
        if key not in session_counters:
            session_counters[key] = 1
        elif dt is not None and prev_dt is not None:
            if (dt - prev_dt).total_seconds() > session_gap_seconds:
                session_counters[key] += 1
        last_dt_by_cam[key] = dt
        session_id = f"{date_folder}_{cam_id}_S{session_counters[key]:02d}"

        # 2. Deteccion de duplicados exactos y similares perceptuales dentro de sesion
        sample_id = f"{date_folder}_{cam_id}_{item['orig_p'].stem[:20]}_{item['sha_orig'][:8]}"
        exact_dup_of = seen_sha.get(item["sha_orig"])
        if exact_dup_of is None:
            seen_sha[item["sha_orig"]] = sample_id

        mad_val: Optional[float] = None
        is_near_dup = False
        prev_thumb = last_thumb_by_cam.get(key)
        prev_dhash = last_dhash_by_cam.get(key)
        if item["readable"] and prev_thumb is not None and item["gray_thumb"] is not None:
            mad_val = round(
                float(np.mean(np.abs(item["gray_thumb"].astype(np.float32) - prev_thumb.astype(np.float32)))),
                3,
            )
            h_dist = hamming_distance(item["dhash_int"], prev_dhash) if prev_dhash is not None else 999
            if mad_val < consecutive_mad_threshold or h_dist <= dhash_hamming_threshold:
                is_near_dup = True

        if exact_dup_of is not None:
            # Si es identico por SHA-256 reutilizamos clúster si es misma camara o creamos identificador estable
            dup_group = current_dup_group_by_cam.get(key, f"DUP_{item['sha_orig'][:10]}")
        elif is_near_dup and key in current_dup_group_by_cam:
            dup_group = current_dup_group_by_cam[key]
        else:
            dup_counter_by_sess[session_id] = dup_counter_by_sess.get(session_id, 0) + 1
            dup_group = f"{session_id}_C{dup_counter_by_sess[session_id]:03d}"
            current_dup_group_by_cam[key] = dup_group

        last_thumb_by_cam[key] = item["gray_thumb"]
        last_dhash_by_cam[key] = item["dhash_int"]

        try:
            rel_img = item["orig_p"].resolve().relative_to(sandbox_root.resolve()).as_posix()
        except ValueError:
            rel_img = Path(
                # Ruta relativa desde sandbox hacia evidencias_vigia (p. ej. ../../evidencias_vigia/...)
                *("..", "..", "evidencias_vigia", item["orig_p"].relative_to(source_root).as_posix())
            ).as_posix()

        rel_annot: Optional[str] = None
        if item["annot_p"] is not None:
            try:
                rel_annot = item["annot_p"].resolve().relative_to(sandbox_root.resolve()).as_posix()
            except ValueError:
                rel_annot = Path(
                    *("..", "..", "evidencias_vigia", item["annot_p"].relative_to(source_root).as_posix())
                ).as_posix()

        records.append(
            ManifestRecord(
                sample_id=sample_id,
                image_path=rel_img,
                sha256=item["sha_orig"],
                capture_timestamp_utc=dt.isoformat().replace("+00:00", "Z") if dt else None,
                camera_id=cam_id,
                width=item["width"],
                height=item["height"],
                source_domain=resolve_source_domain(date_folder, provenance_map),
                session_id=session_id,
                duplicate_group=dup_group,
                annotation_status="UNANNOTATED",
                ground_truth_status="NONE",
                annot_path=rel_annot,
                annot_sha256=item["sha_annot"],
                pair_complete=bool(item["annot_p"] is not None),
                exact_duplicate_of=exact_dup_of,
                date_folder=date_folder,
                size_bytes=int(item["orig_p"].stat().st_size),
                is_readable=bool(item["readable"]),
                sharpness_laplacian=float(item["quality"]["sharpness_laplacian"]),
                luminance_mean_y=float(item["quality"]["luminance_mean_y"]),
                pct_dark=float(item["quality"]["pct_dark"]),
                pct_glare=float(item["quality"]["pct_glare"]),
                dhash_hex=item["dhash_hex"],
                consecutive_mad=mad_val,
            )
        )

    return records


def save_manifest(records: Iterable[ManifestRecord], out_json: Path, out_csv: Path) -> None:
    """Guarda el manifiesto en JSON y CSV con orden determinista."""
    rows = [asdict(r) for r in records]
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_csv.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "schema_version": "1.0.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_samples": len(rows),
        "records": rows,
    }
    out_json.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    fieldnames = list(ManifestRecord.__dataclass_fields__.keys())
    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    sandbox_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Inventario reproducible de evidencias VIGIA-ML.")
    parser.add_argument(
        "--source",
        type=Path,
        default=sandbox_root.parent.parent / "evidencias_vigia",
        help="Ruta a la carpeta fuente de evidencias (solo lectura).",
    )
    parser.add_argument(
        "--dates",
        nargs="*",
        default=None,
        help="Subconjunto opcional de fechas (ej. 20261111 20261114).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=sandbox_root / "data" / "processed",
        help="Carpeta destino para manifest_v1.json y manifest_v1.csv.",
    )
    args = parser.parse_args()

    storage = inspect_storage_budget(args.source, sandbox_root)
    records = build_inventory(args.source, sandbox_root, include_dates=args.dates)
    out_json = args.out_dir / "manifest_v1.json"
    out_csv = args.out_dir / "manifest_v1.csv"
    save_manifest(records, out_json, out_csv)

    unique_clusters = len({r.duplicate_group for r in records})
    unique_sessions = len({r.session_id for r in records})
    print(
        json.dumps(
            {
                "free_disk_gb": storage["free_disk_gb"],
                "total_source_mb": storage["total_source_mb"],
                "manifest_records": len(records),
                "unique_sessions": unique_sessions,
                "unique_duplicate_groups": unique_clusters,
                "out_json": str(out_json.relative_to(sandbox_root).as_posix()),
                "out_csv": str(out_csv.relative_to(sandbox_root).as_posix()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
