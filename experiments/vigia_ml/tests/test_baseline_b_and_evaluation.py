import sys
import unittest
from pathlib import Path

import numpy as np

SANDBOX_ROOT = Path(__file__).resolve().parents[1]
if str(SANDBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(SANDBOX_ROOT))

from src.evaluation.metrics import evaluate_color_predictions
from src.evaluation.splits import (
    DataLeakageError,
    EvaluationSample,
    assert_no_group_leakage,
    generate_group_kfold_splits,
    separate_domains,
)
from src.models.baseline_ml import BaselineMLColorPipeline, BaselineMLConfig, DomainSafetyError
from src.models.color_features import ColorFeatureConfig, extract_color_feature_vector


class TestBaselineBAndEvaluation(unittest.TestCase):
    def test_feature_vector_and_ml_pipeline_contract(self) -> None:
        cfg = ColorFeatureConfig()
        red_crop = np.full((64, 64, 3), (20, 20, 210), dtype=np.uint8)
        blue_crop = np.full((64, 64, 3), (210, 30, 20), dtype=np.uint8)
        yellow_crop = np.full((64, 64, 3), (20, 215, 230), dtype=np.uint8)

        vec = extract_color_feature_vector(red_crop, config=cfg)
        self.assertEqual(vec.shape, (cfg.feature_dim,))
        self.assertFalse(np.isnan(vec).any())

        # Bloqueo si se intenta entrenar sin verificacion ni bandera sandbox
        ml_pipe = BaselineMLColorPipeline(BaselineMLConfig(model_type="random_forest"))
        with self.assertRaises(DomainSafetyError):
            ml_pipe.fit_from_crops([red_crop, blue_crop], ["RED", "BLUE"])

        # Bloqueo si mezcla REAL_FULL_SCALE y SCALE_MODEL_LAB
        with self.assertRaises(DomainSafetyError):
            ml_pipe.fit_from_crops(
                [red_crop, blue_crop],
                ["RED", "BLUE"],
                source_domains=["REAL_FULL_SCALE", "SCALE_MODEL_LAB"],
                ground_truth_verified=True,
            )

        # Ajuste controlado en sandbox sobre muestras sinteticas
        ml_pipe.fit_from_crops(
            [red_crop, red_crop, blue_crop, blue_crop, yellow_crop, yellow_crop],
            ["RED", "RED", "BLUE", "BLUE", "YELLOW", "YELLOW"],
            allow_sandbox_only=True,
        )
        pred_cls, prob, prob_map = ml_pipe.predict_crop(red_crop)
        self.assertEqual(pred_cls, "RED")
        self.assertIn("RED", prob_map)
        self.assertGreaterEqual(prob, 0.50)

    def test_group_kfold_blocks_leakage_and_separates_domains(self) -> None:
        samples = [
            EvaluationSample(f"s{i}", f"{i:064x}", "SCALE_MODEL_LAB", f"S{i//2}", f"C{i//2}")
            for i in range(6)
        ] + [
            EvaluationSample("r1", "f" * 64, "SCREEN_RECAPTURE", "S_REC", "C_REC")
        ]

        lab_only = separate_domains(samples, ["SCALE_MODEL_LAB"])
        self.assertEqual(len(lab_only), 6)

        folds = generate_group_kfold_splits(lab_only, n_splits=3)
        self.assertEqual(len(folds), 3)

        # Fuga deliberada de misma sesion entre train y eval debe fallar
        tr_bad = [EvaluationSample("a", "1" * 64, "SCALE_MODEL_LAB", "S0", "C0")]
        ev_bad = [EvaluationSample("b", "2" * 64, "SCALE_MODEL_LAB", "S0", "C99")]
        with self.assertRaises(DataLeakageError):
            assert_no_group_leakage(tr_bad, ev_bad)

    def test_metrics_report_indeterminate_lighting_and_disclaimer(self) -> None:
        res = evaluate_color_predictions(
            y_true=["RED", "YELLOW", "RED", "BLUE"],
            y_pred=["RED", "INDETERMINATE", "RED", "BLUE"],
            lighting_conditions=["NORMAL", "LOW_LIGHT", "GLARE", "NORMAL"],
            source_domains=["SCALE_MODEL_LAB"] * 4,
            all_ground_truth_human=False,
        )
        self.assertEqual(res["total_samples"], 4)
        self.assertEqual(res["indeterminate_count"], 1)
        self.assertEqual(res["indeterminate_rate"], 0.25)
        self.assertFalse(res["real_world_representative"])
        self.assertIn("LOW_LIGHT", res["by_lighting_condition"])


if __name__ == "__main__":
    unittest.main()
