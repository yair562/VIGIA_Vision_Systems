"""
Metricas reproducibles de evaluacion para reconocimiento de atributos vehiculares.

Calcula:
- Accuracy, Precision, Recall y F1-score (macro y por clase).
- Matriz de confusion ordenada por etiqueta.
- Porcentaje de predicciones ``INDETERMINATE``.
- Desglose estratificado por ``lighting_condition``.
- Bandera explicita ``real_world_representative`` (solo True si 100% de las
  muestras son ``REAL_FULL_SCALE`` con Ground Truth humano verificado).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Dict, List, Optional, Sequence

from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    precision_recall_fscore_support,
)


def evaluate_color_predictions(
    y_true: Sequence[str],
    y_pred: Sequence[str],
    *,
    lighting_conditions: Optional[Sequence[str]] = None,
    source_domains: Optional[Sequence[str]] = None,
    all_ground_truth_human: bool = False,
    labels_order: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    """Calcula el conjunto completo de metricas requeridas en Actividad D."""
    if len(y_true) != len(y_pred) or len(y_true) == 0:
        raise ValueError("y_true e y_pred deben tener la misma longitud (> 0).")

    n = len(y_true)
    indet_count = sum(1 for p in y_pred if p == "INDETERMINATE")
    indet_rate = round(indet_count / n, 4)

    ordered_labels: List[str] = (
        list(labels_order)
        if labels_order is not None
        else sorted(set(y_true) | set(y_pred))
    )

    acc = float(accuracy_score(y_true, y_pred))
    p_macro, r_macro, f1_macro, _ = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=ordered_labels,
        average="macro",
        zero_division=0,
    )
    p_cls, r_cls, f1_cls, supp_cls = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=ordered_labels,
        average=None,
        zero_division=0,
    )
    cm = confusion_matrix(y_true, y_pred, labels=ordered_labels).tolist()

    per_class = {
        lbl: {
            "precision": round(float(p), 4),
            "recall": round(float(r), 4),
            "f1": round(float(f1), 4),
            "support": int(sup),
        }
        for lbl, p, r, f1, sup in zip(ordered_labels, p_cls, r_cls, f1_cls, supp_cls)
    }

    by_lighting: Dict[str, Dict[str, float | int]] = {}
    if lighting_conditions is not None:
        if len(lighting_conditions) != n:
            raise ValueError("lighting_conditions debe coincidir en longitud con y_true.")
        grouped: Dict[str, List[int]] = defaultdict(list)
        for idx, cond in enumerate(lighting_conditions):
            grouped[cond].append(idx)
        for cond, idxs in sorted(grouped.items()):
            yt_c = [y_true[i] for i in idxs]
            yp_c = [y_pred[i] for i in idxs]
            acc_c = float(accuracy_score(yt_c, yp_c))
            _, _, f1_c, _ = precision_recall_fscore_support(
                yt_c, yp_c, average="macro", zero_division=0
            )
            ind_c = sum(1 for p in yp_c if p == "INDETERMINATE") / len(idxs)
            by_lighting[cond] = {
                "samples": len(idxs),
                "accuracy": round(acc_c, 4),
                "f1_macro": round(float(f1_c), 4),
                "indeterminate_rate": round(ind_c, 4),
            }

    domain_counts = dict(Counter(source_domains)) if source_domains is not None else {}
    only_real = (
        source_domains is not None
        and len(source_domains) == n
        and all(d == "REAL_FULL_SCALE" for d in source_domains)
    )
    real_rep = bool(only_real and all_ground_truth_human)

    return {
        "total_samples": n,
        "accuracy": round(acc, 4),
        "precision_macro": round(float(p_macro), 4),
        "recall_macro": round(float(r_macro), 4),
        "f1_macro": round(float(f1_macro), 4),
        "indeterminate_count": indet_count,
        "indeterminate_rate": indet_rate,
        "labels_order": ordered_labels,
        "confusion_matrix": cm,
        "per_class": per_class,
        "by_lighting_condition": by_lighting,
        "source_domains": domain_counts,
        "real_world_representative": real_rep,
        "disclaimer": (
            "Evaluacion valida sobre dataset real 1:1 con GT humano."
            if real_rep
            else "EXPERIMENTAL / SANDBOX: No representativo de operacion vehicular real 1:1."
        ),
    }
