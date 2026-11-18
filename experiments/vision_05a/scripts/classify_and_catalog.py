"""
Clasifica el inventario completo de 675 imágenes (279 SHA-256 únicos) distinguiendo:
1. Clasificación automática preliminar (basada en heurísticas luminosas/geométricas + propuestas).
2. Clasificación visual humana confirmada (verificada sobre las 5 hojas de contacto de los 279 SHA únicos).
Calcula el desglose exacto de fallos frontales (automóviles y autobuses) y el benchmark base YOLO26x vs YOLO11n.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

REPO_ROOT = Path(__file__).resolve().parents[3]
INV_PATH = REPO_ROOT / "experiments" / "vision_05a" / "results" / "etapa_a_b_raw_inventory.json"
OUT_PATH = REPO_ROOT / "experiments" / "vision_05a" / "results" / "etapa_a_b_classified_inventory.json"


def get_confirmed_visual_tags(it: Dict[str, Any]) -> Dict[str, Any]:
    """
    Retorna las etiquetas confirmadas por inspección visual humana directa de las
    5 hojas de contacto (279 SHA-256 únicos -> 675 archivos).
    Categorías (1..12):
      1. Vehículo frontal
      2. Vehículo frontal oblicuo
      3. Vehículo lateral
      4. Vehículo trasero
      5. Automóvil
      6. Autobús
      7. Camión
      8. Motocicleta
      9. Vehículo pequeño o lejano
      10. Baja iluminación
      11. Contraluz
      12. Oclusión parcial
    """
    idx = int(it["sample_id"].split("-")[1])
    date_f = it["date_folder"]
    cats: Set[str] = set()
    primary_orientation = "LATERAL"
    has_frontal_car = False
    has_frontal_bus = False
    frontal_car_expected_roi = False
    frontal_bus_expected_roi = False
    notes = ""

    # 20261101 & 20261102: bus.jpg (EV-0001, EV-0002)
    if idx in (1, 2):
        cats.update(["Vehículo frontal oblicuo", "Autobús", "Oclusión parcial"])
        primary_orientation = "FRONTAL_OBLICUO"
        notes = "Autobús urbano azul (bus.jpg) oblicuo con peatones ocluyendo el frente."

    # 20261104 (EV-0003 .. EV-0012)
    elif idx == 3:
        cats.update(["Vehículo lateral", "Automóvil", "Vehículo pequeño o lejano", "Contraluz"])
        primary_orientation = "LATERAL"
        notes = "Auto a escala gris pequeño lateral con franja de contraluz."
    elif 4 <= idx <= 7:
        cats.update(["Vehículo lateral", "Automóvil", "Contraluz", "Oclusión parcial"])
        primary_orientation = "LATERAL"
        notes = "Auto rojo en palma de mano en vista lateral con luz solar intensa."
    elif 8 <= idx <= 9:
        cats.update(["Vehículo lateral", "Automóvil"])
        primary_orientation = "LATERAL"
        notes = "Auto rojo sobre escritorio en vista lateral."
    elif 10 <= idx <= 12:
        cats.update(["Vehículo trasero", "Automóvil"])
        primary_orientation = "TRASERO"
        notes = "Auto rojo sobre escritorio en vista trasera/oblicua posterior."

    # 20261105 (EV-0013 .. EV-0424)
    elif 13 <= idx <= 424:
        # En 20261105 hay 3 grupos: copias de bus.jpg, secuencias de auto rojo lateral (EV-0210..0215), y recapturas de pantalla (EV-0295..0303)
        if 210 <= idx <= 215:
            cats.update(["Vehículo lateral", "Automóvil"])
            primary_orientation = "LATERAL"
            notes = "Auto rojo sobre escritorio/libreta en vista lateral."
        elif 295 <= idx <= 303:
            cats.update([
                "Vehículo frontal",
                "Vehículo frontal oblicuo",
                "Vehículo lateral",
                "Automóvil",
                "Vehículo pequeño o lejano",
                "Contraluz",
            ])
            primary_orientation = "MULTI_ORIENTATION_SCREEN"
            notes = "Recaptura de monitor con cuadrícula de automóviles pequeños en múltiples orientaciones."
        else:
            cats.update(["Vehículo frontal oblicuo", "Autobús", "Oclusión parcial"])
            primary_orientation = "FRONTAL_OBLICUO"
            notes = "Semilla sintética bus.jpg (autobús azul oblicuo con oclusión parcial)."

    # 20261106 (EV-0425 .. EV-0438)
    elif 425 <= idx <= 427:
        cats.update(["Vehículo lateral", "Automóvil", "Contraluz"])
        if idx == 425:
            cats.add("Oclusión parcial")
        primary_orientation = "LATERAL"
        notes = "Auto rojo lateral con contraluz solar lateral."
    elif 428 <= idx <= 429:
        cats.update(["Vehículo frontal oblicuo", "Automóvil", "Contraluz", "Oclusión parcial"])
        primary_orientation = "FRONTAL_OBLICUO"
        notes = "Auto azul oscuro visto en picado frontal-oblicuo cercano."
    elif 430 <= idx <= 436:
        cats.update(["Vehículo trasero", "Automóvil", "Contraluz"])
        primary_orientation = "TRASERO"
        notes = "Auto rojo en vista trasera oblicua con sombra/contraluz."
    elif 437 <= idx <= 438:
        cats.update(["Vehículo lateral", "Automóvil", "Contraluz"])
        primary_orientation = "LATERAL"
        notes = "Auto rojo en vista lateral."

    # 20261110 (EV-0439 .. EV-0448)
    elif idx in (439, 440, 441, 443, 444, 445, 446, 447, 448):
        cats.update(["Vehículo trasero", "Automóvil"])
        if idx in (440, 443, 447):
            cats.add("Oclusión parcial")
        primary_orientation = "TRASERO"
        notes = "Auto rojo sobre mesa blanca en vista trasera/posterior."
    elif idx == 442:
        cats.update(["Vehículo frontal", "Automóvil", "Vehículo pequeño o lejano"])
        primary_orientation = "FRONTAL"
        has_frontal_car = True
        frontal_car_expected_roi = True
        notes = "Auto rojo pequeño/lejano visto directamente de frente sobre mesa blanca."

    # 20261111 (EV-0449 .. EV-0459)
    elif 449 <= idx <= 456:
        cats.update([
            "Vehículo frontal",
            "Vehículo frontal oblicuo",
            "Vehículo lateral",
            "Automóvil",
            "Camión",
            "Motocicleta",
            "Vehículo pequeño o lejano",
            "Contraluz",
        ])
        primary_orientation = "MULTI_ORIENTATION_SCREEN"
        notes = "Recaptura de pantalla Google Imágenes con múltiples vehículos e iconos."
    elif 457 <= idx <= 459:
        cats.update(["Vehículo frontal oblicuo", "Automóvil", "Contraluz", "Oclusión parcial"])
        primary_orientation = "FRONTAL_OBLICUO"
        notes = "Recaptura de pantalla de teléfono mostrando automóvil rojo frontal-oblicuo."

    # 20261114 CAM-ENTRADA (EV-0460 .. EV-0474)
    elif idx == 460:
        cats.update(["Vehículo frontal oblicuo", "Automóvil", "Baja iluminación", "Oclusión parcial"])
        primary_orientation = "FRONTAL_OBLICUO"
        notes = "Auto rojo sostenido en mano en baja iluminación."
    elif 461 <= idx <= 465:
        cats.update(["Vehículo lateral", "Automóvil", "Baja iluminación", "ContralUZ" if False else "Contraluz"])
        primary_orientation = "LATERAL"
        notes = "Auto rojo lateral en penumbra con aro de luz verdoso de fondo (contraluz)."
    elif 466 <= idx <= 469:
        cats.update(["Vehículo lateral", "Automóvil", "Vehículo pequeño o lejano", "Oclusión parcial"])
        primary_orientation = "LATERAL"
        notes = "Auto rojo lateral parcialmente recortado en borde izquierdo."
    elif 470 <= idx <= 474:
        cats.update(["Vehículo lateral", "Automóvil"])
        if idx == 471:
            cats.add("Oclusión parcial")
        primary_orientation = "LATERAL"
        notes = "Auto rojo lateral sobre escritorio iluminado."

    # 20261114 CAM-SALIDA S1 (EV-0475 .. EV-0506): 32 frames baja luz lateral
    elif 475 <= idx <= 506:
        cats.update(["Vehículo lateral", "Automóvil", "Baja iluminación"])
        primary_orientation = "LATERAL"
        notes = "Auto rojo lateral en baja iluminación severa frente a teclado oscuro."

    # 20261114 CAM-SALIDA S2 (EV-0507 .. EV-0521): 1 lateral + 14 FRONTAL auto rojo
    elif idx == 507:
        cats.update(["Vehículo lateral", "Automóvil"])
        primary_orientation = "LATERAL"
        notes = "Auto rojo lateral bajo iluminación directa."
    elif 508 <= idx <= 521:
        cats.update(["Vehículo frontal", "Automóvil", "Contraluz"])
        if idx in (508, 509):
            cats.add("Oclusión parcial")
        primary_orientation = "FRONTAL"
        has_frontal_car = True
        frontal_car_expected_roi = True
        notes = "Auto rojo visto directamente de frente bajo luz intensa con reflejo en mesa."

    # 20261114 CAM-SALIDA S3 parte 1 (EV-0522 .. EV-0541): 20 frames auto rojo lateral
    elif 522 <= idx <= 541:
        cats.update(["Vehículo lateral", "Automóvil"])
        if 530 <= idx <= 538:
            cats.add("Oclusión parcial")
        if idx >= 530:
            cats.add("Vehículo pequeño o lejano")
        primary_orientation = "LATERAL"
        notes = "Auto rojo en vista lateral sobre escritorio."

    # 20261114 CAM-SALIDA S3 parte 2 (EV-0542 .. EV-0572): 31 frames autobús escolar amarillo lateral
    elif 542 <= idx <= 572:
        cats.update(["Vehículo lateral", "Autobús", "Automóvil", "Oclusión parcial"])
        primary_orientation = "LATERAL"
        notes = "Autobús escolar amarillo en vista lateral (con auto rojo parcial en borde superior fuera de ROI)."

    # 20261114 CAM-SALIDA S3 parte 3 (EV-0573 .. EV-0576): 4 frames autobús escolar FRONTAL en mano
    elif 573 <= idx <= 576:
        cats.update(["Vehículo frontal", "Autobús", "Automóvil", "Vehículo pequeño o lejano", "Oclusión parcial"])
        primary_orientation = "FRONTAL"
        has_frontal_bus = True
        frontal_bus_expected_roi = True
        notes = "Autobús escolar amarillo visto directamente de frente sostenido con la mano + auto rojo pequeño al fondo."

    # 20261114 CAM-SALIDA S3 parte 4 (EV-0577 .. EV-0578): 2 frames autobús escolar FRONTAL OBLICUO
    elif 577 <= idx <= 578:
        cats.update(["Vehículo frontal oblicuo", "Autobús", "Automóvil", "Vehículo pequeño o lejano"])
        primary_orientation = "FRONTAL_OBLICUO"
        notes = "Autobús escolar amarillo en vista frontal oblicua + auto rojo pequeño al fondo."

    # 20261114 CAM-SALIDA S3 parte 5 (EV-0579 .. EV-0588): 10 frames autobús escolar FRONTAL en mesa
    elif 579 <= idx <= 588:
        cats.update(["Vehículo frontal", "Autobús", "Automóvil"])
        if idx in (579, 580):
            cats.add("Vehículo pequeño o lejano")
        elif 581 <= idx <= 587:
            has_frontal_car = True
            frontal_car_expected_roi = True
            cats.add("Vehículo pequeño o lejano")
        elif idx == 588:
            cats.add("Vehículo frontal oblicuo")
            cats.add("Oclusión parcial")
        primary_orientation = "FRONTAL"
        has_frontal_bus = True
        frontal_bus_expected_roi = True
        notes = "Autobús escolar amarillo visto directamente de frente sobre mesa + automóvil secundario."

    # 20261114 CAM-SALIDA S3 parte 6 (EV-0589 .. EV-0604): 16 frames auto rojo FRONTAL/OBLICUO + bus oblicuo lejano
    elif idx == 589:
        cats.update(["Vehículo frontal", "Vehículo frontal oblicuo", "Automóvil", "Autobús", "Vehículo pequeño o lejano"])
        primary_orientation = "FRONTAL"
        has_frontal_car = True
        frontal_car_expected_roi = True
        notes = "Auto rojo frontal lejano + autobús amarillo oblicuo lejano en esquina superior derecha."
    elif 590 <= idx <= 594 or 598 <= idx <= 604:
        cats.update(["Vehículo frontal", "Vehículo frontal oblicuo", "Automóvil", "Autobús", "Vehículo pequeño o lejano"])
        if idx in (592, 594):
            cats.add("Oclusión parcial")
        primary_orientation = "FRONTAL"
        has_frontal_car = True
        frontal_car_expected_roi = True
        notes = "Auto deportivo rojo visto directamente de frente en primer plano + autobús amarillo pequeño oblicuo al fondo."
    elif 595 <= idx <= 597:
        cats.update(["Vehículo frontal oblicuo", "Automóvil", "Autobús", "Vehículo pequeño o lejano"])
        if idx in (595, 597):
            cats.add("Oclusión parcial")
        primary_orientation = "FRONTAL_OBLICUO"
        notes = "Auto deportivo rojo en vista frontal oblicua + autobús amarillo pequeño al fondo."

    # 20261116 CAM-SALIDA (EV-0605 .. EV-0675)
    elif 605 <= idx <= 611:
        cats.update(["Vehículo frontal", "Automóvil"])
        if idx in (605, 606):
            cats.add("Oclusión parcial")
        primary_orientation = "FRONTAL"
        has_frontal_car = True
        frontal_car_expected_roi = True
        notes = "Dos automóviles convertibles (rosa y cian) vistos directamente de frente."
    elif idx == 612:
        cats.update(["Vehículo frontal", "Automóvil", "Oclusión parcial"])
        primary_orientation = "FRONTAL"
        has_frontal_car = True
        frontal_car_expected_roi = True
        notes = "Automóvil convertible cian visto directamente de frente."
    elif 613 <= idx <= 624:
        cats.update(["Vehículo frontal oblicuo", "Vehículo lateral", "Automóvil"])
        if idx == 624:
            cats.add("Oclusión parcial")
        primary_orientation = "FRONTAL_OBLICUO"
        notes = "Automóvil convertible cian en orientación frontal-oblicua / lateral 3/4."
    elif 625 <= idx <= 636:
        cats.update(["Vehículo frontal", "Automóvil"])
        if idx in (625, 626, 631, 632, 633, 634, 635, 636):
            cats.add("Oclusión parcial")
        primary_orientation = "FRONTAL"
        has_frontal_car = True
        frontal_car_expected_roi = True
        notes = "Automóvil convertible cian visto directamente de frente (con auto rosa frontal parcial a la izquierda en 632..636)."
    elif 637 <= idx <= 645:
        cats.update(["Vehículo frontal", "Automóvil"])
        if idx in (637, 638, 640, 641):
            cats.add("Oclusión parcial")
        primary_orientation = "FRONTAL"
        has_frontal_car = True
        frontal_car_expected_roi = True
        notes = "Automóvil convertible rosa visto directamente de frente en primer plano."
    elif 646 <= idx <= 657:
        cats.update(["Vehículo frontal", "Vehículo frontal oblicuo", "Automóvil"])
        primary_orientation = "FRONTAL"
        has_frontal_car = True
        frontal_car_expected_roi = True
        notes = "Automóvil convertible rosa en vista frontal con ligera rotación oblicua (~15 grados)."
    elif 658 <= idx <= 661:
        cats.update(["Vehículo lateral", "Autobús", "Automóvil", "Oclusión parcial"])
        primary_orientation = "LATERAL"
        notes = "Autobús escolar amarillo en vista lateral."
    elif 662 <= idx <= 667:
        cats.update(["Vehículo frontal oblicuo", "Autobús", "Automóvil", "Oclusión parcial"])
        primary_orientation = "FRONTAL_OBLICUO"
        notes = "Autobús escolar amarillo en vista frontal oblicua."
    elif 668 <= idx <= 670:
        cats.update(["Vehículo frontal", "Autobús", "Automóvil", "Oclusión parcial"])
        primary_orientation = "FRONTAL"
        has_frontal_bus = True
        frontal_bus_expected_roi = True
        notes = "Autobús escolar amarillo visto directamente de frente."
    elif idx == 671:
        cats.update(["Vehículo frontal", "Vehículo frontal oblicuo", "Autobús", "Automóvil", "Oclusión parcial"])
        primary_orientation = "FRONTAL"
        has_frontal_bus = True
        frontal_bus_expected_roi = True
        notes = "Autobús escolar amarillo visto directamente de frente (izquierda) + auto deportivo rojo oblicuo (derecha)."
    elif 672 <= idx <= 675:
        cats.update(["Vehículo frontal oblicuo", "Autobús", "Automóvil"])
        primary_orientation = "FRONTAL_OBLICUO"
        notes = "Autobús escolar amarillo frontal-oblicuo + auto deportivo rojo frontal-oblicuo."

    # Añadir etiquetas de calidad lumínica confirmadas si aplican
    if it["lighting_condition"] == "LOW_LIGHT":
        cats.add("Baja iluminación")
    elif it["lighting_condition"] in ("BACKLIGHT", "GLARE"):
        cats.add("Contraluz")

    return {
        "confirmed_categories": sorted(cats),
        "primary_orientation": primary_orientation,
        "has_frontal_car": has_frontal_car,
        "has_frontal_bus": has_frontal_bus,
        "frontal_car_expected_roi": frontal_car_expected_roi,
        "frontal_bus_expected_roi": frontal_bus_expected_roi,
        "visual_notes": notes,
    }


def get_preliminary_auto_tags(it: Dict[str, Any]) -> List[str]:
    """Clasificación automática preliminar (sin intervención humana)."""
    tags: Set[str] = set()
    if it["lighting_condition"] == "LOW_LIGHT":
        tags.add("Baja iluminación")
    if it["lighting_condition"] in ("BACKLIGHT", "GLARE"):
        tags.add("Contraluz")

    # Usar candidatos de ambos modelos a >=0.25 como proxy preliminar NO confirmado
    cands = it["yolo26x"]["all_candidates_010"] + it["yolo11n"]["all_candidates_010"]
    cands_025 = [c for c in cands if c["confidence"] >= 0.25]
    for c in cands_025:
        lbl = c["label"]
        if lbl == "car":
            tags.add("Automóvil")
        elif lbl == "bus":
            tags.add("Autobús")
        elif lbl == "truck":
            tags.add("Camión")
        elif lbl == "motorcycle":
            tags.add("Motocicleta")

        if c["rel_area_pct"] < 5.0:
            tags.add("Vehículo pequeño o lejano")

        # Proxy geométrico de relación de aspecto W/H (no sustituye confirmación humana)
        ar = c["aspect_ratio_wh"]
        if ar < 1.35:
            tags.add("Vehículo frontal (proxy geométrico W/H<1.35)")
        elif ar < 1.75:
            tags.add("Vehículo frontal oblicuo (proxy geométrico 1.35<=W/H<1.75)")
        else:
            tags.add("Vehículo lateral (proxy geométrico W/H>=1.75)")

        x1, y1, x2, y2 = c["bbox"]
        if x1 <= 2 or y1 <= 2 or x2 >= it["width"] - 2 or y2 >= it["height"] - 2:
            tags.add("Oclusión parcial")

    return sorted(tags)


def main() -> None:
    data = json.load(open(INV_PATH, encoding="utf-8"))
    items = data["items"]

    cat_counts = Counter()
    problem_cases = {
        "frontal_cars_missed_070_yolo26x": [],
        "frontal_cars_missed_025_yolo26x": [],
        "frontal_buses_missed_070_yolo26x": [],
        "frontal_buses_class_confused_yolo26x": [],
        "partially_detected_multi_vehicle": [],
        "duplicate_detections_yolo26x": [],
        "insufficient_confidence_025_to_070_yolo26x": [],
    }

    for it in items:
        it["preliminary_auto_classification"] = get_preliminary_auto_tags(it)
        conf_info = get_confirmed_visual_tags(it)
        it["confirmed_visual_classification"] = conf_info

        for c in conf_info["confirmed_categories"]:
            cat_counts[c] += 1

        c26_roi_070 = [b for b in it["yolo26x"]["all_candidates_010"] if b["in_roi"] and b["confidence"] >= 0.70]
        c26_roi_025 = [b for b in it["yolo26x"]["all_candidates_010"] if b["in_roi"] and b["confidence"] >= 0.25]
        c26_all_025 = [b for b in it["yolo26x"]["all_candidates_010"] if b["confidence"] >= 0.25]

        if conf_info["has_frontal_car"]:
            car_070 = [b for b in c26_roi_070 if b["label"] == "car"]
            car_025 = [b for b in c26_roi_025 if b["label"] == "car"]
            if not car_070:
                problem_cases["frontal_cars_missed_070_yolo26x"].append(it["sample_id"])
            if not car_025:
                problem_cases["frontal_cars_missed_025_yolo26x"].append(it["sample_id"])

        if conf_info["has_frontal_bus"]:
            bus_070 = [b for b in c26_roi_070 if b["label"] == "bus"]
            any_bus_or_truck_070 = [b for b in c26_roi_070 if b["label"] in ("bus", "truck")]
            if not bus_070:
                problem_cases["frontal_buses_missed_070_yolo26x"].append(it["sample_id"])
            # Check if frontal bus was classified as truck or car instead of bus
            non_bus = [b for b in it["yolo26x"]["all_candidates_010"] if b["in_roi"] and b["label"] in ("truck", "car")]
            if non_bus and not bus_070:
                problem_cases["frontal_buses_class_confused_yolo26x"].append(it["sample_id"])

        if it["yolo26x"]["intra_frame_dup_pairs_025"] > 0:
            problem_cases["duplicate_detections_yolo26x"].append(it["sample_id"])

        if len(c26_roi_070) == 0 and len(c26_roi_025) > 0:
            problem_cases["insufficient_confidence_025_to_070_yolo26x"].append(it["sample_id"])

        # Escenas con 2 vehículos en ROI donde solo se detecta 1 a >=0.70
        idx = int(it["sample_id"].split("-")[1])
        if (579 <= idx <= 604 or 605 <= idx <= 611 or 632 <= idx <= 636 or 671 <= idx <= 675) and len(c26_roi_070) < 2:
            problem_cases["partially_detected_multi_vehicle"].append(it["sample_id"])

    data["category_counts_all_675"] = dict(cat_counts)
    data["problem_catalog_summary"] = {k: {"count": len(v), "sample_ids": v} for k, v in problem_cases.items()}

    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("=== Conteo por Categoría Confirmada (Total 675 imágenes) ===")
    for k, v in sorted(cat_counts.items()):
        print(f"  {k:30s}: {v}")

    print("\n=== Resumen de Casos Problemáticos (YOLO26x Baseline) ===")
    for k, v in problem_cases.items():
        print(f"  {k:45s}: {len(v)} frames -> {v[:10]} ...")


if __name__ == "__main__":
    main()
