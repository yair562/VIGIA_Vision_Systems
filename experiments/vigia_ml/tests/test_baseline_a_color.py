import sys
import unittest
from pathlib import Path

import numpy as np

SANDBOX_ROOT = Path(__file__).resolve().parents[1]
if str(SANDBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(SANDBOX_ROOT))

from src.color_analysis.baseline_classic import predict_color_classic


def _solid_bgr(b: int, g: int, r: int, size: tuple[int, int] = (120, 160)) -> np.ndarray:
    img = np.zeros((size[0], size[1], 3), dtype=np.uint8)
    img[:, :] = (b, g, r)
    return img


class TestBaselineAColor(unittest.TestCase):
    def test_primary_chromatic_and_achromatic_colors(self) -> None:
        # BGR colors
        cases = [
            (_solid_bgr(20, 20, 210), "RED"),
            (_solid_bgr(210, 40, 20), "BLUE"),
            (_solid_bgr(20, 220, 230), "YELLOW"),
            (_solid_bgr(40, 180, 35), "GREEN"),
            (_solid_bgr(235, 235, 235), "WHITE"),
            (_solid_bgr(45, 45, 45), "BLACK"),
        ]
        for img, expected in cases:
            pred = predict_color_classic(img)
            self.assertEqual(
                pred.predicted_color,
                expected,
                msg=f"Esperado {expected}, obtenido {pred.predicted_color} ({pred.reason})",
            )
            self.assertFalse(pred.is_indeterminate)
            self.assertGreater(pred.confidence, 0.30)

    def test_insufficient_signal_returns_indeterminate(self) -> None:
        # Imagen casi totalmente oscura (subexposicion severa)
        too_dark = _solid_bgr(8, 8, 10)
        pred_dark = predict_color_classic(too_dark)
        self.assertEqual(pred_dark.predicted_color, "INDETERMINATE")
        self.assertTrue(pred_dark.is_indeterminate)

        # ROI demasiado pequena
        normal = _solid_bgr(20, 20, 200)
        pred_small = predict_color_classic(normal, roi_xyxy=(0, 0, 12, 12))
        self.assertEqual(pred_small.predicted_color, "INDETERMINATE")
        self.assertTrue(pred_small.is_indeterminate)

        # Reflejo especular saturado severo (todo V=255, S=0)
        glare = _solid_bgr(255, 255, 255)
        pred_glare = predict_color_classic(glare)
        self.assertEqual(pred_glare.predicted_color, "INDETERMINATE")
        self.assertTrue(pred_glare.is_indeterminate)


if __name__ == "__main__":
    unittest.main()
