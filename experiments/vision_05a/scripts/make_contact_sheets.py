"""
Genera hojas de contacto (contact sheets) numeradas para los 279 hashes SHA-256 únicos
de evidencias_vigia/, permitiendo inspección visual directa 100% verificada sin
modificar las evidencias originales.
"""

import json
from pathlib import Path
import cv2
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO_ROOT / "evidencias_vigia"
INV_PATH = REPO_ROOT / "experiments" / "vision_05a" / "results" / "etapa_a_b_raw_inventory.json"
CS_DIR = REPO_ROOT / "experiments" / "vision_05a" / "results" / "contact_sheets"
CS_DIR.mkdir(parents=True, exist_ok=True)


def main() -> None:
    data = json.load(open(INV_PATH, encoding="utf-8"))
    items = data["items"]
    unique_items = [it for it in items if not it["is_exact_duplicate"]]
    print(f"Total unique items: {len(unique_items)}")

    thumb_w, thumb_h = 200, 150
    cols, rows = 8, 8
    per_sheet = cols * rows

    for sheet_idx in range(0, len(unique_items), per_sheet):
        batch = unique_items[sheet_idx : sheet_idx + per_sheet]
        canvas = np.zeros((rows * thumb_h, cols * thumb_w, 3), dtype=np.uint8)
        for i, it in enumerate(batch):
            r = i // cols
            c = i % cols
            img = cv2.imread(str(EVIDENCE_DIR / it["relative_path"]))
            if img is None:
                continue
            resized = cv2.resize(img, (thumb_w, thumb_h), interpolation=cv2.INTER_AREA)
            label = f"{it['sample_id']} {it['date_folder'][-4:]}"
            ts_short = (it["file_name"].split("_")[0][-6:] if "_" in it["file_name"] else "")
            cv2.rectangle(resized, (0, 0), (thumb_w, 22), (0, 0, 0), -1)
            cv2.putText(
                resized,
                f"{label} {ts_short}",
                (4, 15),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.42,
                (0, 255, 255),
                1,
                cv2.LINE_AA,
            )
            y0, x0 = r * thumb_h, c * thumb_w
            canvas[y0 : y0 + thumb_h, x0 : x0 + thumb_w] = resized

        out_path = CS_DIR / f"sheet_{sheet_idx // per_sheet + 1:02d}.jpg"
        cv2.imwrite(str(out_path), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        print(f"Saved {out_path.name} ({len(batch)} thumbnails)")


if __name__ == "__main__":
    main()
