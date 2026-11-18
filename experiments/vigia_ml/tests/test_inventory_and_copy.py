import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

SANDBOX_ROOT = Path(__file__).resolve().parents[1]
if str(SANDBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(SANDBOX_ROOT))

from src.dataset.controlled_copy import execute_controlled_copy
from src.dataset.inventory import build_inventory, compute_sha256, resolve_source_domain


def _write_jpg(path: Path, bgr: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok = cv2.imwrite(str(path), bgr)
    assert ok


class TestInventoryAndControlledCopy(unittest.TestCase):
    def test_inventory_pairing_duplicates_and_sha256_copy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "evidencias_vigia"
            sandbox = tmp_path / "experiments" / "vigia_ml"
            sandbox.mkdir(parents=True, exist_ok=True)

            # Frame 1 y Frame 2 casi identicos (clúster duplicado)
            base_img = np.full((120, 160, 3), (30, 30, 200), dtype=np.uint8)
            near_dup = base_img.copy()
            near_dup[0:5, 0:5] = (32, 32, 202)
            # Frame 3 distinto en nueva fecha
            other_img = np.full((120, 160, 3), (200, 180, 40), dtype=np.uint8)
            cv2.rectangle(other_img, (20, 20), (130, 100), (20, 220, 220), -1)

            f1 = source / "20261114" / "CAM-SALIDA" / "20261114T010000_000000Z_aaaaaaaaaaaa_orig.jpg"
            f1a = source / "20261114" / "CAM-SALIDA" / "20261114T010000_000000Z_aaaaaaaaaaaa_annot.jpg"
            f2 = source / "20261114" / "CAM-SALIDA" / "20261114T010003_000000Z_bbbbbbbbbbbb_orig.jpg"
            f2a = source / "20261114" / "CAM-SALIDA" / "20261114T010003_000000Z_bbbbbbbbbbbb_annot.jpg"
            f3 = source / "20261111" / "CAM-ENTRADA" / "20261111T224000_000000Z_cccccccccccc_orig.jpg"

            _write_jpg(f1, base_img)
            _write_jpg(f1a, base_img)
            _write_jpg(f2, near_dup)
            _write_jpg(f2a, near_dup)
            _write_jpg(f3, other_img)

            orig_sha_before = compute_sha256(f1)

            records = build_inventory(source, sandbox)
            self.assertEqual(len(records), 3)
            by_date = {r.date_folder: r for r in records}
            self.assertEqual(by_date["20261111"].source_domain, "SCREEN_RECAPTURE")
            self.assertFalse(by_date["20261111"].pair_complete)

            recs_14 = [r for r in records if r.date_folder == "20261114"]
            self.assertEqual(len(recs_14), 2)
            self.assertEqual(recs_14[0].duplicate_group, recs_14[1].duplicate_group)
            self.assertEqual(recs_14[0].source_domain, "SCALE_MODEL_LAB")

            # Fecha desconocida nunca debe asumirse REAL_FULL_SCALE
            self.assertEqual(resolve_source_domain("20990101"), "UNKNOWN")

            # Copia controlada deduplicada (debe copiar 1 de 20261114 + 1 de 20261111 = 2 orig)
            receipt = execute_controlled_copy(
                source,
                sandbox,
                include_dates=("20261111", "20261114"),
                deduplicate_per_cluster=True,
                min_free_gb=0.1,
            )
            self.assertEqual(receipt["selected_pairs"], 2)
            self.assertEqual(receipt["sha256_verified_orig"], 2)
            self.assertEqual(compute_sha256(f1), orig_sha_before)
            self.assertTrue((sandbox / "data" / "raw" / "copy_receipt.json").is_file())


if __name__ == "__main__":
    unittest.main()
