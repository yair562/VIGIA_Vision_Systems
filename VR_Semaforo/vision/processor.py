import os
import time
import cv2
import torch
import numpy as np
from ultralytics import YOLO

# ==========================================
# Configuración del Shadow Mode (Active Learning)
# ==========================================
CARPETA_DUDAS = "dataset_dudoso"
os.makedirs(CARPETA_DUDAS, exist_ok=True)

# ==========================================
# Verificación de Aceleración por Hardware
# ==========================================
print("========================================")
print("[INFO] Verificación de GPU:")
print("CUDA Disponible:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("Dispositivo:", torch.cuda.get_device_name(0))
print("========================================\n")

print("[INFO] Cargando modelo YOLO (x) en la arquitectura VRAM...")
# Instanciamos el modelo extra grande para máxima precisión de frente
model = YOLO("yolo11x.pt")
model.to("cuda")

# Calentamiento del modelo para optimizar la primera inferencia
dummy = np.zeros((640, 640, 3), dtype=np.uint8)
model.predict(source=dummy, half=True, verbose=False)
print("[INFO] Modelo calentado correctamente")


def contar_carritos(frame, dibujar=False, params=None):
    """
    Detecta vehículos usando YOLOv11x acelerado por hardware.
    Implementa Shadow Mode para guardar imágenes con un umbral de duda en local.
    """
    inicio = time.perf_counter()
    
    # Abrimos el umbral a 0.20 para recolectar casos difíciles (como vistas frontales)
    results = model.predict(
        source=frame,
        classes=[2, 3, 5, 7],  # Clases COCO: 2=car, 3=motorcycle, 5=bus, 7=truck
        conf=0.20, 
        half=True,             # Activación de FP16 para los Tensor Cores
        verbose=False
    )
    
    tiempo = (time.perf_counter() - inicio) * 1000
    print(f"[YOLO] {tiempo:.2f} ms")
    
    result = results[0]
    boxes_yolo = result.boxes
    
    cantidad = 0
    guardar_frame = False  # Bandera de Active Learning
    
    for box in boxes_yolo:
        confianza = float(box.conf[0])
        
        # 1. Conteo oficial (Alta seguridad para el semáforo)
        if confianza >= 0.30:
            cantidad += 1
            
        # 2. Shadow Mode (Zona de duda para robustecer el dataset local)
        elif 0.20 <= confianza < 0.50:
            guardar_frame = True
            print(f"[SHADOW MODE] Objeto dudoso detectado con {confianza:.2f} de confianza.")

    # Almacenamiento local automatizado de imágenes ambiguas para escalabilidad manual
    if guardar_frame:
        timestamp = int(time.time() * 1000)
        nombre_archivo = os.path.join(CARPETA_DUDAS, f"duda_{timestamp}.jpg")
        cv2.imwrite(nombre_archivo, frame)
    
    if not dibujar:
        return cantidad
        
    # ==========================================
    # MODO DIBUJAR (Para el frontend móvil)
    # ==========================================
    lista_boxes = []
    frame_anotado = result.plot() 
    
    for box in boxes_yolo:
        # Extraemos coordenadas del tensor y pasamos a CPU/NumPy
        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
        
        # Formato estándar esperado por app.py [x, y, w, h]
        x = int(x1)
        y = int(y1)
        w = int(x2 - x1)
        h = int(y2 - y1)
        
        lista_boxes.append((x, y, w, h))
        
    return cantidad, frame_anotado, lista_boxes