import sys
import unittest
from pathlib import Path

SANDBOX_ROOT = Path(__file__).resolve().parents[1]
if str(SANDBOX_ROOT) not in sys.path:
    sys.path.insert(0, str(SANDBOX_ROOT))

from src.dataset.annotation_schema import (
    AnnotationDataset,
    ImageAnnotationRecord,
    VehicleAnnotation,
    YoloAuxReference,
)


class TestAnnotationSchema(unittest.TestCase):
    def test_yolo_cannot_be_marked_ground_truth(self) -> None:
        with self.assertRaises(ValueError):
            YoloAuxReference(
                model_name="yolo11n.pt",
                bbox_xyxy=(10, 10, 100, 100),
                raw_class="car",
                confidence=0.91,
                is_ground_truth=True,
            )

    def test_valid_annotation_and_disagreement_tracking(self) -> None:
        ref = YoloAuxReference(
            model_name="yolo11n.pt",
            bbox_xyxy=(10, 10, 100, 100),
            raw_class="truck",
            confidence=0.65,
            is_ground_truth=False,
        )
        ann_a = VehicleAnnotation(
            annotation_id="obj_01",
            bbox_xyxy=(12, 12, 102, 98),
            vehicle_class="BUS",
            observed_color="YELLOW",
            visibility="FULL",
            occlusion="NONE",
            lighting_condition="NORMAL",
            blur_level="MODERATE",
            annotator_id="student_01",
            yolo_aux_reference=ref,
        )
        ann_b = VehicleAnnotation(
            annotation_id="obj_01",
            bbox_xyxy=(12, 12, 102, 98),
            vehicle_class="BUS",
            observed_color="ORANGE",
            visibility="FULL",
            occlusion="NONE",
            lighting_condition="NORMAL",
            blur_level="MODERATE",
            annotator_id="reviewer_01",
        )
        ds = AnnotationDataset(
            records=[
                ImageAnnotationRecord(
                    sample_id="s_001",
                    image_path="data/raw/sample.jpg",
                    sha256="a" * 64,
                    source_domain="SCALE_MODEL_LAB",
                    session_id="S01",
                    duplicate_group="S01_C001",
                    objects=[ann_a],
                )
            ]
        )
        diffs = ds.compare_double_annotation("s_001", ann_a, ann_b)
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0].field_name, "observed_color")
        self.assertEqual(ann_a.review_status, "DISPUTED")
        self.assertEqual(ds.records[0].ground_truth_status, "DISPUTED")

    def test_invalid_taxonomy_rejected(self) -> None:
        with self.assertRaises(ValueError):
            VehicleAnnotation(
                annotation_id="obj_bad",
                bbox_xyxy=(0, 0, 50, 50),
                vehicle_class="SPACESHIP",
                observed_color="RED",
                visibility="FULL",
                occlusion="NONE",
                lighting_condition="NORMAL",
                blur_level="SHARP",
                annotator_id="student_01",
            )


if __name__ == "__main__":
    unittest.main()
