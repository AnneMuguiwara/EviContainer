# config/settings.py
import os
from dotenv import load_dotenv

# Carga las variables del archivo .env al entorno de Python
load_dotenv()

# --- HARDWARE SETTINGS ---
ARDUINO_SENSORES_PORT = os.getenv("ARDUINO_SENSORES_PORT", "/dev/ttyUSB0")
ARDUINO_MOTORES_PORT = os.getenv("ARDUINO_MOTORES_PORT", "/dev/ttyUSB1")
QR_SCANNER_PORT = os.getenv("QR_SCANNER_PORT", "/dev/ttyACM0")
BAUD_RATE = int(os.getenv("BAUD_RATE", 9600))

# --- API SETTINGS (Actualizado para nueva arquitectura EcoSort) ---
# Base unificada para todos los endpoints
API_BASE_URL = os.getenv("API_BASE_URL", "https://renova-3q4h.onrender.com/api")

# Token único del contenedor
CONTAINER_TOKEN = os.getenv("CONTAINER_TOKEN", "")

# --- PATHS SETTINGS ---
# Definimos rutas absolutas para evitar problemas al ejecutar el main desde otros lados
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODELS_DIR = os.path.join(BASE_DIR, "models")
IMAGES_DIR = os.path.join(BASE_DIR, "data", "images")
# --- MODO SIMULACIÓN (pruebas en laptop sin el hardware de la Pi) ---
# Con true: la cámara cae a la webcam o a fotos de prueba, y el QR y el Arduino
# de sensores se pueden simular desde la terminal si no están conectados.
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "false").lower() == "true"
# auto | picamera | webcam | sample
CAMERA_MODE = os.getenv("CAMERA_MODE", "auto").lower()
WEBCAM_INDEX = int(os.getenv("WEBCAM_INDEX", 0))
SAMPLE_IMAGES_DIR = os.getenv("SAMPLE_IMAGES_DIR", os.path.join(BASE_DIR, "dataset_capturas"))

# --- PUENTE CON EVI (backend de RenovaAvatar en la misma máquina) ---
EVI_NOTIFY_ENABLED = os.getenv("EVI_NOTIFY_ENABLED", "true").lower() == "true"
EVI_URL = os.getenv("EVI_URL", "http://127.0.0.1:3000/api").rstrip("/")
EVI_BRIDGE_KEY = os.getenv("EVI_BRIDGE_KEY", "")
EVI_TIMEOUT = float(os.getenv("EVI_TIMEOUT", 3))
# Opcional: serial del contenedor en Ecosort, para que Evi identifique al usuario en este contenedor.
CONTAINER_SERIAL_NUMBER = os.getenv("CONTAINER_SERIAL_NUMBER", "")
