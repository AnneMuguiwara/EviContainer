# controlContainer

Sistema de reciclaje inteligente que integra Raspberry Pi, Arduino y una API para:
- Validar usuarios con QR.
- Detectar presencia y flujo del proceso con una máquina de estados en Arduino (LCD, buzzer y tira LED NeoPixel).
- Capturar foto del objeto con PiCamera2.
- Enviar la imagen a una API con IA para clasificar el material.
- Reportar niveles de llenado (3 sensores ultrasónicos) al finalizar la sesión.

## 📦 Características

- ✅ Validación de usuarios por token QR contra API.
- 🔄 Flujo guiado con máquina de estados (LCD, buzzer y LED).
- 📸 Captura con autoenfoque (Picamera2).
- 🤖 Clasificación vía API (IA) y ruteo a motores opcionales según material.
- 📡 Reporte de niveles de llenado con 3 ultrasonidos (aluminio, plástico y no reciclable).
- 🧩 Modular: `photos`, `api_client`, `qr_handler`.

## 🏗️ Arquitectura

Raspberry Pi (Python) orquesta el flujo y se comunica por serial con:
- Arduino Nano Sensores (LCD, buzzer, IR, ultrasónicos) — obligatorio.
- Arduino Nano Motores (banda/servos) — opcional.
Además, se comunica con:
- Lector QR (serial).
- API Backend (Laravel u otro) para validar y clasificar.

## 📁 Estructura

```
controlContainer/
├── main.py                        # Orquestador principal
├── README.md
├── src/
│   ├── api_client.py             # Envío imagen + actualización de capacidad
│   ├── qr_handler.py             # Lectura/validación de token QR
│   ├── photos.py                 # Cámara (Picamera2)
│   └── config.py                 # Configuración local (CONTAINER_ID)
└── ArduinoNano/
    └── SensoresConect.ino        # Código Arduino (LCD, buzzer, IR, ultrasónicos, LED)
```

## 🔧 Requisitos e instalación

- Raspberry Pi OS actualizado
- Python 3
- Cámara habilitada (libcamera/Picamera2)
- Acceso a puertos serial

Dependencias del sistema:
```bash
sudo apt update
sudo apt install -y python3-pip python3-picamera2 python3-serial
```

Dependencias Python:
```bash
pip3 install requests pyserial picamera2
```

Habilitar cámara:
```bash
sudo raspi-config
# Interface Options → Camera → Enable
```

## ⚙️ Configuración

- Puertos en `main.py` (se permiten comodines):
```python
ARDUINO_SENSORES_PORT = '/dev/ttyUSB*'
ARDUINO_MOTORES_PORT  = '/dev/ttyUSB*'  
QR_SCANNER_PORT       = '/dev/ttyACM*'
BAUD_RATE = 9600
```

- ID de contenedor en `src/config.py`:
```python
CONTAINER_ID = 1  # ajusta a tu instalación
```

- Endpoints en `src/api_client.py`:
```python
SCAN_URL = "https://tu-api.com/api/scans"                 # POST imagen + ids
UPDATE_CAPACITY_URL = "https://tu-api.com/api/capacity"   # POST niveles
```

- Endpoint de validación en `src/qr_handler.py`:
```python
API_URL = "https://tu-api.com/api/validate-user"
```

- Arduino: abre y sube `ArduinoNano/SensoresConect.ino` con el Arduino IDE a tu Nano.

## ▶️ Ejecución

```bash
cd /ruta/a/controlContainer
python3 main.py
```

Flujo:
1) Usuario escanea QR → validación con API.
2) Arduino guía en LCD. Cuando detecta objeto 2s → envía `FOTO`.
3) Pi captura, envía a API y recibe resultado.
4) Se informa a Arduino: aprobado/rechazado. Motores se activan según material.
5) Al terminar sesión → se consultan ultrasonidos y se reportan a la API.

## 🔌 Protocolo Serial

- Raspberry Pi → Arduino (sensores):
  - `VALIDANDO`
  - `ERROR_SESION`
  - `SESION_OK:<nombre>`
  - `APROBADO:<material_simple>`
  - `RECHAZADO`
  - `LEER_ULTRASONICOS`

- Arduino (sensores) → Raspberry Pi:
  - `FOTO`
  - `TERMINAR`
  - `NIVELES:<alu>,<basura>,<pla>`  (valores en cm; `-1` si error)
  - `Info: ...` (logs informativos)

- Raspberry Pi → Arduino (motores, opcional):
  - `ALUMINIO`
  - `PLASTICO`
  - `OTRO`

Notas:
- El material que se envía en `APROBADO:` se “normaliza” (sin acentos) desde la respuesta de API para facilitar parsing.
- Los niveles se solicitan explícitamente al finalizar sesión con `LEER_ULTRASONICOS`.

## 🌐 API

- Validación de usuario
  - POST `/api/validate-user`
  - Headers: `Authorization: Bearer {token_qr}`
  - Respuesta 200:
    ```json
    { "success": true, "data": { "user": { "id": 123, "name": "Juan Pérez" } } }
    ```

- Envío de imagen
  - POST `/api/scans` (multipart/form-data)
  - Campos: `image` (jpeg), `container_id` (int), `user_id` (int)
  - Ejemplo 200/422:
    ```json
    { "success": true, "data": { "reciclable": true, "tipo_espanol": "Plástico", "confianza": "95%" } }
    ```

- Actualización de capacidad (niveles)
  - POST `/api/capacity` (JSON)
  - Cuerpo:
    ```json
    {
      "capacity": {
        "sensor1": 12,   // plástico
        "sensor2": 15,   // no reciclable
        "sensor3": 8     // aluminio
      }
    }
    ```

## 📸 Cámara

- `src/photos.py` usa Picamera2 con autoenfoque continuo.
- Captura por defecto a 1280x720.
- Imagen se guarda en `images/captura_YYYY-MM-DD_HH-MM-SS.jpg`.

## 🧪 Solución de problemas

- Cámara no inicializa:
  - Verifica `raspi-config`, conexión y reinicia.
- Serial no conecta:
  - Verifica puertos con `ls /dev/tty*`.
  - Agrega tu usuario a `dialout`: `sudo usermod -a -G dialout $USER` (cierra sesión).
- API no responde:
  - Revisa `SCAN_URL`, `UPDATE_CAPACITY_URL` y `API_URL`.
  - Valida conectividad y logs del backend.
- Lectura de niveles:
  - Si recibes `-1`, puede ser timeout del sensor ultrasónico. Revisa cableado y alimentación.

## ⚠️ Notas

- En `src/api_client.py`, la función `send_image_to_server` usa `SCAN_URL`. Asegúrate de definirla (no usar `API_URL` para el escaneo).
- El Arduino de motores es opcional. Si no está, el sistema opera en modo visual.

## 📄 Licencia

Consulta LICENSE.

## 👥 Autores

Equipo 3 y contribuidores.
## 💻 Probar en laptop junto con Evi (modo simulación)

Sirve para probar el flujo completo sin el hardware de la Pi, usando el micrófono y la bocina de la laptop para Evi.

1. Levanta Evi (repo RenovaAvatar) y abre el kiosko en `http://127.0.0.1:5173`.
2. En esta carpeta, prepara el entorno (solo la primera vez):
   ```
   python -m venv .venv
   .venv\Scripts\python -m pip install -r requirements-laptop.txt
   copy .env.example .env
   ```
3. En `.env` pon `SIMULATION_MODE=true`, tu `CONTAINER_TOKEN`, el puerto del lector QR (`QR_SCANNER_PORT`, p. ej. `COM13`) y en `EVI_BRIDGE_KEY` la misma clave que `CONTAINER_BRIDGE_KEY` de RenovaAvatar.
4. Corre `.venv\Scripts\python main.py`:
   - **Identificación real:** escanea el QR del usuario con el lector (serial o USB tipo teclado) y el contenedor lo valida en Ecosort. Las teclas de material no funcionan hasta que hay sesión.
   - **Material con una tecla, sin Enter** (CNN simulada): `1` plástico · `2` aluminio · `3` cartón · `4` vidrio · `5` no reciclable · `0` no reconocido
   - `f` o espacio → foto real + IA (si TensorFlow está instalado) · `t` → terminar sesión · `h` → ayuda · `q` o Ctrl+C → apagar

Evi saluda al usuario por su nombre, muestra en el kiosko la tarjeta de lo que «vio» la CNN (material, confianza, top-3 y la etiqueta «Simulación» si se eligió con tecla), reacciona a cada envase y se despide con el resumen.
El contenedor le avisa por `POST {EVI_URL}/avatar/container-event`; si Evi no está corriendo, el contenedor sigue funcionando igual.

> ⚠️ En simulación los escaneos se registran en la API real con el `CONTAINER_TOKEN` configurado: usa un usuario y contenedor de prueba.

En la Raspberry Pi no hace falta cambiar nada: con `SIMULATION_MODE=false` (valor por defecto) usa Picamera2, los Arduinos y el lector QR como siempre, y también avisa a Evi si corre en la misma Pi.
