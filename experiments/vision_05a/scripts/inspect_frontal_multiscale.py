import json
from pathlib import Path
import cv2
from ultralytics import YOLO

inv = json.load(open("experiments/vision_05a/results/etapa_a_b_classified_inventory.json", encoding="utf-8"))["items"]
uniq = [it for it in inv if not it["is_exact_duplicate"]]
m = YOLO("experiments/yolo26x/weights/yolo26x.pt")
m.to("cuda:0")

for it in uniq:
    c = it["confirmed_visual_classification"]
    if c["has_frontal_car"] or c["has_frontal_bus"]:
        img = cv2.imread(str(Path("evidencias_vigia") / it["relative_path"]))
        r640 = m.predict(img, imgsz=640, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False)[0]
        r480 = m.predict(img, imgsz=480, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False)[0]
        r384 = m.predict(img, imgsz=384, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False)[0]
        r320 = m.predict(img, imgsz=320, classes=[2, 3, 5, 7], conf=0.10, quantize=16, nms=False, verbose=False)[0]
        b640 = [(m.names[int(b.cls[0])], round(float(b.conf[0]), 3), [int(x) for x in b.xyxy[0].tolist()]) for b in r640.boxes]
        b480 = [(m.names[int(b.cls[0])], round(float(b.conf[0]), 3), [int(x) for x in b.xyxy[0].tolist()]) for b in r480.boxes]
        b384 = [(m.names[int(b.cls[0])], round(float(b.conf[0]), 3), [int(x) for x in b.xyxy[0].tolist()]) for b in r384.boxes]
        b320 = [(m.names[int(b.cls[0])], round(float(b.conf[0]), 3), [int(x) for x in b.xyxy[0].tolist()]) for b in r320.boxes]
        max640 = max([x[1] for x in b640], default=0)
        if max640 < 0.70 or c["has_frontal_bus"]:
            print(f"{it['sample_id']} (car={c['has_frontal_car']}, bus={c['has_frontal_bus']})")
            print("  640:", b640)
            print("  480:", b480)
            print("  384:", b384)
            print("  320:", b320)
