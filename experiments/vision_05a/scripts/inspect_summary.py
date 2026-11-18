import json
from collections import Counter, defaultdict

data = json.load(open("experiments/vision_05a/results/etapa_a_b_raw_inventory.json", encoding="utf-8"))
items = data["items"]
print("Total items:", len(items), "Unique SHA256:", data["unique_sha256_count"])

by_date = defaultdict(list)
for it in items:
    by_date[f"{it['date_folder']}/{it['camera_code']}"].append(it)

for k, lst in sorted(by_date.items()):
    uniq_sha = len({x["sha256"] for x in lst})
    pclusters = len({x["perceptual_duplicate_group"] for x in lst})
    res = Counter(x["resolution"] for x in lst)
    y26_070 = sum(1 for x in lst if x["yolo26x"]["roi_count_070"] > 0)
    y11_070 = sum(1 for x in lst if x["yolo11n"]["roi_count_070"] > 0)
    y26_025 = sum(1 for x in lst if x["yolo26x"]["roi_count_025"] > 0)
    y11_025 = sum(1 for x in lst if x["yolo11n"]["roi_count_025"] > 0)
    print(
        f"{k:22s} | n={len(lst):3d} | sha={uniq_sha:3d} | pclust={pclusters:3d} | res={dict(res)} "
        f"| 26x@0.70={y26_070:3d}/{len(lst):3d} (@0.25:{y26_025:3d}) "
        f"| 11n@0.70={y11_070:3d}/{len(lst):3d} (@0.25:{y11_025:3d})"
    )

print("\n--- Inspecting 20261114 and 20261116 frames where 26x@0.70 misses or differs from 11n, or multi-vehicle ---")
for it in items:
    if it["date_folder"] in ("20261104", "20261106", "20261110", "20261114", "20261116"):
        c26 = it["yolo26x"]["all_candidates_010"]
        c11 = it["yolo11n"]["all_candidates_010"]
        r26_70 = it["yolo26x"]["roi_count_070"]
        r11_70 = it["yolo11n"]["roi_count_070"]
        if r26_70 == 0 or r11_70 == 0 or len(c26) > 1 or len(c11) > 1:
            b26_str = [(b["label"], b["confidence"], b["bbox"], b["in_roi"]) for b in c26]
            b11_str = [(b["label"], b["confidence"], b["bbox"], b["in_roi"]) for b in c11]
            print(f"{it['sample_id']} | {it['relative_path']} | db={it.get('db_tipo_vehiculo_pred')}:{it.get('db_confianza_vehiculo')}")
            print(f"   26x: {b26_str}")
            print(f"   11n: {b11_str}")
