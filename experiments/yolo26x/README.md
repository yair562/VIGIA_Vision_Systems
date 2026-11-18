# Entorno Experimental Aislado — YOLO26x (VISION-03C.1)

Espacio aislado para evaluar **Ultralytics YOLO26x (`yolo26x.pt`)** frente a `yolo11n.pt` y `yolo11x.pt` sobre NVIDIA RTX 4050 Laptop GPU sin alterar el sistema productivo de VIGÍA Vision Systems.

## Estructura
- `weights/`: Pesos aislados (`yolo11n.pt` copiado por SHA-256, `yolo11x.pt` y `yolo26x.pt` descargados).
- `configs/yolo26x_eval.yaml`: Parámetros experimentales desacoplados.
- `scripts/`: Herramientas reproducibles de descarga, verificación de contrato, benchmark y evaluación por dominio.
- `results/`: Manifiestos y reportes JSON generados.
- `tests/`: Pruebas unitarias de compatibilidad con contratos de VIGÍA.
- `.venv_yolo26x/`: Entorno virtual dedicado.

## Ejecución (desde `experiments/yolo26x`)
```powershell
.\.venv_yolo26x\Scripts\python.exe scripts\prepare_weights.py
.\.venv_yolo26x\Scripts\python.exe scripts\verify_yolo26x_contract.py
.\.venv_yolo26x\Scripts\python.exe scripts\run_yolo26x_benchmark.py
.\.venv_yolo26x\Scripts\python.exe scripts\evaluate_domains_yolo26x.py
.\.venv_yolo26x\Scripts\python.exe -m unittest discover -s tests -v
```
