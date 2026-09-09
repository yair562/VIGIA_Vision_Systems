# traffic/bridge.py

import serial
import time
import threading

PUERTO_COM = r'\\.\COM11'
serial_lock = threading.Lock()

try:
    # Abrimos el puerto con timeout nativo de 200ms
    arduino = serial.Serial(PUERTO_COM, 9600, timeout=0.2)

    # Esperar auto-reset del Arduino
    time.sleep(2)

    # Activar líneas de control
    arduino.dtr = True
    arduino.rts = True

    print(f"🔌 [BRIDGE] ¡CONEXIÓN REAL ESTABLECIDA EN EL PUERTO {PUERTO_COM}!")

except Exception as e:
    print(
        f"⚠️ [BRIDGE] ALERTA CRÍTICA: No se pudo abrir {PUERTO_COM}. "
        f"MODO SIMULACIÓN ACTIVO. Razón: {e}"
    )
    arduino = None


def actualizar_hardware(vehiculos, tiempo_verde_base, estado):
    """
    Envía la cantidad de vehículos al Arduino.

    El Arduino ejecuta la rutina ASM:
        tiempo = (vehiculos * 3) + 5

    Retorna:
        int -> tiempo calculado por ASM
    """

    if arduino and arduino.is_open:

        with serial_lock:

            try:
                # Limpiar basura pendiente
                arduino.reset_input_buffer()

                # Enviar cantidad de vehículos
                datos = f"{vehiculos}\n"
                arduino.write(datos.encode("utf-8"))

                # Leer respuesta
                respuesta = (
                    arduino.readline()
                    .decode("utf-8", errors="ignore")
                    .strip()
                )

                if respuesta and "RESP_ASM:" in respuesta:

                    segundos_calculados = respuesta.split(":")[1]

                    print(
                        f"⚙️ [ASM ARDUINO] Operación confirmada -> "
                        f"Luz Verde: {segundos_calculados}s "
                        f"(Vehículos: {vehiculos})"
                    )

                    # IMPORTANTE:
                    # Retornamos el valor real calculado por ASM
                    return int(segundos_calculados)

                elif respuesta:

                    print(
                        f"ℹ️ [SERIAL RECV] Mensaje recibido: {respuesta}"
                    )

                else:

                    print(
                        f"⏳ [BRIDGE] Sin respuesta del Arduino "
                        f"(timeout alcanzado)"
                    )

            except Exception as e:

                print(
                    f"⚠️ [BRIDGE] Error en la transacción serial: {e}"
                )

    else:

        print(
            f"🚫 [BRIDGE HARDWARE APAGADO] "
            f"Puerto {PUERTO_COM} no disponible"
        )

    # FALLBACK
    # Si el Arduino no respondió, simulamos la misma fórmula
    tiempo_estimado = (vehiculos * 3) + 5

    print(
        f"🟡 [SIMULACIÓN] Tiempo calculado localmente: "
        f"{tiempo_estimado}s"
    )

    return tiempo_estimado