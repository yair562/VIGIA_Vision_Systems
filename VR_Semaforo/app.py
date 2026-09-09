print(">>> APP REAL CARGADO")

import os
import ssl
import base64
import socket
import threading

import cv2
import numpy as np

from flask import Flask, render_template, jsonify, request
from werkzeug.serving import make_server

# Importaciones de tu arquitectura local
from vision.service import process_pc_capture
from vision.processor import contar_carritos
from traffic.analyzer import TrafficAnalyzer
from traffic.bridge import actualizar_hardware

app = Flask(__name__)

# =========================
# RUTAS DE INTERFAZ
# =========================

@app.route("/")
def home():
    return render_template("index.html")


@app.route("/mobile")
def mobile():

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()

    server_url = f"https://{ip}:5443"

    return render_template(
        "mobile.html",
        server_url=server_url
    )


# =========================
# CAMARA LOCAL (PC)
# =========================

@app.route("/capture", methods=["POST"])
def capture():

    resultado = process_pc_capture()

    tiempo_real_asm = actualizar_hardware(
        resultado["vehiculos"],
        resultado["tiempo_verde_segundos"],
        resultado["estado"]
    )

    return jsonify({
        "success": True,
        "carritos": resultado["vehiculos"],
        "estado": resultado["estado"],
        "verde": tiempo_real_asm
    })


# =========================
# MOBILE UPLOAD (IMAGEN)
# =========================

@app.route("/capture-mobile", methods=["POST"])
def capture_mobile():

    file = request.files["image"]
    img_bytes = file.read()

    np_arr = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    dibujar = request.form.get(
        "dibujar",
        "false"
    ).lower() == "true"

    analizador = TrafficAnalyzer()

    if dibujar:

        # Conteo + dibujo
        n, frame_anotado, boxes = contar_carritos(
            frame,
            dibujar=True
        )

        # Análisis de tráfico
        resultado = analizador.analizar(n)

        # Cálculo REAL desde Arduino + ASM
        tiempo_real_asm = actualizar_hardware(
            resultado["vehiculos"],
            resultado["tiempo_verde_segundos"],
            resultado["estado"]
        )

        # Imagen anotada a Base64
        _, buffer = cv2.imencode(
            ".jpg",
            frame_anotado
        )

        img_base64 = base64.b64encode(
            buffer
        ).decode("utf-8")

        return jsonify({
            "success": True,
            "carritos": resultado["vehiculos"],
            "estado": resultado["estado"],
            "verde": tiempo_real_asm,
            "boxes": [
                {
                    "x": x,
                    "y": y,
                    "w": w,
                    "h": h
                }
                for (x, y, w, h) in boxes
            ],
            "imagen_anotada":
                f"data:image/jpeg;base64,{img_base64}"
        })

    else:

        # Conteo normal
        n = contar_carritos(frame)

        # Análisis de tráfico
        resultado = analizador.analizar(n)

        # Cálculo REAL desde Arduino + ASM
        tiempo_real_asm = actualizar_hardware(
            resultado["vehiculos"],
            resultado["tiempo_verde_segundos"],
            resultado["estado"]
        )

        return jsonify({
            "success": True,
            "carritos": resultado["vehiculos"],
            "estado": resultado["estado"],
            "verde": tiempo_real_asm
        })


# =========================
# SERVER START
# =========================

if __name__ == "__main__":

    BASE_DIR = os.path.dirname(
        os.path.abspath(__file__)
    )

    CERT_PATH = os.path.join(
        BASE_DIR,
        "cert.pem"
    )

    KEY_PATH = os.path.join(
        BASE_DIR,
        "key.pem"
    )

    ssl_context = None

    if (
        os.path.exists(CERT_PATH)
        and
        os.path.exists(KEY_PATH)
    ):

        ssl_context = ssl.SSLContext(
            ssl.PROTOCOL_TLS_SERVER
        )

        ssl_context.load_cert_chain(
            CERT_PATH,
            KEY_PATH
        )

        print("🔐 SSL configurado")

    else:

        print("⚠️ No se encontraron certificados")
        exit(1)

    http_server = make_server(
        "0.0.0.0",
        5000,
        app
    )

    https_server = make_server(
        "0.0.0.0",
        5443,
        app,
        ssl_context=ssl_context
    )

    t_http = threading.Thread(
        target=http_server.serve_forever,
        daemon=True
    )

    t_https = threading.Thread(
        target=https_server.serve_forever,
        daemon=True
    )

    t_http.start()
    t_https.start()

    print("🌐 HTTP en http://0.0.0.0:5000")
    print("🔐 HTTPS en https://0.0.0.0:5443")

    t_http.join()
    t_https.join()