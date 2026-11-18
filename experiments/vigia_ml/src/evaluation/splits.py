"""
Particionado reproducible sin fuga de datos (Actividad D).

Prohibe particiones aleatorias por fotograma cuando existen rafagas temporales
o capturas del mismo objeto fisico. Utiliza agrupamiento estricto por sesion,
clúster de duplicados o identificador de objeto fisico.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from sklearn.model_selection import GroupKFold


@dataclass(frozen=True)
class EvaluationSample:
    """Metadatos minimos requeridos para particionado y evaluacion sin fugas."""

    sample_id: str
    sha256: str
    source_domain: str
    session_id: str
    duplicate_group: str
    lighting_condition: str = "NORMAL"
    physical_object_id: Optional[str] = None
    true_label: Optional[str] = None
    ground_truth_verified: bool = False


class DataLeakageError(ValueError):
    """Error lanzado cuando se detecta fuga entre entrenamiento y evaluacion."""


def compute_composite_group_key(sample: EvaluationSample) -> str:
    """
    Combina ``session_id`` y ``physical_object_id`` (si existe) para garantizar
    que ninguna secuencia correlacionada o mismo vehiculo cruce folds.
    """
    if sample.physical_object_id:
        return f"{sample.session_id}::{sample.physical_object_id}"
    return sample.session_id


def separate_domains(
    samples: Sequence[EvaluationSample],
    allowed_domains: Sequence[str],
) -> List[EvaluationSample]:
    """Filtra muestras por dominio autorizado evitando mezclar laboratorio y real."""
    allowed = set(allowed_domains)
    return [s for s in samples if s.source_domain in allowed]


def assert_no_group_leakage(
    train_samples: Sequence[EvaluationSample],
    eval_samples: Sequence[EvaluationSample],
) -> None:
    """Verifica cero interseccion en SHA-256, sesion, duplicado y objeto fisico."""
    train_shas = {s.sha256 for s in train_samples}
    eval_shas = {s.sha256 for s in eval_samples}
    if train_shas & eval_shas:
        raise DataLeakageError("Fuga detectada: SHA-256 repetido entre train y eval.")

    train_dups = {s.duplicate_group for s in train_samples}
    eval_dups = {s.duplicate_group for s in eval_samples}
    if train_dups & eval_dups:
        raise DataLeakageError("Fuga detectada: mismo duplicate_group en train y eval.")

    train_sess = {s.session_id for s in train_samples}
    eval_sess = {s.session_id for s in eval_samples}
    if train_sess & eval_sess:
        raise DataLeakageError("Fuga detectada: misma session_id en train y eval.")

    train_objs = {s.physical_object_id for s in train_samples if s.physical_object_id}
    eval_objs = {s.physical_object_id for s in eval_samples if s.physical_object_id}
    if train_objs & eval_objs:
        raise DataLeakageError("Fuga detectada: mismo objeto fisico en train y eval.")


def generate_group_kfold_splits(
    samples: Sequence[EvaluationSample],
    *,
    n_splits: int = 3,
    allowed_domains: Optional[Sequence[str]] = None,
) -> List[Tuple[List[EvaluationSample], List[EvaluationSample]]]:
    """
    Genera particiones ``GroupKFold`` garantizando separacion de sesiones y dominios.
    """
    pool = (
        separate_domains(samples, allowed_domains)
        if allowed_domains is not None
        else list(samples)
    )
    groups = [compute_composite_group_key(s) for s in pool]
    unique_groups = set(groups)
    if len(unique_groups) < n_splits:
        raise ValueError(
            f"Grupos insuficientes ({len(unique_groups)}) para n_splits={n_splits}. "
            "No dividir arbitrariamente por fotograma."
        )

    gkf = GroupKFold(n_splits=n_splits)
    folds: List[Tuple[List[EvaluationSample], List[EvaluationSample]]] = []
    for train_idx, eval_idx in gkf.split(pool, groups=groups):
        tr = [pool[i] for i in train_idx]
        ev = [pool[i] for i in eval_idx]
        assert_no_group_leakage(tr, ev)
        folds.append((tr, ev))
    return folds
