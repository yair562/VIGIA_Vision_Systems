class TrafficAnalyzer:
    def analizar(self, cantidad_vehiculos):
        """
        Toma la cantidad de vehículos de la cámara y determina 
        el comportamiento del semáforo.
        """
        estado = self._clasificar_estado(cantidad_vehiculos)
        tiempo_verde = self._calcular_tiempo_verde(estado)

        return {
            "vehiculos": cantidad_vehiculos,
            "estado": estado,
            "tiempo_verde_segundos": tiempo_verde
        }

    def _clasificar_estado(self, cantidad):
        if cantidad <= 2:
            return "BAJO"
        elif cantidad <= 5:
            return "MEDIO"
        else:
            return "ALTO"
            
    def _calcular_tiempo_verde(self, estado):
        if estado == "BAJO":
            return 10
        elif estado == "MEDIO":
            return 15
        else:
            return 20