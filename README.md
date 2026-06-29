# FlightRadar24 Feeder Simulator

Este proyecto es un simulador de un alimentador (feeder) de FlightRadar24. Genera datos de tráfico aéreo simulados de forma realista y proporciona una interfaz web local para monitorizar el estado y una salida TCP con datos en formato SBS-1. 

Está diseñado para pruebas, desarrollo o demostraciones donde se requiere una fuente de datos ADS-B local sin necesidad de hardware de recepción real (como un RTL-SDR).

## Características principales

*   **Generador de Tráfico Aéreo:** Crea un grupo (pool) de aviones con rutas típicas sobre España y Europa Occidental. Los aviones se mueven en tiempo real calculando su latitud, longitud, altitud y velocidad en función del tiempo.
*   **Servidor HTTP (Interfaz Web):**
    *   **Monitorización (`index.html`):** Panel de control (Dashboard) que muestra el estado de la conexión, número de aeronaves trackeadas, estadísticas de rendimiento (mensajes por segundo, etc.) y una tabla en vivo con los aviones dentro del rango.
    *   **Configuración (`settings.html`):** Interfaz para ajustar parámetros (simulados) del receptor, ubicación, red y registro.
    *   **Endpoints JSON:** Sirve los archivos `/monitor.json` y `/flights.json` con la misma estructura que los receptores FR24 reales, facilitando la integración con herramientas de terceros o scrapers.
*   **Servidor TCP (BaseStation / SBS-1):** Expone un flujo de datos continuo en el puerto 30003, transmitiendo mensajes tipo CSV (MSG 1, 3, 4, y 8) que pueden ser leídos por software como Virtual Radar Server (VRS) o PlanePlotter.

## Archivos del Proyecto

El proyecto consta de tres archivos principales:

1.  **`simulator.py` (Script principal en Python):** Contiene toda la lógica del simulador. Genera los datos de los aviones, levanta el servidor HTTP para la interfaz web/JSON y gestiona el servidor TCP multihilo para el flujo SBS-1.
2.  **`index.html` (Panel de Estado):** Interfaz web principal. Utiliza JavaScript (Fetch API) para consultar `/monitor.json` y `/flights.json` cada 5 segundos y actualizar el DOM dinámicamente. 
3.  **`settings.html` (Panel de Configuración):** Interfaz para modificar los parámetros del simulador (simulando persistencia mediante `localStorage` para demostración).

## Requisitos

*   Python 3.6 o superior.
*   No requiere dependencias externas (solo utiliza módulos estándar como `socket`, `threading`, `http.server`, `json`, `math`, etc.).

## Instalación y Uso

1.  Clona este repositorio o descarga los 3 archivos en la misma carpeta.
2.  (Opcional) Puedes editar el archivo `simulator.py` para cambiar la dirección IP de escucha (`HOST = "192.168.1.48"`) si deseas que escuche en `0.0.0.0` (todas las interfaces) o `127.0.0.1` (solo local).
3.  Ejecuta el script de Python:

   ```bash
   python simulator.py
   ```

4.  Una vez iniciado, la consola mostrará las direcciones de acceso:
    *   **Panel de control HTTP:** `http://<TU_IP>:8754/` (o `index.html`)
    *   **Datos JSON (Vuelos):** `http://<TU_IP>:8754/flights.json`
    *   **Datos JSON (Monitor):** `http://<TU_IP>:8754/monitor.json`
    *   **Flujo de datos SBS-1:** Conecta tu cliente TCP (ej. PuTTY, netcat o Virtual Radar) a `tcp://<TU_IP>:30003`.

## Estructura de los Datos (Endpoints JSON)

El script Python responde exactamente como lo haría un receptor FR24 físico:

*   **/flights.json**: Retorna un objeto JSON donde cada clave es la dirección ICAO de un avión y el valor es un array estructurado (latitud, longitud, altitud, velocidad, etc.).
*   **/monitor.json**: Retorna un diccionario plano de variables de estado (tiempo de uptime, configuraciones simuladas, estado del MLAT, conteo de mensajes, etc.).

## Créditos y Agradecimientos
* SkyDronex - DoverKan