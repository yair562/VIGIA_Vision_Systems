import serial
import time

class ArduinoService:

    def __init__(self):
        self.arduino = None

    def conectar(self):

        if self.arduino:
            return True

        try:
            self.arduino = serial.Serial(
                port="COM3",
                baudrate=9600,
                timeout=1
            )

            time.sleep(2)

            return True

        except Exception as e:
            print(f"Error Arduino: {e}")
            return False

    def enviar(self, comando):

        if not self.arduino:
            return False

        self.arduino.write(comando.encode())
        return True