import os
import glob
import random
import shutil
import time
import logging
from typing import Optional

# Importamos las rutas seguras que creamos en el paso anterior
from config import settings

# Configuramos el logger para este módulo
logger = logging.getLogger(__name__)


class PiCamera:
    """Cámara de la Raspberry Pi (Picamera2) con autoenfoque."""

    def __init__(self):
        # Import diferido: picamera2 solo existe en la Raspberry Pi.
        from picamera2 import Picamera2

        self.picam2 = Picamera2()
        preview_config = self.picam2.create_preview_configuration()
        self.picam2.configure(preview_config)
        self.picam2.start()
        self.picam2.set_controls({"AfMode": 2, "AfTrigger": 0})
        logger.info("Cámara inicializada con autoenfoque continuo.")
        time.sleep(2)

    def capture(self, filepath: str) -> None:
        logger.info("Enfocando y preparando para la captura...")
        capture_config = self.picam2.create_still_configuration(main={"size": (1280, 720)})
        self.picam2.switch_mode(capture_config)
        time.sleep(1)
        self.picam2.capture_file(filepath)

    def close(self) -> None:
        self.picam2.close()


class WebcamCamera:
    """Webcam de la laptop vía OpenCV (solo modo simulación)."""

    def __init__(self, index: int):
        import cv2

        self.cv2 = cv2
        self.capture_device = cv2.VideoCapture(index)
        if not self.capture_device.isOpened():
            raise RuntimeError(f"No se pudo abrir la webcam {index}.")
        logger.info(f"Webcam {index} inicializada.")

    def capture(self, filepath: str) -> None:
        # Se descartan unos cuadros para que la exposición se ajuste.
        for _ in range(5):
            self.capture_device.read()
        ok, frame = self.capture_device.read()
        if not ok:
            raise RuntimeError("La webcam no devolvió imagen.")
        self.cv2.imwrite(filepath, frame)

    def close(self) -> None:
        self.capture_device.release()


class SampleImageCamera:
    """Usa fotos ya tomadas (dataset_capturas) en lugar de una cámara (solo modo simulación)."""

    def __init__(self, folder: str):
        self.images = sorted(
            glob.glob(os.path.join(folder, "*.jpg")) + glob.glob(os.path.join(folder, "*.png"))
        )
        if not self.images:
            raise RuntimeError(f"No hay imágenes de prueba en {folder}.")
        logger.info(f"Cámara simulada con {len(self.images)} fotos de {folder}.")

    def capture(self, filepath: str) -> None:
        source = random.choice(self.images)
        shutil.copyfile(source, filepath)
        logger.info(f"[Simulación] Foto tomada de {os.path.basename(source)}")

    def close(self) -> None:
        pass


def setup_camera():
    """
    Inicializa la cámara. En la Raspberry usa Picamera2. Solo en modo simulación
    (SIMULATION_MODE=true) cae a la webcam o a las fotos de prueba, para no
    registrar escaneos falsos en producción si la cámara real falla.
    """
    mode = settings.CAMERA_MODE

    if mode in ("auto", "picamera"):
        try:
            return PiCamera()
        except Exception as e:
            if mode == "picamera" or not settings.SIMULATION_MODE:
                logger.critical(f"No se pudo inicializar la cámara. Detalle: {e}")
                return None
            logger.warning(f"Picamera2 no disponible ({e}). Probando alternativas de simulación...")

    if mode in ("auto", "webcam"):
        try:
            return WebcamCamera(settings.WEBCAM_INDEX)
        except Exception as e:
            if mode == "webcam":
                logger.critical(f"No se pudo abrir la webcam. Detalle: {e}")
                return None
            logger.warning(f"Webcam no disponible ({e}). Se usarán fotos de prueba.")

    try:
        return SampleImageCamera(settings.SAMPLE_IMAGES_DIR)
    except Exception as e:
        logger.critical(f"No hay cámara disponible. Detalle: {e}")
        return None


def take_photo(camera) -> Optional[str]:
    """Toma una fotografía, la guarda en la ruta configurada y retorna el path."""
    if not camera:
        logger.error("Intento de captura sin cámara disponible.")
        return None

    try:
        os.makedirs(settings.IMAGES_DIR, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        filepath = os.path.join(settings.IMAGES_DIR, f"captura_{timestamp}.jpg")
        camera.capture(filepath)
        logger.info(f"Foto guardada exitosamente en: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Fallo al tomar la foto: {e}")
        return None
