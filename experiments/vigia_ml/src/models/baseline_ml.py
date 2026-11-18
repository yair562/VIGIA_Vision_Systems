"""
Baseline B — Diseno tecnico reproducible de Machine Learning clasico (SVM / Random Forest).

IMPORTANTE:
- En VIGIA-ML-02 NO se entrena ningun modelo definitivo ni de produccion.
- Este modulo define el contrato reproducible, la extraccion de caracteristicas,
  el soporte de rechazo ``INDETERMINATE`` por umbral de probabilidad y las
  salvaguardas contra mezcla de dominios o entrenamiento sin Ground Truth humano.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from src.models.color_features import ColorFeatureConfig, extract_color_feature_vector


@dataclass(frozen=True)
class BaselineMLConfig:
    model_type: str = "svm_rbf"  # 'svm_rbf' | 'random_forest'
    random_seed: int = 42
    indeterminate_proba_threshold: float = 0.50
    rf_n_estimators: int = 120
    svm_c: float = 2.0


class DomainSafetyError(ValueError):
    """Se lanza si se intenta validar/entrenar sin respetar aislamiento de dominios o GT."""


class BaselineMLColorPipeline:
    """
    Wrapper experimental sobre scikit-learn (``SVC`` / ``RandomForestClassifier``)
    con extraccion determinista de caracteristicas y abstencion ``INDETERMINATE``.
    """

    def __init__(
        self,
        ml_config: Optional[BaselineMLConfig] = None,
        feature_config: Optional[ColorFeatureConfig] = None,
    ) -> None:
        self.ml_config = ml_config or BaselineMLConfig()
        self.feature_config = feature_config or ColorFeatureConfig()
        self.pipeline = self._build_sklearn_pipeline(self.ml_config)
        self._is_fitted = False

    @staticmethod
    def _build_sklearn_pipeline(cfg: BaselineMLConfig) -> Pipeline:
        if cfg.model_type == "svm_rbf":
            clf = SVC(
                C=cfg.svm_c,
                kernel="rbf",
                probability=True,
                class_weight="balanced",
                random_state=cfg.random_seed,
            )
            return Pipeline([("scaler", StandardScaler()), ("clf", clf)])
        if cfg.model_type == "random_forest":
            clf = RandomForestClassifier(
                n_estimators=cfg.rf_n_estimators,
                class_weight="balanced_subsample",
                random_state=cfg.random_seed,
            )
            return Pipeline([("scaler", StandardScaler()), ("clf", clf)])
        raise ValueError(f"model_type no soportado: {cfg.model_type}")

    def fit_from_crops(
        self,
        crops_bgr: Sequence[np.ndarray],
        labels: Sequence[str],
        *,
        source_domains: Optional[Sequence[str]] = None,
        ground_truth_verified: bool = False,
        allow_sandbox_only: bool = False,
    ) -> "BaselineMLColorPipeline":
        """
        Ajusta el clasificador unicamente si las etiquetas cumplen trazabilidad:
        - Rechaza entrenar sin GT humano salvo prueba unitaria/sandbox explicita.
        - Rechaza mezclar datos reales 1:1 con recapturas/juguetes salvo separacion explicita.
        """
        if not ground_truth_verified and not allow_sandbox_only:
            raise DomainSafetyError(
                "Entrenamiento bloqueado: se requiere Ground Truth humano verificado "
                "(o allow_sandbox_only=True exclusivamente en pruebas aisladas)."
            )
        if len(crops_bgr) != len(labels) or len(crops_bgr) < 2:
            raise ValueError("Se requieren >= 2 pares (crop, label) consistentes.")
        if len(set(labels)) < 2:
            raise ValueError("Se requieren al menos 2 clases de color distintas.")

        if source_domains is not None:
            dom_set = set(source_domains)
            if "REAL_FULL_SCALE" in dom_set and (
                "SCALE_MODEL_LAB" in dom_set or "SCREEN_RECAPTURE" in dom_set
            ):
                raise DomainSafetyError(
                    "Prohibido mezclar muestras REAL_FULL_SCALE con SCALE_MODEL_LAB o "
                    "SCREEN_RECAPTURE dentro del mismo conjunto sin experimento declarado."
                )

        x_mat = np.vstack(
            [extract_color_feature_vector(img, None, self.feature_config) for img in crops_bgr]
        )
        self.pipeline.fit(x_mat, list(labels))
        self._is_fitted = True
        return self

    def predict_crop(
        self,
        image_bgr: np.ndarray,
        roi_xyxy: Optional[Tuple[int, int, int, int]] = None,
    ) -> Tuple[str, float, Dict[str, float]]:
        """Predice clase cromatica y probabilidad, devolviendo ``INDETERMINATE`` bajo umbral."""
        if not self._is_fitted:
            raise RuntimeError("BaselineMLColorPipeline no ha sido entrenado.")

        vec = extract_color_feature_vector(image_bgr, roi_xyxy, self.feature_config).reshape(1, -1)
        probs = self.pipeline.predict_proba(vec)[0]
        classes: List[str] = [str(c) for c in self.pipeline.classes_]
        prob_map = {cls_name: round(float(p), 4) for cls_name, p in zip(classes, probs)}
        best_idx = int(np.argmax(probs))
        best_cls = classes[best_idx]
        best_prob = float(probs[best_idx])

        if best_prob < self.ml_config.indeterminate_proba_threshold:
            return "INDETERMINATE", round(best_prob, 4), prob_map
        return best_cls, round(best_prob, 4), prob_map
