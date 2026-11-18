"""
scratch/run_full_test_audit.py
==============================
Ejecuta la auditoría integral de pruebas automatizadas para VIGÍA Vision Systems
(Fase VISION-05B.1).

Agrupa las suites en:
1. Visión Artificial, FSM, YOLO y Clasificación de Color.
2. Subsistemas de Seguridad, Red, Ingesta, IPC y Persistencia.
"""

from __future__ import annotations

import io
import sys
import time
import unittest
from pathlib import Path
from typing import Dict, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

VISION_SUITES = [
    "tests.unit.test_domain_models",
    "tests.unit.test_detection_repository",
    "tests.unit.test_topology_validator",
    "tests.unit.test_vision_stage1_components",
    "tests.unit.test_vision_02a_temporal_fsm",
    "tests.unit.test_vision_03c2_yolo26x_integration",
    "tests.unit.test_vision_04a_progressive_integration",
    "tests.unit.test_vision_05a_frontal_optimization",
    "tests.unit.test_vision_05b_color_classifier",
    "tests.unit.test_vision_pipeline",
    "tests.unit.test_yolo_detector",
]

SYSTEM_SUITES = [
    "tests.unit.test_async_persistence_pilot",
    "tests.unit.test_auth_rbac",
    "tests.unit.test_auth_stream_protection",
    "tests.unit.test_camera",
    "tests.unit.test_camera_stream_and_backend",
    "tests.unit.test_crl_management",
    "tests.unit.test_ipc_hardening",
    "tests.unit.test_isolated_signer",
    "tests.unit.test_lan_detector",
    "tests.unit.test_mobile_ingest_api",
    "tests.unit.test_network_discovery",
    "tests.unit.test_signer_fail_closed",
]


def run_suite_group(group_name: str, module_names: List[str]) -> Tuple[int, int, int, int, float, List[Dict]]:
    print(f"\n{'='*80}")
    print(f"EJECUTANDO GRUPO: {group_name} ({len(module_names)} suites)")
    print(f"{'='*80}")

    total_runs = 0
    total_passes = 0
    total_failures = 0
    total_errors = 0
    total_skipped = 0
    t0_group = time.perf_counter()
    details = []

    loader = unittest.TestLoader()

    for mod_name in module_names:
        t0_mod = time.perf_counter()
        try:
            suite = loader.loadTestsFromName(mod_name)
        except Exception as e:
            print(f"[ERROR CARGANDO] {mod_name}: {e}")
            details.append({"module": mod_name, "status": "LOAD_ERROR", "error": str(e)})
            continue

        # Capturar salida para mantener formato limpio
        stream = io.StringIO()
        runner = unittest.TextTestRunner(stream=stream, verbosity=1)
        result = runner.run(suite)
        dt_mod = time.perf_counter() - t0_mod

        runs = result.testsRun
        fails = len(result.failures)
        errs = len(result.errors)
        skips = len(result.skipped)
        passes = runs - fails - errs - skips

        total_runs += runs
        total_passes += passes
        total_failures += fails
        total_errors += errs
        total_skipped += skips

        status_str = "PASS" if (fails == 0 and errs == 0) else "FAIL"
        print(f"  [{status_str:4s}] {mod_name:50s} | Runs: {runs:3d} | Pass: {passes:3d} | Skip: {skips:2d} | Fail: {fails:1d} | Err: {errs:1d} | {dt_mod:6.2f}s")

        if fails > 0 or errs > 0:
            for f in result.failures:
                print(f"         FAILURE in {f[0]}: {f[1][:200]}...")
            for e in result.errors:
                print(f"         ERROR in {e[0]}: {e[1][:200]}...")

        details.append({
            "module": mod_name,
            "runs": runs,
            "passes": passes,
            "failures": fails,
            "errors": errs,
            "skipped": skips,
            "duration_sec": round(dt_mod, 3),
            "status": status_str,
        })

    group_duration = time.perf_counter() - t0_group
    print(f"\nResumen Grupo '{group_name}': {total_runs} pruebas | {total_passes} pasadas | {total_skipped} omitidas | {total_failures} fallos | {total_errors} errores | {group_duration:.2f}s")
    return total_runs, total_passes, total_failures, total_errors, group_duration, details


def main():
    print("Iniciando Verificación de Regresión Completa para VISION-05B.1...")
    t_start = time.perf_counter()

    vis_runs, vis_pass, vis_fail, vis_err, vis_dur, vis_details = run_suite_group("VISIÓN, FSM, YOLO Y COLOR", VISION_SUITES)
    sys_runs, sys_pass, sys_fail, sys_err, sys_dur, sys_details = run_suite_group("SISTEMA, SEGURIDAD, RED, IPC Y PERSISTENCIA", SYSTEM_SUITES)

    grand_total_runs = vis_runs + sys_runs
    grand_total_pass = vis_pass + sys_pass
    grand_total_fail = vis_fail + sys_fail
    grand_total_err = vis_err + sys_err
    grand_total_dur = time.perf_counter() - t_start

    print("\n" + "="*80)
    print("RESUMEN GLOBAL DE REGRESIÓN (VISION-05B.1)")
    print("="*80)
    print(f"Total de Pruebas Ejecutadas:  {grand_total_runs}")
    print(f"Pruebas Pasadas (PASS):       {grand_total_pass}")
    print(f"Pruebas Fallidas (FAIL):      {grand_total_fail}")
    print(f"Errores de Ejecución (ERR):   {grand_total_err}")
    print(f"Tasa de Éxito Global:         {(grand_total_pass / grand_total_runs)*100:.2f}%" if grand_total_runs > 0 else "N/A")
    print(f"Tiempo Total de Suite:        {grand_total_dur:.2f}s")
    print("="*80)


if __name__ == "__main__":
    main()
