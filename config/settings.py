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